import asyncio
import json
import random
from pathlib import Path

import pytest

from backend.core import AutoEngine, Settings, Scene, Registry, Configuration, Director, SimulatedOBS, validate_decision, DeepSeekEngine


def run(coro):
    return asyncio.run(coro)


def test_weighted_selection_and_memory():
    scenes = [Scene(id='a', name='A', weight=0), Scene(id='b', name='B', weight=8), Scene(id='c', name='C', enabled=False)]
    engine = AutoEngine(random.Random(8))
    decision = engine.decide(scenes, 'a', [], Settings())
    assert decision.scene_id == 'b'
    assert all(engine.decide(scenes, 'a', ['b'], Settings(memory=1)).scene_id == 'b' for _ in range(3))
    scenes[0].weight = 1
    assert engine.decide(scenes, 'c', ['b'], Settings(memory=1)).scene_id == 'a'
    assert engine.decide([scenes[0]], 'a', [], Settings()) is None
    assert engine.decide([], None, [], Settings()) is None


def test_registry_preserves_uuid_config_on_rename_and_marks_missing():
    reg = Registry({'one': Scene(id='one', name='old', weight=7, category='guitar')})
    reg.sync([{'sceneUuid': 'one', 'sceneName': 'new'}, {'sceneUuid': 'two', 'sceneName': 'other'}])
    assert reg.scenes['one'].name == 'new'
    assert reg.scenes['one'].weight == 7
    assert reg.scenes['two'].category == 'other'
    reg.sync([{'sceneUuid': 'two', 'sceneName': 'other'}])
    assert reg.scenes['one'].missing
    with pytest.raises(ValueError):
        validate_decision('one', reg, 'two')


def test_config_persists_without_secrets(tmp_path):
    cfg = Configuration(tmp_path / 'settings.json')
    cfg.settings.timing.min_seconds = 4
    cfg.registry.sync([{'sceneUuid': 'uuid', 'sceneName': 'TEST'}])
    cfg.save()
    loaded = Configuration(tmp_path / 'settings.json')
    assert loaded.settings.timing.min_seconds == 4
    assert loaded.registry.scenes['uuid'].name == 'TEST'
    assert 'password' not in (tmp_path / 'settings.json').read_text().lower()
    assert 'api_key' not in (tmp_path / 'settings.json').read_text().lower()


def test_director_pause_stop_manual_and_disconnect(tmp_path):
    async def scenario():
        obs = SimulatedOBS()
        cfg = Configuration(tmp_path / 'settings.json')
        director = Director(obs, cfg)
        await director.connect(simulated=True)
        cfg.settings.timing.min_seconds = 1
        cfg.settings.timing.max_seconds = 1
        await director.start()
        assert director.state == 'running'
        await director.pause()
        assert director.state == 'paused'
        await director.resume()
        await director.manual('sim-2')
        assert director.state == 'paused'
        await director.stop()
        assert director.state == 'stopped'
        assert director.next_at is None
        await director.start()
        await director.disconnected()
        assert director.state == 'stopped'
        assert director.needs_explicit_start
        await director.close()
    run(scenario())


def test_own_change_not_treated_as_manual_and_stale_decision_rejected(tmp_path):
    async def scenario():
        cfg = Configuration(tmp_path / 'settings.json')
        obs = SimulatedOBS()
        director = Director(obs, cfg)
        await director.connect(simulated=True)
        await director.start()
        before = director.generation
        await director.next()
        assert director.state == 'running'
        assert director.generation > before
        await director.pause()
        assert not await director.apply_decision('sim-2', generation=before)
        await director.close()
    run(scenario())


def test_deepseek_real_client_contract_and_validation():
    import httpx
    seen = []
    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={'choices': [{'finish_reason':'stop', 'message':{'content':'{"scene":"B","hold_seconds":12,"reason":"variedad","confidence":0.8}'}}], 'usage':{'total_tokens':10}})
    async def scenario():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            engine = DeepSeekEngine(client)
            result = await engine.decide('secret', 'deepseek-flash', [Scene(id='b',name='B')], 'A', [], Settings(), '')
            assert result.scene_id == 'b'
            assert result.hold_seconds == 12
        assert seen[0]['response_format'] == {'type':'json_object'}
        assert seen[0]['model'] == 'deepseek-flash'
    run(scenario())


def test_deepseek_timeout_and_invalid_json():
    import httpx
    async def scenario():
        def timeout(req): raise httpx.ReadTimeout('timeout')
        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
            with pytest.raises(httpx.ReadTimeout):
                await DeepSeekEngine(client).decide('k','deepseek-flash',[Scene(id='a',name='A')],None,[],Settings(),'')
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'not json'}}]}))) as client:
            with pytest.raises(ValueError):
                await DeepSeekEngine(client).decide('k','deepseek-flash',[Scene(id='a',name='A')],None,[],Settings(),'')
    run(scenario())


def test_unknown_scene_and_invalid_interval():
    reg = Registry({'a':Scene(id='a',name='A')})
    with pytest.raises(ValueError): validate_decision('invented',reg,None)
    with pytest.raises(ValueError): Settings.model_validate({'timing': {'min_seconds':20,'max_seconds':8}})
