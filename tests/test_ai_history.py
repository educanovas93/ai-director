import asyncio
from backend.core import Configuration, Director, SimulatedOBS, Decision


def test_ai_recommendations_are_logged_without_applying(tmp_path):
    async def scenario():
        d=Director(SimulatedOBS(),Configuration(tmp_path/'c.json'))
        await d.connect(simulated=True)
        d.config.settings.mode='ai'; d.config.settings.ai.recommend_only=True
        async def decide(*args): return Decision(scene_id='sim-2',hold_seconds=12,reason='variedad',source='ai')
        d.ai.decide=decide
        await d.start()
        await d._decide(d.generation)
        assert d.total_changes==0
        assert d.events[-1]['accepted'] and not d.events[-1]['applied']
        await d.close()
    asyncio.run(scenario())
