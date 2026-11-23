import asyncio
from backend.core import Configuration, Director, SimulatedOBS


def test_stop_cancels_waiting_timer_without_cut(tmp_path):
    async def scenario():
        d=Director(SimulatedOBS(),Configuration(tmp_path/'c.json'))
        await d.connect(simulated=True)
        d.config.profiles['Concierto']['timing'].update(min_seconds=1,max_seconds=1,preferred_seconds=1)
        await d.start()
        await d.stop()
        await asyncio.sleep(1.1)
        assert d.total_changes==0
        assert d.status()['state']=='stopped'
        await d.close()
    asyncio.run(scenario())
