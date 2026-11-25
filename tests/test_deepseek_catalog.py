import asyncio
import httpx
from backend.core import DeepSeekEngine


def test_deepseek_catalog_contains_only_text_chat_models():
    def handler(req):
        assert req.url.path=='/models'
        assert req.headers['authorization']=='Bearer test-key'
        return httpx.Response(200,json={'data':[
            {'id':'deepseek-flash','name':'Flash','input_modalities':['text','image'],'output_modalities':['text']},
            {'id':'deepseek-asr','input_modalities':['audio'],'output_modalities':['text']},
        ]})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            data=await DeepSeekEngine(client).list_models('deepseek','test-key')
        assert [m['id'] for m in data['models']]==['deepseek-flash']
    asyncio.run(scenario())
