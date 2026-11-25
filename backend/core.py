"""Domain, OBS adapters and two decision engines. No audiovisual inference in this release."""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import random
import time
from urllib.parse import urlparse
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, model_validator

log = logging.getLogger(__name__)
# obsws-python 1.8.1 logs its connection password at INFO: never let it propagate.
logging.getLogger('obsws_python').disabled = True
logging.getLogger('obsws_python').setLevel(logging.CRITICAL + 1)
logging.getLogger('obsws_python.baseclient').disabled = True
logging.getLogger('obsws_python.baseclient.ObsClient').disabled = True

Category = Literal['general', 'voice', 'guitar', 'bass', 'drums', 'zoom', 'multi', 'other']

class Scene(BaseModel):
    id: str
    name: str
    enabled: bool = True
    weight: float = Field(default=3, ge=0, le=100)
    category: Category = 'other'
    min_seconds: float | None = Field(default=None, ge=1, le=3600)
    max_seconds: float | None = Field(default=None, ge=1, le=3600)
    missing: bool = False

    @model_validator(mode='after')
    def check_duration(self):
        if self.min_seconds is not None and self.max_seconds is not None and self.min_seconds > self.max_seconds:
            raise ValueError('Duración mínima de escena superior a máxima')
        return self

class Timing(BaseModel):
    min_seconds: float = Field(default=8, ge=1, le=3600)
    max_seconds: float = Field(default=20, ge=1, le=3600)
    preferred_seconds: float = Field(default=12, ge=1, le=3600)
    memory: int = Field(default=2, ge=0, le=50)
    intensity: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode='after')
    def bounds(self):
        if self.min_seconds > self.max_seconds:
            raise ValueError('El tiempo mínimo no puede superar el máximo')
        return self

class ManualSettings(BaseModel):
    policy: Literal['temporary', 'indefinite', 'continue'] = 'temporary'
    pause_seconds: float = Field(default=30, ge=1, le=3600)

class AISettings(BaseModel):
    provider: Literal['deepseek', 'opencode'] = 'deepseek'
    model: str = Field(default='deepseek-flash', min_length=1, max_length=100)
    model_base_url: str | None = None
    instructions: str = Field(default='', max_length=4000)
    frequency_seconds: float = Field(default=12, ge=1, le=3600)
    timeout_seconds: float = Field(default=8, ge=1, le=120)
    fallback: Literal['hold', 'automatic'] = 'automatic'
    recommend_only: bool = False

    @model_validator(mode='after')
    def safe_endpoint(self):
        if self.model_base_url is not None:
            if self.provider != 'opencode' or not allowed_opencode_base(self.model_base_url):
                raise ValueError('Endpoint OpenCode no permitido')
        return self

def allowed_opencode_base(url: str) -> bool:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return (parsed.scheme == 'https' and parsed.hostname == 'opencode.ai' and port in (None, 443)
            and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
            and (parsed.path in ('/inference/openai/v1', '/inference/go/openai/v1')
                 or parsed.path.startswith('/inference/custom/conn_')))

class Settings(BaseModel):
    obs: dict[str, Any] = Field(default_factory=lambda: {'host': '127.0.0.1', 'port': 4455})
    timing: Timing = Field(default_factory=Timing)
    manual: ManualSettings = Field(default_factory=ManualSettings)
    ai: AISettings = Field(default_factory=AISettings)
    mode: Literal['automatic', 'ai'] = 'automatic'
    active_profile: str = 'Concierto'

    @model_validator(mode='after')
    def obs_bounds(self):
        if set(self.obs) - {'host', 'port'}:
            raise ValueError('Solo host y puerto OBS son persistentes')
        host = self.obs.get('host', '')
        port = self.obs.get('port', 4455)
        if not isinstance(host, str) or not host or len(host) > 255 or not isinstance(port, int) or not (1 <= port <= 65535):
            raise ValueError('Host o puerto OBS incorrecto')
        return self

class Decision(BaseModel):
    scene_id: str
    hold_seconds: float = Field(ge=1, le=3600)
    reason: str = Field(max_length=500)
    confidence: float = Field(default=1, ge=0, le=1)
    source: str = 'automatic'

class AIReply(BaseModel):
    scene: str
    hold_seconds: float
    reason: str = Field(max_length=500)
    confidence: float = Field(ge=0, le=1)

