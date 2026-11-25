import asyncio
import httpx
from backend.core import Configuration, Director, SimulatedOBS


def test_runtime_ai_error_explains_auth_failure(tmp_path):
    async def scenario():
        d=Director(SimulatedOBS(),Configuration(tmp_path/'config.json'))
        await d.connect(simulated=True)
        d.config.settings.ai.provider='opencode'
        d.config.settings.ai.model='deepseek-v4.1-flash'
        d.keys['opencode']='private-key'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(401,json={'error':'unauthorized'}))) as client:
            d.ai.client=client
            await d.start()
            d.config.settings.mode='ai'
            await d.next()
            assert 'HTTP 401' in d.status()['error']
            assert 'clave' in d.status()['error'].lower()
            assert 'private-key' not in d.status()['error']
            await d.close()
    asyncio.run(scenario())
