import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from backend.core import Configuration, DeepSeekEngine, Scene, Settings
from backend.main import create_app


def run(coro): return asyncio.run(coro)


def test_opencode_key_uses_opencode_endpoint_and_compatible_payload():
    requests=[]
    def handler(req):
        requests.append(req)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"scene":"Guitarra","hold_seconds":9,"reason":"variedad","confidence":0.8}'}}], 'usage':{'cost':0.001}})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            cfg=Settings.model_validate({'ai':{'provider':'opencode','model':'deepseek-v4.1-flash'}})
            decision=await DeepSeekEngine(client).decide('opencode-test-key','deepseek-v4.1-flash',[Scene(id='a',name='Guitarra')],None,[],cfg,'')
            assert decision.scene_id=='a'
    run(scenario())
    assert requests[0].url.host=='opencode.ai'
    assert requests[0].url.path=='/inference/openai/v1/chat/completions'
    assert requests[0].headers['authorization']=='Bearer opencode-test-key'
    assert 'thinking' not in json.loads(requests[0].content)


def test_models_catalog_filters_chat_and_untrusted_endpoints(tmp_path):
    app=create_app(tmp_path/'settings.json')
    app.state.director.keys['opencode']='test-opencode'
    catalog={'opencode':{'models':{
        'deepseek-v4.1-flash':{'id':'deepseek-v4.1-flash','name':'DeepSeek Flash','type':'chat','modalities':{'input':['text','image/png']},'cost':{'text':{'input':{'price':.12},'output':{'price':.48}}},'api':{'chat-completions':{'base_url':'https://opencode.ai/inference/openai/v1'}}},
        'bad':{'id':'bad','type':'chat','api':{'chat-completions':{'base_url':'http://127.0.0.1:9000'}}},
        'image-only':{'id':'image-only','type':'image','api':{'images':{'base_url':'https://opencode.ai/inference/openai/v1'}}},
        'deepseek-v4.1-flash-free':{'id':'deepseek-v4.1-flash-free','type':'chat','api':{'chat-completions':{'base_url':'https://opencode.ai/inference/openai/v1'}}},
    }}}
    def handler(req):
        assert req.url.path=='/console/api/v1/models'
        return httpx.Response(200,json=catalog)
    app.state.director.ai.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        r=c.get('/api/ai/models?provider=opencode')
        assert r.status_code==200,r.text
        data=r.json()
        assert [m['id'] for m in data['models']]==['deepseek-v4.1-flash']
        assert data['models'][0]['input_price']==.12
        assert 'image/png' in data['models'][0]['input_modalities']
    run(app.state.director.ai.client.aclose())


def test_provider_http_error_is_actionable_and_redacted(tmp_path):
    app=create_app(tmp_path/'settings.json')
    app.state.director.key='never-print-this-secret'
    app.state.director.ai.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(401,json={'error':{'message':'invalid api key'}})))
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        c.post('/api/obs/connect',json={'simulated':True})
        r=c.post('/api/ai/test')
        assert r.status_code in (400,502)
        assert '401' in r.text
        assert 'never-print-this-secret' not in r.text
        assert 'DeepSeek' in r.text
    run(app.state.director.ai.client.aclose())


def test_ai_provider_settings_persist_without_keys(tmp_path):
    cfg=Configuration(tmp_path/'settings.json')
    cfg.settings.ai.provider='opencode'
    cfg.settings.ai.model='deepseek-v4.1-flash'
    cfg.save()
    assert Configuration(tmp_path/'settings.json').settings.ai.provider=='opencode'
    assert 'api_key' not in (tmp_path/'settings.json').read_text().lower()
