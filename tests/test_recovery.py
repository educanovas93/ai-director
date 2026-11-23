import asyncio
import logging
import time

from backend.core import Configuration, Director, SimulatedOBS, Scene, Registry, Settings, DeepSeekEngine


def run(coro): return asyncio.run(coro)


def test_reconnect_removes_missing_scene_and_does_not_resume(tmp_path):
    async def scenario():
        obs=SimulatedOBS(); cfg=Configuration(tmp_path/'c.json'); d=Director(obs,cfg)
        await d.connect(simulated=True)
        cfg.registry.scenes['sim-2'].weight=7
        await d.start(); await d.disconnected()
        obs.scenes=[s for s in obs.scenes if s['sceneUuid']!='sim-2']
        await d.connect(simulated=True)
        assert d.state=='stopped' and d.needs_explicit_start
        assert cfg.registry.scenes['sim-2'].missing
        assert all(x['scene']!='Voz' for x in d.simulate(20))
        await d.close()
    run(scenario())


def test_mode_switch_invalidates_pending_generation(tmp_path):
    async def scenario():
        obs=SimulatedOBS(); cfg=Configuration(tmp_path/'c.json'); d=Director(obs,cfg)
        await d.connect(simulated=True); await d.start()
        old=d.generation
        cfg.settings.mode='ai'; d.generation += 1
        assert not await d.apply_decision('sim-2',old)
        await d.close()
    run(scenario())


def test_obs_library_password_logger_disabled():
    assert logging.getLogger('obsws_python.baseclient').disabled


def test_ai_frequency_is_respected(tmp_path):
    async def scenario():
        from backend.core import Decision
        obs=SimulatedOBS(); cfg=Configuration(tmp_path/'c.json'); d=Director(obs,cfg)
        await d.connect(simulated=True)
        cfg.settings.mode='ai';cfg.settings.ai.frequency_seconds=30
        async def decide(*args): return Decision(scene_id='sim-2',hold_seconds=8,reason='test',source='ai')
        d.ai.decide=decide
        await d.start();await d._decide(d.generation)
        assert d.total_changes==1
        assert d.next_at-time.monotonic() > 29
        await d.close()
    run(scenario())
