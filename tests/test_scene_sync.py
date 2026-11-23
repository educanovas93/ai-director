import asyncio
from backend.core import Director, Configuration, SimulatedOBS


def test_scene_revision_changes_on_obs_collection_update(tmp_path):
    async def scenario():
        obs=SimulatedOBS(); d=Director(obs,Configuration(tmp_path/'c.json'))
        await d.connect(simulated=True)
        first=d.status()['scene_revision']
        await d.refresh()
        assert d.status()['scene_revision']==first
        obs.scenes.append({'sceneUuid':'sim-6','sceneName':'Bajo'})
        await d.refresh()
        assert d.status()['scene_revision']>first
        await d.close()
    asyncio.run(scenario())
