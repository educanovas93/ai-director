import asyncio
from pathlib import Path
import pytest
from backend.core import Director, Configuration, SimulatedOBS, RealOBS


def run(coro): return asyncio.run(coro)


def test_recommend_only_does_not_spin_or_cut(tmp_path):
    async def scenario():
        obs=SimulatedOBS(); cfg=Configuration(tmp_path/'c.json'); d=Director(obs,cfg)
        await d.connect(simulated=True)
        cfg.settings.mode='ai'; cfg.settings.ai.recommend_only=True
        async def decide(*args):
            from backend.core import Decision
            return Decision(scene_id='sim-2',hold_seconds=12,reason='test',source='ai')
        d.ai.decide=decide
        await d.start()
        old=d.next_at
        await d._decide(d.generation)
        assert d.next_at > old
        assert d.total_changes==0
        await d.close()
    run(scenario())


def test_external_event_pauses_and_no_late_cut(tmp_path):
    async def scenario():
        obs=SimulatedOBS(); cfg=Configuration(tmp_path/'c.json'); d=Director(obs,cfg)
        await d.connect(simulated=True); await d.start()
        old=d.generation
        await obs.set_program('Guitarra')
        await asyncio.sleep(.02)
        assert d.state == 'paused'
        assert not await d.apply_decision('sim-2',old)
        await d.close()
    run(scenario())


def test_explicit_disconnect_disables_reconnect(tmp_path):
    async def scenario():
        d=Director(SimulatedOBS(),Configuration(tmp_path/'c.json'))
        await d.connect(simulated=True)
        await d.disconnect()
        assert d.auto_reconnect is False
        await d.close()
    run(scenario())


def test_real_obs_uses_program_uuid_not_preview():
    async def scenario():
        class Req:
            def __init__(self): self.calls=[]
            def send(self,cmd,data): self.calls.append((cmd,data))
        o=RealOBS(); o.req=Req()
        await o.set_program('General','uuid-123')
        assert o.req.calls==[('SetCurrentProgramScene',{'sceneUuid':'uuid-123'})]
    run(scenario())
