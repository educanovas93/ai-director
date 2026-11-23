import asyncio
from backend.core import Director, Configuration, SimulatedOBS, Decision


def test_concurrent_next_never_overlap_ai_requests(tmp_path):
    async def scenario():
        d=Director(SimulatedOBS(),Configuration(tmp_path/'c.json'))
        await d.connect(simulated=True)
        d.config.settings.mode='ai'
        d.config.settings.timing.min_seconds=30
        d.config.settings.timing.max_seconds=30
        d.config.profiles['Concierto']['timing']=d.config.settings.timing.model_dump()
        active=0; peak=0
        async def decide(*args):
            nonlocal active,peak
            active+=1;peak=max(peak,active)
            await asyncio.sleep(.02)
            active-=1
            return Decision(scene_id='sim-2',hold_seconds=30,reason='test',source='ai')
        d.ai.decide=decide
        await d.start()
        await asyncio.gather(d.next(),d.next())
        assert peak==1
        assert d.total_changes==1
        await d.close()
    asyncio.run(scenario())