class Registry:
    def __init__(self, scenes: dict[str, Scene] | None = None):
        self.scenes = scenes or {}

    def sync(self, raw: list[dict]):
        seen = set()
        for item in raw:
            name = item.get('sceneName') or item.get('name')
            key = item.get('sceneUuid') or name
            if not name or not key:
                continue
            seen.add(key)
            if key not in self.scenes:
                # Upgrade an older name-keyed entry when OBS starts exposing UUIDs.
                old = self.scenes.pop(name, None) if key != name else None
                self.scenes[key] = old.model_copy(update={'id': key}) if old else Scene(id=key, name=name)
            self.scenes[key].name = name
            self.scenes[key].missing = False
        for key, scene in self.scenes.items():
            scene.missing = key not in seen

    def available(self):
        return [s for s in self.scenes.values() if s.enabled and not s.missing and s.weight > 0]

    def id_for(self, name: str | None):
        return next((s.id for s in self.scenes.values() if s.name == name and not s.missing), None)

    def name_for(self, ident: str | None):
        return self.scenes[ident].name if ident in self.scenes else None

class Configuration:
    def __init__(self, path: Path):
        self.path = path
        self.settings = Settings()
        self.registry = Registry()
        self.profiles: dict[str, dict] = {
            'Concierto': {'timing': {'min_seconds': 8, 'max_seconds': 20, 'preferred_seconds': 12, 'memory': 2, 'intensity': .7}, 'weights': {}, 'categories': {'zoom': 1.3, 'voice': 1.25, 'guitar': 1.2, 'general': 1}},
            'Charla': {'timing': {'min_seconds': 18, 'max_seconds': 40, 'preferred_seconds': 26, 'memory': 2, 'intensity': .2}, 'weights': {}, 'categories': {'general': 1.5, 'multi': 1.4, 'zoom': .6}},
            'Personalizado': {'timing': self.settings.timing.model_dump(), 'weights': {}, 'categories': {}},
        }
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            self.settings = Settings.model_validate(data.get('settings', {}))
            self.registry = Registry({k: Scene.model_validate(v) for k,v in data.get('scenes', {}).items()})
            self.profiles.update(data.get('profiles', {}))

    def save(self):
        data = {'settings': self.settings.model_dump(), 'scenes': {k:v.model_dump() for k,v in self.registry.scenes.items()}, 'profiles': self.profiles}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, self.path)

    def effective_timing(self):
        profile = self.profiles.get(self.settings.active_profile, {})
        return Timing.model_validate(profile.get('timing', self.settings.timing.model_dump()))

    def weights(self):
        profile = self.profiles.get(self.settings.active_profile, {})
        by_id = profile.get('weights', {})
        by_cat = profile.get('categories', {})
        return {s.id: float(by_id.get(s.id, s.weight)) * float(by_cat.get(s.category, 1)) for s in self.registry.scenes.values()}

class AutoEngine:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()

    def decide(self, scenes: list[Scene], current: str | None, history: list[str], settings: Settings, weights: dict[str,float] | None = None, timing: Timing | None = None) -> Decision | None:
        timing = timing or settings.timing
        scenes = [s for s in scenes if s.enabled and not s.missing and (weights or {}).get(s.id, s.weight) > 0]
        candidates = [s for s in scenes if s.id != current]
        if not candidates:
            return None
        recent = set(history[-timing.memory:]) if timing.memory else set()
        fresh = [s for s in candidates if s.id not in recent]
        if fresh:
            candidates = fresh
        # Relax recent exclusions only; NEVER relax disabled, missing or current exclusions.
        selected = self.rng.choices(candidates, weights=[(weights or {}).get(s.id,s.weight) for s in candidates], k=1)[0]
        low = max(timing.min_seconds, selected.min_seconds or timing.min_seconds)
        high = min(timing.max_seconds, selected.max_seconds or timing.max_seconds)
        if low > high:
            low, high = timing.min_seconds, timing.max_seconds
        hold = self.rng.triangular(low,high,max(low,min(high,timing.preferred_seconds)))
        hold = max(low, min(high, hold * (1.15 - .3*timing.intensity)))
        return Decision(scene_id=selected.id,hold_seconds=hold,reason='Selección ponderada con memoria',source='automatic')

def validate_decision(ident: str, registry: Registry, current: str | None):
    scene = registry.scenes.get(ident)
    if not scene or not scene.enabled or scene.missing or scene.weight <= 0 or ident == current:
        raise ValueError('Escena no permitida, inexistente o ya en programa')
    return scene

