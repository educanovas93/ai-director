import asyncio

import httpx

from backend.core import DeepSeekEngine, Scene, Settings


def run(coro): return asyncio.run(coro)


def _ok(req):
    return httpx.Response(200,json={'choices':[{'message':{'content':'{"scene":"Voz","hold_seconds":10,"reason":"x","confidence":0.9}'}}]})


def _engine_with(monkeypatch_responses):
    calls=[]
    def handler(req):
        calls.append(req)
        for fragment,response in monkeypatch_responses:
            if fragment in str(req.url):
                return response
        return httpx.Response(500,json={'error':{'message':'unexpected url'}})
    return calls, handler


def test_go_key_hitting_payg_402_falls_back_to_go():
    calls,handler=_engine_with([
        ('/inference/openai/v1', httpx.Response(402,json={'error':{'message':'Insufficient balance. This request is pay-as-you-go, billed to OpenCode Models credits.'}})),
        ('/inference/go/openai/v1', _ok(None)),
    ])
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            cfg=Settings.model_validate({'ai':{'provider':'opencode','model':'deepseek-v4.1-flash'}})
            d=await DeepSeekEngine(client).decide('k','deepseek-v4.1-flash',[Scene(id='v',name='Voz')],None,[],cfg,'')
            assert d.scene_id=='v'
    run(scenario())
    assert [c.url.path for c in calls]==['/inference/openai/v1/chat/completions','/inference/go/openai/v1/chat/completions']
    assert calls[1].headers['x-opencode-session']==calls[0].headers['x-opencode-session']


def test_plan_go_uses_go_endpoint_first():
    calls,handler=_engine_with([('/inference/go/openai/v1', _ok(None))])
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            cfg=Settings.model_validate({'ai':{'provider':'opencode','model':'deepseek-v4.1-flash','plan':'go'}})
            await DeepSeekEngine(client).decide('k','deepseek-v4.1-flash',[Scene(id='v',name='Voz')],None,[],cfg,'')
    run(scenario())
    assert len(calls)==1 and calls[0].url.path=='/inference/go/openai/v1/chat/completions'


def test_plan_payg_does_not_silently_switch_to_go():
    calls,handler=_engine_with([
        ('/inference/openai/v1', httpx.Response(402,json={'error':{'message':'Insufficient balance'}})),
        ('/inference/go/openai/v1', _ok(None)),
    ])
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            cfg=Settings.model_validate({'ai':{'provider':'opencode','model':'deepseek-v4.1-flash','plan':'payg'}})
            try:
                await DeepSeekEngine(client).decide('k','deepseek-v4.1-flash',[Scene(id='v',name='Voz')],None,[],cfg,'')
            except httpx.HTTPStatusError as exc:
                assert exc.response.status_code==402
            else:
                assert False, 'payg must not fall back to the Go plan'
    run(scenario())
    assert len(calls)==1


def test_auto_plan_remembers_working_base():
    async def scenario():
        calls=[]
        def handler(req):
            calls.append(str(req.url))
            if len(calls)==1:
                return httpx.Response(402,json={'error':{'message':'Insufficient balance'}})
            return _ok(None)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            engine=DeepSeekEngine(client)
            cfg=Settings.model_validate({'ai':{'provider':'opencode','model':'deepseek-v4.1-flash'}})
            await engine.decide('k','deepseek-v4.1-flash',[Scene(id='v',name='Voz')],None,[],cfg,'')
            await engine.decide('k','deepseek-v4.1-flash',[Scene(id='v',name='Voz')],None,[],cfg,'')
            assert engine.active_base=='https://opencode.ai/inference/go/openai/v1'
        # Second decision starts directly on the remembered Go base.
        assert len(calls)==3
    run(scenario())
