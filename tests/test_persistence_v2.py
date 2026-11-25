from fastapi.testclient import TestClient
import pytest
from backend.main import create_app
from backend.core import Settings


def test_scene_toggle_and_provider_survive_restart_without_auto_start(tmp_path):
    path=tmp_path/'settings.json'
    app=create_app(path)
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        assert c.post('/api/obs/connect',json={'simulated':True}).status_code==200
        assert c.put('/api/scenes/sim-2',json={'enabled':False}).status_code==200
        assert c.put('/api/config',json={'ai':{'provider':'opencode','model':'deepseek-v4.1-flash','model_base_url':'https://opencode.ai/inference/openai/v1'}}).status_code==200
        assert c.post('/api/ai/key',json={'provider':'opencode','key':'session-secret-123'}).status_code==200
        assert 'session-secret-123' not in c.get('/api/config').text
        assert 'session-secret-123' not in path.read_text()
    fresh=create_app(path)
    with TestClient(fresh,base_url='http://127.0.0.1:8765') as c:
        assert c.get('/api/status').json()['state']=='stopped'
        assert c.get('/api/config').json()['ai']['provider']=='opencode'
        assert next(s for s in c.get('/api/scenes').json()['scenes'] if s['id']=='sim-2')['enabled'] is False


def test_opencode_endpoint_rejects_local_and_redirect_hosts():
    for url in ('http://127.0.0.1:9000','https://opencode.ai.evil.com/inference/openai/v1','https://opencode.ai@evil.com/inference/openai/v1','https://opencode.ai:bad/inference/openai/v1'):
        with pytest.raises(ValueError):
            Settings.model_validate({'ai':{'provider':'opencode','model_base_url':url}})
