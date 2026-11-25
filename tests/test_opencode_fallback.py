import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from backend.core import DeepSeekEngine, Scene, Settings
from backend.main import create_app


def run(coro): return asyncio.run(coro)


def test_go_key_falls_back_to_go_endpoint_with_session_headers():
    calls=[]
    def handler(req):
        calls.append(req)
        if len(calls)==1:
            return httpx.Response(404,json={'error':{'message':'model not found on this base'}})
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"scene":"Voz","hold_seconds":10,"reason":"x","confidence":0.9}'}}]})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            cfg=Settings.model_validate({'ai':{'provider':'opencode','model':'deepseek-v4.1-flash'}})
            d=await DeepSeekEngine(client).decide('k','deepseek-v4.1-flash',[Scene(id='v',name='Voz')],None,[],cfg,'')
            assert d.scene_id=='v'
    run(scenario())
    assert calls[1].url.path=='/inference/go/openai/v1/chat/completions'
    assert calls[0].headers['x-opencode-session']==calls[1].headers['x-opencode-session']
    assert calls[0].headers['user-agent'].startswith('algunos-indios-ai-director/')


def test_console_key_does_not_fall_back_when_first_base_works():
    calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"scene":"Voz","hold_seconds":10,"reason":"x","confidence":0.9}'}}]})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            cfg=Settings.model_validate({'ai':{'provider':'opencode','model':'deepseek-v4.1-flash','model_base_url':'https://opencode.ai/inference/openai/v1'}})
            await DeepSeekEngine(client).decide('k','deepseek-v4.1-flash',[Scene(id='v',name='Voz')],None,[],cfg,'')
    run(scenario())
    assert len(calls)==1 and calls[0].url.path=='/inference/openai/v1/chat/completions'


def test_empty_content_with_reasoning_retries_without_thinking():
    calls=[]
    def handler(req):
        calls.append(json.loads(req.content))
        if len(calls)==1:
            return httpx.Response(200,json={'choices':[{'message':{'content':'','reasoning_content':'pensando...'}}]})
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"scene":"Voz","hold_seconds":10,"reason":"x","confidence":0.9}'}}]})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            cfg=Settings.model_validate({'ai':{'provider':'opencode','model':'deepseek-v4.1-flash'}})
            d=await DeepSeekEngine(client).decide('k','deepseek-v4.1-flash',[Scene(id='v',name='Voz')],None,[],cfg,'')
            assert d.scene_id=='v'
    run(scenario())
    assert len(calls)==2 and calls[1]['reasoning_effort']=='none'


def test_provider_error_message_is_surfaced_without_key(tmp_path):
    app=create_app(tmp_path/'settings.json')
    app.state.director.keys['opencode']='sk-secret-never-echo'
    app.state.director.config.settings.ai.provider='opencode'
    def handler(req):
        return httpx.Response(403,json={'error':{'message':'This model requires a Go subscription'}})
    app.state.director.ai.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        c.post('/api/obs/connect',json={'simulated':True})
        r=c.post('/api/ai/test')
        assert r.status_code==502
        body=r.text
        assert '403' in body and 'Go subscription' in body
        assert 'sk-secret-never-echo' not in body
    run(app.state.director.ai.client.aclose())