class DeepSeekEngine:
    """Metadata-only director for DeepSeek or OpenCode's chat-completions API."""
    URL = 'https://api.deepseek.com/chat/completions'

    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client
        self.latency = None
        self.usage = None

    async def list_models(self, provider: str, key: str, timeout: float = 8):
        if provider not in ('deepseek', 'opencode'):
            raise ValueError('Proveedor de IA desconocido')
        if provider == 'deepseek' and not key:
            raise ValueError('Introduce primero una API key de DeepSeek')
        url = ('https://api.deepseek.com/models' if provider == 'deepseek' else
               'https://opencode.ai/console/api/v1/models' if key else
               'https://opencode.ai/inference/v1/models')
        own = self.client is None
        client = self.client or httpx.AsyncClient(timeout=timeout)
        try:
            response = await client.get(url, headers={'Authorization': f'Bearer {key}'} if key else {})
            response.raise_for_status()
            raw = response.json()
            if provider == 'opencode' and key:
                entries = [(group, model) for group, details in raw.items()
                           for model in details.get('models', {}).values()]
            else:
                entries = [(provider, model) for model in raw.get('data', [])]
            models = []
            for group, item in entries:
                ident = item.get('id', '')
                if not ident or ident.endswith('-free') or item.get('type', 'chat') != 'chat':
                    continue
                api = item.get('api', {}).get('chat-completions', {})
                base = api.get('base_url')
                if provider == 'opencode' and not (base and allowed_opencode_base(base)):
                    continue
                if provider == 'deepseek':
                    inputs = item.get('input_modalities', ['text'])
                    if 'text' not in inputs or 'text' not in item.get('output_modalities', ['text']):
                        continue
                else:
                    inputs = item.get('modalities', {}).get('input', ['text'])
                cost = item.get('cost', {}).get('text', {})
                models.append({'id': ident, 'name': item.get('name') or ident,
                               'model_base_url': base if provider == 'opencode' else None,
                               'input_modalities': inputs, 'input_price': cost.get('input', {}).get('price'),
                               'output_price': cost.get('output', {}).get('price'), 'group': group})
            return {'models': sorted(models, key=lambda model: model['id']),
                    'source': 'account' if key else 'public',
                    'warning': None if key else 'Catálogo público: introduce tu clave para consultar los modelos de tu cuenta.'}
        finally:
            if own: await client.aclose()

    async def decide(self, key: str, model: str, scenes: list[Scene], current: str | None, history: list[str], settings: Settings, instructions: str, timing: Timing | None = None, seconds_since_last_cut: float = 0) -> Decision:
        provider = settings.ai.provider
        if not key: raise ValueError(f'Falta API key de {provider}')
        timing = timing or settings.timing
        context = {'mode':settings.active_profile,'current_scene':next((s.name for s in scenes if s.id==current),current),'available_scenes':[{'id':s.id,'name':s.name,'category':s.category,'weight':s.weight} for s in scenes], 'last_scenes':[next((s.name for s in scenes if s.id==ident),ident) for ident in history[-10:]], 'seconds_since_last_cut':round(seconds_since_last_cut,1),'min_seconds':timing.min_seconds,'max_seconds':timing.max_seconds,'user_instructions':instructions}
        payload = {'model':model,'messages':[{'role':'system','content':'Eres realizador de OBS. Solo dispones de metadatos. Devuelve únicamente JSON con scene, hold_seconds, reason, confidence. Escoge una escena de available_scenes distinta de current_scene. No afirmes observar vídeo ni audio.'},{'role':'user','content':json.dumps(context,ensure_ascii=False)}], 'max_tokens':256,'stream':False}
        if provider == 'deepseek':
            url = self.URL
            payload.update(response_format={'type':'json_object'},thinking={'type':'disabled'})
        elif provider == 'opencode':
            base = settings.ai.model_base_url or 'https://opencode.ai/inference/openai/v1'
            if not allowed_opencode_base(base): raise ValueError('Endpoint OpenCode no permitido')
            url = base.rstrip('/') + '/chat/completions'
        else:
            raise ValueError('Proveedor de IA desconocido')
        own = self.client is None
        client = self.client or httpx.AsyncClient(timeout=settings.ai.timeout_seconds)
        start = time.monotonic()
        try:
            res = await client.post(url,headers={'Authorization':f'Bearer {key}'},json=payload)
            res.raise_for_status()
            response = res.json()
            self.usage = response.get('usage')
            content = response['choices'][0]['message']['content']
            answer = AIReply.model_validate_json(content)
            matches = [s for s in scenes if s.id == answer.scene or s.name == answer.scene]
            if not matches: raise ValueError(f'{provider} propuso escena desconocida')
            ident = matches[0].id
            if ident == current or not matches[0].enabled or matches[0].missing: raise ValueError(f'{provider} propuso escena no permitida')
            return Decision(scene_id=ident,hold_seconds=max(timing.min_seconds,min(timing.max_seconds,answer.hold_seconds)),reason=answer.reason,confidence=answer.confidence,source='ai')
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f'Respuesta de {provider} incompleta') from exc
        finally:
            self.latency = round(time.monotonic()-start,3)
            if own: await client.aclose()

