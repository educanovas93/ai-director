"""Local-only FastAPI control surface for Algunos Indios AI Director."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import httpx
import json
import logging
import os
from typing import Literal
from pathlib import Path
import socket
import threading
import time
import webbrowser
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .core import Configuration, Director, RealOBS, Settings, Scene, validate_decision

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger(__name__)


def server_bind():
    """Bind loopback by default; only the explicitly authorized private IP otherwise."""
    host = os.environ.get('AI_DIRECTOR_BIND_HOST', '127.0.0.1')
    if host not in {'127.0.0.1', '10.208.99.128'}:
        raise ValueError('Interfaz no autorizada para AI Director')
    port = int(os.environ.get('AI_DIRECTOR_PORT', '8765'))
    if not 1 <= port <= 65535:
        raise ValueError('Puerto inválido para AI Director')
    return host, port


def authorized_origin(host_header: str, origin: str | None, bind_host: str, allowed_ports: set[int]) -> bool:
    allowed_hosts = {'localhost', '127.0.0.1'} if bind_host == '127.0.0.1' else {bind_host}
    try:
        target = urlsplit('http://' + host_header)
        target_port = target.port or 80
        if target.hostname not in allowed_hosts or target_port not in allowed_ports:
            return False
        if origin is None:
            return True  # curl/health checks; browser writes include Origin.
        source = urlsplit(origin)
        return source.scheme == 'http' and source.hostname == target.hostname and (source.port or 80) == target_port
    except ValueError:
        return False

class ConnectBody(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None,ge=1,le=65535)
    password: str | None = None
    simulated: bool = False

class ModeBody(BaseModel):
    mode: str

class ManualBody(BaseModel):
    scene_id: str

class KeyBody(BaseModel):
    key: str
    provider: Literal['deepseek','opencode'] | None = None

class SimulationBody(BaseModel):
    count: int = Field(default=20,ge=1,le=100)

class ProfileBody(BaseModel):
    action: str
    name: str
    source: str | None = None


def _secrets_path() -> Path:
    return Path(os.environ.get('AI_DIRECTOR_SECRETS_FILE', str(ROOT/'data'/'.secrets.json')))


def _secure_store(key: str, provider: str):
    if os.name == 'nt':
        import keyring
        keyring.set_password('AlgunosIndiosAIDirector',provider,key)
        return
    # Linux/macOS: private 0600 file inside the gitignored data/ directory.
    path = _secrets_path()
    path.parent.mkdir(parents=True,exist_ok=True)
    data = {}
    if path.exists():
        try: data = json.loads(path.read_text(encoding='utf-8'))
        except Exception: data = {}
    data[provider] = key
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data),encoding='utf-8')
    os.chmod(temp,0o600)
    os.replace(temp,path)
    os.chmod(path,0o600)


def _secure_load(provider: str):
    if os.name == 'nt':
        try:
            import keyring
            return keyring.get_password('AlgunosIndiosAIDirector',provider) or ''
        except Exception as exc:
            log.warning('Credential Manager unavailable: %s',type(exc).__name__)
    env = os.environ.get('OPENCODE_API_KEY' if provider == 'opencode' else 'DEEPSEEK_API_KEY','')
    if env: return env
    path = _secrets_path()
    try:
        return (json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}).get(provider,'')
    except Exception:
        log.warning('Stored credential unreadable for %s',provider)
        return ''


def create_app(config_path: Path | None = None):
    bind_host, bind_port = server_bind()
    public_port = int(os.environ.get('AI_DIRECTOR_PUBLIC_PORT', str(bind_port)))
    if public_port != bind_port and (bind_host != '10.208.99.128' or public_port != 80):
        raise ValueError('Puerto público no autorizado')
    allowed_ports = {bind_port, public_port}
    config = Configuration(config_path or ROOT/'data'/'settings.json')
    director = Director(RealOBS(), config)
    director.keys.update({provider: _secure_load(provider) for provider in ('deepseek','opencode')})

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        director._reconnect = asyncio.create_task(director.reconnect_loop())
        yield
        await director.close()

    app = FastAPI(title='Algunos Indios AI Director', lifespan=lifespan)
    app.state.director = director

    @app.middleware('http')
    async def localhost_guard(request: Request, call_next):
        from fastapi.responses import JSONResponse
        if not authorized_origin(request.headers.get('host',''),request.headers.get('origin'),bind_host,allowed_ports):
            return JSONResponse({'detail':'Origen o host no autorizado'},status_code=403)
        return await call_next(request)

    def fail(exc, provider=None):
        provider = provider or config.settings.ai.provider
        label = 'OpenCode' if provider == 'opencode' else 'DeepSeek'
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            upstream = ''
            try:
                data = exc.response.json()
                upstream = str((data.get('error') or {}).get('message') or data.get('message') or '')
            except Exception:
                upstream = (exc.response.text or '')[:200]
            upstream = ' '.join(upstream.split())[:180]
            hints = {401: f'La clave no es válida para {label}, o pertenece a otro tipo de plan. Las claves OpenCode y DeepSeek no son intercambiables.',
                     403: 'Sin acceso al modelo: revisa saldo/plan y si tu clave es Go o Console. Los modelos -free de OpenCode no funcionan desde clientes externos.',
                     404: 'Modelo o endpoint desconocido: actualiza la lista de modelos y elige otro.',
                     429: 'Límite de peticiones o saldo alcanzado: espera o revisa tu cuenta.'}
            hint = hints.get(code, 'Comprueba proveedor, modelo y estado del servicio.')
            if upstream: hint += f' Proveedor: «{upstream}»'
            log.warning('AI upstream HTTP %s (%s): %s',code,provider,upstream[:120] or 'sin mensaje')
            raise HTTPException(502, {'message': f'{label} respondió HTTP {code}', 'provider': provider,
                                      'status_code': code, 'hint': hint})
        if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError)):
            raise HTTPException(504, {'message': f'{label}: tiempo de espera agotado', 'provider': provider,
                                      'hint': 'Aumenta el timeout o usa el modo automático como fallback.'})
        if isinstance(exc, ValidationError): raise HTTPException(422,str(exc))
        log.warning('Operation rejected: %s',type(exc).__name__)
        raise HTTPException(400,str(exc) if isinstance(exc,ValueError) else type(exc).__name__)

    @app.get('/api/status')
    async def status(): return director.status()

    @app.get('/api/scenes')
    async def scenes(): return {'scenes':[s.model_dump() for s in config.registry.scenes.values()]}

    @app.put('/api/scenes/{scene_id:path}')
    async def edit_scene(scene_id: str, body: dict):
        scene = config.registry.scenes.get(scene_id)
        if not scene: raise HTTPException(404,'Escena desconocida')
        if not set(body) <= {'enabled','weight','category','min_seconds','max_seconds'}:
            raise HTTPException(422,'Campo de escena no editable')
        try:
            updated = Scene.model_validate({**scene.model_dump(),**body})
            config.registry.scenes[scene_id] = updated
            if 'weight' in body:
                config.profiles[config.settings.active_profile].setdefault('weights',{})[scene_id] = updated.weight
            config.save()
            director._signal()
            return updated.model_dump()
        except Exception as exc: fail(exc)

    @app.post('/api/obs/connect')
    async def obs_connect(body: ConnectBody):
        try:
            if body.host or body.port:
                new = Settings.model_validate({**config.settings.model_dump(),'obs':{'host':body.host or config.settings.obs['host'],'port':body.port or config.settings.obs['port']}})
                config.settings = new; config.save()
            await director.connect(body.simulated,body.host,body.port,body.password)
            return director.status()
        except Exception as exc: fail(exc)

    @app.post('/api/obs/disconnect')
    async def obs_disconnect():
        try: await director.disconnect(); return director.status()
        except Exception as exc: fail(exc)

    @app.post('/api/obs/refresh')
    async def obs_refresh():
        try: await director.refresh(); return await scenes()
        except Exception as exc: fail(exc)

    @app.post('/api/director/start')
    async def start():
        try: await director.start(); return director.status()
        except Exception as exc: fail(exc)

    @app.post('/api/director/pause')
    async def pause():
        try: await director.pause(); return director.status()
        except Exception as exc: fail(exc)

    @app.post('/api/director/resume')
    async def resume():
        try: await director.resume(); return director.status()
        except Exception as exc: fail(exc)

    @app.post('/api/director/stop')
    async def stop():
        await director.stop()
        return director.status()

    @app.post('/api/director/next')
    async def next_scene():
        try: await director.next(); return director.status()
        except Exception as exc: fail(exc)

    @app.post('/api/director/manual')
    async def manual(body: ManualBody):
        try: await director.manual(body.scene_id); return director.status()
        except Exception as exc: fail(exc)

    @app.post('/api/director/mode')
    async def mode(body: ModeBody):
        try:
            config.settings = Settings.model_validate({**config.settings.model_dump(),'mode':body.mode})
            config.save()
            director.generation += 1
            if director.state == 'running': director.next_at = time.monotonic()+config.effective_timing().min_seconds
            director._signal()
            return director.status()
        except Exception as exc: fail(exc)

    @app.get('/api/config')
    async def get_config():
        return {**config.settings.model_dump(),'ai':{**config.settings.ai.model_dump(),
                'has_key':bool(director.key),'key_status':{name:bool(value) for name,value in director.keys.items()}}}

    @app.put('/api/config')
    async def put_config(body: dict):
        if not set(body) <= {'obs','timing','manual','ai','mode','active_profile'}:
            raise HTTPException(422,'Campo de configuración desconocido')
        if 'ai' in body and not isinstance(body['ai'],dict):
            raise HTTPException(422,'Configuración IA inválida')
        if 'ai' in body and set(body['ai']) & {'key','api_key','has_key','key_status'}:
            raise HTTPException(422,'Utiliza el endpoint dedicado de credenciales')
        try:
            original = config.settings.model_dump()
            for k,v in body.items():
                original[k] = {**original[k],**v} if isinstance(v,dict) and isinstance(original[k],dict) else v
            if 'ai' in body and body['ai'].get('provider',config.settings.ai.provider) != config.settings.ai.provider:
                original['ai']['model'] = body['ai'].get('model') or ('deepseek-v4.1-flash' if body['ai']['provider']=='opencode' else 'deepseek-flash')
                original['ai']['model_base_url'] = body['ai'].get('model_base_url')
            new = Settings.model_validate(original)
            if new.active_profile not in config.profiles: raise ValueError('Perfil inexistente')
            config.settings = new
            # Editing timing in an active profile updates its timing immediately.
            if 'timing' in body:
                config.profiles[new.active_profile]['timing'] = new.timing.model_dump()
            config.save()
            director.generation += 1
            if director.state == 'running': director.next_at = time.monotonic()+config.effective_timing().min_seconds
            director._signal()
            return await get_config()
        except Exception as exc: fail(exc)

    @app.get('/api/profiles')
    async def profiles(): return {'profiles':config.profiles,'active':config.settings.active_profile}

    @app.post('/api/profiles')
    async def profile(body: ProfileBody):
        import copy
        try:
            name = body.name.strip()
            if not name or len(name)>80: raise ValueError('Nombre de perfil inválido')
            if body.action == 'save':
                config.profiles[name] = {'timing':config.settings.timing.model_dump(),'weights':{s.id:s.weight for s in config.registry.scenes.values()},'categories':{}}
            elif body.action == 'duplicate':
                if name in config.profiles or body.source not in config.profiles: raise ValueError('Perfil ya existe o fuente desconocida')
                config.profiles[name] = copy.deepcopy(config.profiles[body.source])
            elif body.action == 'load':
                if name not in config.profiles: raise ValueError('Perfil desconocido')
                target = config.profiles[name]
                if not target.get('weights'):
                    target['weights'] = {s.id:s.weight for s in config.registry.scenes.values()}
                for ident, weight in target['weights'].items():
                    if ident in config.registry.scenes:
                        config.registry.scenes[ident].weight = weight
                config.settings.active_profile = name
                config.settings.timing = type(config.settings.timing).model_validate(target['timing'])
            elif body.action == 'delete':
                if name in ('Concierto','Charla','Personalizado') or name == config.settings.active_profile: raise ValueError('No puedes borrar perfiles de fábrica ni el perfil activo')
                config.profiles.pop(name)
            else: raise ValueError('Acción de perfil desconocida')
            config.save(); director.generation += 1
            if director.state == 'running': director.next_at = time.monotonic()+config.effective_timing().min_seconds
            director._signal()
            return await profiles()
        except Exception as exc: fail(exc)

    @app.post('/api/simulation')
    async def simulation(body: SimulationBody):
        try: return {'changes':director.simulate(body.count),'mode':'automatic','note':'Simulación local; OBS no se modifica'}
        except Exception as exc: fail(exc)

    @app.post('/api/ai/key')
    async def ai_key(body: KeyBody):
        provider = body.provider or config.settings.ai.provider
        try:
            _secure_store(body.key,provider)
            director.keys[provider] = body.key
            return {'has_key':bool(body.key),'persistent':os.name=='nt','provider':provider}
        except Exception as exc: fail(exc,provider)

    @app.get('/api/ai/models')
    async def ai_models(provider: Literal['deepseek','opencode'] | None = None):
        selected = provider or config.settings.ai.provider
        try:
            return await asyncio.wait_for(director.ai.list_models(selected,director.keys.get(selected,''),config.settings.ai.timeout_seconds),timeout=config.settings.ai.timeout_seconds)
        except Exception as exc: fail(exc,selected)

    @app.post('/api/ai/test')
    async def ai_test():
        try:
            cfg = config.settings
            available = config.registry.available()
            if not available: raise ValueError('No hay escenas disponibles')
            result = await asyncio.wait_for(director.ai.decide(director.key,cfg.ai.model,available,director.current,list(director.history),cfg,cfg.ai.instructions,config.effective_timing(),time.monotonic()-(director.last_cut_at or time.monotonic())),timeout=cfg.ai.timeout_seconds)
            validate_decision(result.scene_id,config.registry,director.current)
            director.record(config.registry.name_for(result.scene_id),result.reason,'ai-test',applied=False)
            return {'accepted':True,'applied':False,'scene':config.registry.name_for(result.scene_id),'decision':result.model_dump(),'latency':director.ai.latency,'usage':director.ai.usage,'base_url':director.ai.last_url}
        except Exception as exc:
            director.record('(sin escena)','Prueba IA rechazada: '+type(exc).__name__,'ai-test',accepted=False)
            fail(exc)

    @app.get('/api/history')
    async def history(): return {'history':list(reversed(director.events)),'scenes':[config.registry.name_for(s) or s for s in reversed(director.history)],'total_changes':director.total_changes}

    @app.websocket('/ws/status')
    async def ws_status(ws: WebSocket):
        if not authorized_origin(ws.headers.get('host',''),ws.headers.get('origin'),bind_host,allowed_ports):
            await ws.close(code=1008); return
        await ws.accept()
        try:
            while True:
                await ws.send_json(director.status())
                await asyncio.sleep(1)
        except (WebSocketDisconnect,RuntimeError,ConnectionError): pass

    @app.get('/')
    async def index(): return FileResponse(ROOT/'frontend'/'index.html')
    app.mount('/css',StaticFiles(directory=ROOT/'frontend'/'css'),name='css')
    app.mount('/js',StaticFiles(directory=ROOT/'frontend'/'js'),name='js')
    return app


if __name__ == '__main__':
    import uvicorn
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
    host, port = server_bind()
    def open_when_ready():
        for _ in range(100):
            try:
                with socket.create_connection((host,port),timeout=.2):
                    webbrowser.open(f'http://{host}:{port}/'); return
            except OSError: time.sleep(.1)
    if os.environ.get('AI_DIRECTOR_NO_BROWSER') != '1':
        threading.Thread(target=open_when_ready,daemon=True).start()
    uvicorn.run(create_app(),host=host,port=port,log_level='info')
