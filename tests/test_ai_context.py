import asyncio
import json
import httpx
from backend.core import DeepSeekEngine, Scene, Settings


def test_ai_context_contains_scene_names_and_elapsed_time():
    sent=[]
    def handler(req):
        sent.append(json.loads(req.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"scene":"Guitarra","hold_seconds":12,"reason":"alternar","confidence":0.8}'}}]})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await DeepSeekEngine(client).decide('key','deepseek-flash',[Scene(id='uuid-1',name='Guitarra')],'uuid-2',['uuid-3'],Settings(),'sin audiovisual',seconds_since_last_cut=11)
    asyncio.run(scenario())
    context=json.loads(sent[0]['messages'][1]['content'])
    assert context['seconds_since_last_cut']==11
    assert context['available_scenes'][0]['name']=='Guitarra'
    assert sent[0]['max_tokens'] <= 512