class SimulatedOBS:
    simulated = True
    def __init__(self):
        self.scenes = [{'sceneUuid':f'sim-{i}', 'sceneName':name} for i,name in enumerate(['General', 'Voz', 'Guitarra', 'Batería', 'Multicámara'],1)]
        self.current = 'General'
        self.callback = None
        self.connected = False

    async def connect(self, host=None, port=None, password=None, callback=None):
        self.connected = True
        self.callback = callback
    async def disconnect(self): self.connected = False
    async def get_scenes(self): return list(self.scenes)
    async def get_current(self): return self.current
    async def set_program(self, name, ident=None):
        if name not in [s['sceneName'] for s in self.scenes]: raise ValueError('Escena inexistente')
        self.current = name
        if self.callback: self.callback('scene',name)

class RealOBS:
    simulated = False
    def __init__(self):
        self.req = None
        self.events = None
        self.connected = False

    async def connect(self, host, port, password, callback):
        from obsws_python import ReqClient, EventClient, Subs
        # Both clients are synchronous; never block the event loop with socket IO.
        req = await asyncio.to_thread(ReqClient,host=host,port=port,password=password or '',timeout=3)
        try:
            events = await asyncio.to_thread(EventClient,host=host,port=port,password=password or '',timeout=3,subs=Subs.SCENES|Subs.CONFIG)
            def on_current_program_scene_changed(data):
                callback('scene',getattr(data,'scene_name',None))
            def on_scene_list_changed(data): callback('list',None)
            def on_scene_created(data): callback('list',None)
            def on_scene_removed(data): callback('list',None)
            def on_scene_name_changed(data): callback('list',None)
            def on_current_scene_collection_changed(data): callback('list',None)
            events.callback.register([on_current_program_scene_changed,on_scene_list_changed,on_scene_created,on_scene_removed,on_scene_name_changed,on_current_scene_collection_changed])
        except Exception:
            await asyncio.to_thread(req.base_client.ws.close)
            raise
        self.req, self.events, self.connected = req,events,True

    async def disconnect(self):
        self.connected = False
        if self.events:
            await asyncio.to_thread(self.events.disconnect)
            self.events = None
        if self.req:
            await asyncio.to_thread(self.req.base_client.ws.close)
            self.req = None

    async def get_scenes(self):
        data = await asyncio.to_thread(self.req.get_scene_list)
        return data.scenes
    async def get_current(self):
        data = await asyncio.to_thread(self.req.get_current_program_scene)
        return data.scene_name
    async def set_program(self,name,ident=None):
        # OBS WebSocket v5 accepts sceneUuid or sceneName for PROGRAM (not preview).
        payload = {'sceneUuid': ident} if ident and ident != name else {'sceneName': name}
        await asyncio.to_thread(self.req.send,'SetCurrentProgramScene',payload)

class Director:
    def __init__(self, obs, config: Configuration):
        self.obs, self.config = obs,config
        self.auto = AutoEngine()
        self.ai = DeepSeekEngine()
        self.keys = {'deepseek': os.environ.get('DEEPSEEK_API_KEY',''),
                     'opencode': os.environ.get('OPENCODE_API_KEY','')}
        self.password = os.environ.get('OBS_WEBSOCKET_PASSWORD','')
        self.state = 'stopped'
        self.connected = False
        self.generation = 0
        self.current = None
        self.history = deque(maxlen=200)
        self.events = deque(maxlen=200)
        self.total_changes = 0
        self.scene_revision = 0
        self.last_decision = ''
        self.reason = ''
        self.error = ''
        self.next_at = None
        self.started_at = None
        self.last_cut_at = None
        self.needs_explicit_start = True
        self._task = None
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self._decision_lock = asyncio.Lock()
        self._pending_own = None
        self._manual_until = None
        self._reconnect = None
        self._shutting_down = False
        self.auto_reconnect = True

    @property
    def key(self):
        return self.keys.get(self.config.settings.ai.provider, '')

    @key.setter
    def key(self, value):
        self.keys[self.config.settings.ai.provider] = value

    def _signal(self):
        self._wake.set()

    async def connect(self, simulated=False, host=None, port=None, password=None):
        # A newly selected OBS endpoint must not inherit a running scheduler.
        if self.state != 'stopped': await self.stop()
        async with self._lock:
            if self.obs.connected: await self.obs.disconnect()
            if simulated != self.obs.simulated:
                self.obs = SimulatedOBS() if simulated else RealOBS()
            self.auto_reconnect = not simulated
            host = host or self.config.settings.obs['host']
            port = port or self.config.settings.obs['port']
            if password is not None: self.password = password
            try:
                loop = asyncio.get_running_loop()
                def event(kind, value):
                    loop.call_soon_threadsafe(lambda: asyncio.create_task(self._event(kind,value)))
                await self.obs.connect(host,port,self.password,event)
                self.connected = True
                await self._refresh_locked()
                self.error = ''
                self._signal()
            except Exception as exc:
                self.connected = False
                self.error = f'OBS desconectado: {type(exc).__name__}'
                log.warning('OBS connection failed: %s',type(exc).__name__)
                raise

    async def _refresh_locked(self):
        before = {k:s.model_dump() for k,s in self.config.registry.scenes.items()}
        self.config.registry.sync(await self.obs.get_scenes())
        if before != {k:s.model_dump() for k,s in self.config.registry.scenes.items()}:
            self.scene_revision += 1
        self.current = self.config.registry.id_for(await self.obs.get_current())
        self.config.save()
        self._signal()

    async def refresh(self):
        async with self._lock:
            if not self.connected: raise ValueError('OBS desconectado')
            await self._refresh_locked()

    async def disconnected(self):
        # Never restart director automatically after reconnect.
        await self.stop()
        self.connected = False
        self.needs_explicit_start = True
        self.error = 'OBS desconectado; pulsa iniciar tras reconectar'
        self._signal()

    async def disconnect(self):
        await self.stop()
        async with self._lock:
            self.auto_reconnect = False
            await self.obs.disconnect()
            self.connected = False
            self.needs_explicit_start = True
            self._signal()

    async def _event(self,kind,value):
        if kind == 'list':
            try: await self.refresh()
            except Exception: await self.disconnected()
            return
        async with self._lock:
            ident = self.config.registry.id_for(value)
            if ident is None:
                self._signal()
                return
            self.current = ident
            if self._pending_own and self._pending_own[0] == ident and time.monotonic()-self._pending_own[1] < 3:
                self._pending_own = None
            elif self.state == 'running':
                self._pending_own = None
                policy = self.config.settings.manual
                if policy.policy != 'continue':
                    self.state = 'paused'
                    self._manual_until = time.monotonic()+policy.pause_seconds if policy.policy == 'temporary' else None
                else:
                    self.next_at = time.monotonic()+self.config.effective_timing().min_seconds
                self.generation += 1
                self.reason = 'Intervención externa OBS/Stream Deck'
                self.last_decision = value
                self.last_cut_at = time.monotonic()
                self.history.append(ident)
                self.record(value,self.reason,'external',applied=True)
            self._signal()

    async def start(self):
        async with self._lock:
            if not self.connected: raise ValueError('OBS desconectado')
            if not self.config.registry.available(): raise ValueError('Activa al menos una escena con peso positivo')
            if self.state != 'stopped': raise ValueError('La realización ya está iniciada')
            self.state = 'running'
            self.generation += 1
            self.needs_explicit_start = False
            self.started_at = time.monotonic()
            self.last_cut_at = self.started_at
            self.next_at = time.monotonic()+self.config.effective_timing().min_seconds
            self._task = asyncio.create_task(self._run())
            self._signal()

    async def pause(self):
        async with self._lock:
            if self.state != 'running': raise ValueError('Realización no activa')
            self.state = 'paused'; self.generation += 1; self.next_at = None
            self._manual_until = None
            self._signal()

    async def resume(self):
        async with self._lock:
            if self.state != 'paused': raise ValueError('No está pausado')
            self.state = 'running'; self.generation += 1; self._manual_until = None
            self.next_at = time.monotonic()+self.config.effective_timing().min_seconds
            self._signal()

    async def stop(self):
        async with self._lock:
            self.state = 'stopped'; self.generation += 1; self.next_at = None
            self._manual_until = None
            self._signal()
            task, self._task = self._task, None
        if task and task is not asyncio.current_task():
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass

    async def close(self):
        self._shutting_down = True
        await self.stop()
        if self._reconnect:
            self._reconnect.cancel()
            try: await self._reconnect
            except asyncio.CancelledError: pass
        await self.obs.disconnect()

    async def manual(self,ident):
        async with self._lock:
            if not self.connected: raise ValueError('OBS desconectado')
            scene = self.config.registry.scenes.get(ident)
            if not scene or scene.missing: raise ValueError('Escena no existe en OBS')
            if ident == self.current: return
            self._pending_own = (ident,time.monotonic())
            await self.obs.set_program(scene.name, ident)
            self.current = ident
            self.last_cut_at = time.monotonic()
            self.history.append(ident)
            self.total_changes += 1
            self.last_decision = scene.name
            self.reason = 'Cambio manual desde el panel'
            self.record(scene.name,self.reason,'manual',applied=True)
            if self.state == 'running':
                policy = self.config.settings.manual
                self.generation += 1
                if policy.policy != 'continue':
                    self.state = 'paused'
                    self._manual_until = time.monotonic()+policy.pause_seconds if policy.policy == 'temporary' else None
                    self.next_at = None
                else: self.next_at = time.monotonic()+self.config.effective_timing().min_seconds
            self._signal()

    def record(self, scene, reason, mode, accepted=True, applied=False):
        self.events.append({'timestamp':datetime.now(timezone.utc).isoformat(),'scene':scene,'reason':reason,'mode':mode,'accepted':accepted,'applied':applied})

    async def apply_decision(self, ident, generation, hold=None, reason='', source='automatic'):
        async with self._lock:
            if generation != self.generation or self.state != 'running' or not self.connected: return False
            try: scene = validate_decision(ident,self.config.registry,self.current)
            except ValueError: return False
            self._pending_own = (ident,time.monotonic())
            try:
                await self.obs.set_program(scene.name, ident)
            except Exception:
                self._pending_own = None
                await self.disconnected_unlocked()
                return False
            self.current = ident
            self.last_cut_at = time.monotonic()
            self.generation += 1
            self.history.append(ident)
            self.total_changes += 1
            self.last_decision = scene.name
            self.reason = reason
            self.record(scene.name,reason,source,applied=True)
            self.next_at = time.monotonic()+(hold or self.config.effective_timing().min_seconds)
            self._signal()
            return True

    async def disconnected_unlocked(self):
        self.connected = False
        self.state = 'stopped'; self.generation += 1; self.next_at = None
        self.needs_explicit_start = True
        self.error = 'Conexión OBS perdida; reconexión sin reanudar cortes'
        self._signal()

    async def next(self):
        if self.state != 'running': raise ValueError('Inicia la realización antes de cortar')
        await self._decide(self.generation)

    async def _decide(self, generation, dry=False):
        async with self._decision_lock:
            if not dry and (generation != self.generation or self.state != 'running' or not self.connected):
                return None
            return await self._decide_locked(generation,dry)

    async def _decide_locked(self, generation, dry=False):
        scenes = self.config.registry.available()
        if not scenes: return None
        settings = self.config.settings
        current = self.current
        history = list(self.history)
        timing = self.config.effective_timing()
        choice = None
        if settings.mode == 'ai':
            try:
                choice = await asyncio.wait_for(self.ai.decide(self.key,settings.ai.model,scenes,current,history,settings,settings.ai.instructions,timing,time.monotonic()-(self.last_cut_at or time.monotonic())),timeout=settings.ai.timeout_seconds)
                validate_decision(choice.scene_id,self.config.registry,current)
                if choice.hold_seconds < timing.min_seconds or choice.hold_seconds > timing.max_seconds:
                    raise ValueError('Duración fuera de límites')
                self.error = ''
                if settings.ai.recommend_only or dry:
                    if not dry and generation == self.generation and self.state == 'running':
                        self.next_at = time.monotonic()+max(timing.min_seconds,settings.ai.frequency_seconds)
                        self._signal()
                    self.reason = 'Recomendación IA (no aplicada): '+choice.reason
                    self.last_decision = self.config.registry.name_for(choice.scene_id) or ''
                    if not dry: self.record(self.last_decision,choice.reason,'ai',accepted=True,applied=False)
                    return choice
            except Exception as exc:
                if isinstance(exc, httpx.HTTPStatusError):
                    status = exc.response.status_code
                    hint = {401:'clave incorrecta para este proveedor',403:'modelo sin acceso o saldo insuficiente',404:'modelo/endpoint inexistente',429:'límite de peticiones'}.get(status,'error del proveedor')
                    self.error = f'{settings.ai.provider} HTTP {status}: {hint}'
                elif isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError)):
                    self.error = f'{settings.ai.provider}: timeout de {settings.ai.timeout_seconds}s; fallback local'
                else:
                    self.error = f'{settings.ai.provider}: {type(exc).__name__} (respuesta no válida o escena no permitida)'
                self.record('(sin escena)','Respuesta IA rechazada: '+type(exc).__name__,'ai',accepted=False,applied=False)
                log.warning('AI decision rejected: %s',type(exc).__name__)
                if settings.ai.fallback == 'hold':
                    if generation == self.generation and self.state == 'running':
                        self.next_at = time.monotonic()+timing.min_seconds
                        self._signal()
                    return None
        if choice is None or settings.mode != 'ai':
            choice = self.auto.decide(scenes,current,history,settings,self.config.weights(),timing)
        if not choice:
            self.next_at = time.monotonic()+timing.min_seconds
            self._signal()
            return None
        if dry: return choice
        hold = max(choice.hold_seconds,settings.ai.frequency_seconds) if choice.source == 'ai' else choice.hold_seconds
        await self.apply_decision(choice.scene_id,generation,hold,choice.reason,choice.source)
        return choice

    async def _run(self):
        while True:
            async with self._lock:
                state = self.state
                now = time.monotonic()
                if state == 'paused' and self._manual_until and now >= self._manual_until:
                    self.state = 'running'; self.generation += 1; self._manual_until = None
                    self.next_at = now+self.config.effective_timing().min_seconds
                    state = 'running'; self._signal()
                deadline = self._manual_until if state == 'paused' else self.next_at if state == 'running' else None
                generation = self.generation
                self._wake.clear()
            if state == 'stopped': return
            if deadline is None:
                await self._wake.wait()
            elif deadline > time.monotonic():
                try: await asyncio.wait_for(self._wake.wait(),deadline-time.monotonic())
                except asyncio.TimeoutError: pass
            elif state == 'running':
                await self._decide(generation)
            else:
                await asyncio.sleep(.01)

    async def reconnect_loop(self):
        while not self._shutting_down:
            await asyncio.sleep(5)
            if self.obs.simulated or self.connected or not self.auto_reconnect:
                if self.connected and not self.obs.simulated:
                    try: await self.refresh()
                    except Exception: await self.disconnected()
                continue
            try: await self.connect(simulated=False)
            except Exception: pass

    def status(self):
        now = time.monotonic()
        return {'obs_connected':self.connected,'simulated':self.obs.simulated,'scene_revision':self.scene_revision,'current_scene':self.config.registry.name_for(self.current),'mode':self.config.settings.mode,'state':self.state,'next_cut_in':round(max(0,self.next_at-now),1) if self.state=='running' and self.next_at else None,'session_seconds':int(now-self.started_at) if self.started_at and self.state!='stopped' else 0,'total_changes':self.total_changes,'last_decision':self.last_decision,'reason':self.reason,'history':list(reversed(self.events)),'ai_latency':self.ai.latency,'ai_usage':self.ai.usage,'error':self.error,'needs_explicit_start':self.needs_explicit_start}

    def simulate(self,count=20):
        if not self.connected: raise ValueError('OBS desconectado')
        scenes = self.config.registry.available()
        if not scenes: raise ValueError('Ninguna escena habilitada')
        current = self.current
        history = list(self.history)
        result=[]
        for _ in range(count):
            d = self.auto.decide(scenes,current,history,self.config.settings,self.config.weights(),self.config.effective_timing())
            if not d: break
            result.append({'scene':self.config.registry.name_for(d.scene_id),'hold_seconds':round(d.hold_seconds,1)})
            current = d.scene_id; history.append(current)
        return result
