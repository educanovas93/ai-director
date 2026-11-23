from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import create_app


def test_api_mock_full_flow(tmp_path):
    app = create_app(tmp_path / 'config.json')
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        assert client.get('/api/status').json()['state'] == 'stopped'
        assert client.post('/api/obs/connect',json={'simulated':True}).status_code == 200
        scenes = client.get('/api/scenes').json()['scenes']
        assert len(scenes) >= 3
        assert client.post('/api/director/start').status_code == 200
        assert client.post('/api/director/next').status_code == 200
        assert client.get('/api/status').json()['total_changes'] == 1
        assert len(client.post('/api/simulation',json={'count':20}).json()['changes']) == 20
        assert client.post('/api/director/stop').status_code == 200
        assert client.get('/api/status').json()['state'] == 'stopped'


def test_api_rejects_bad_origin_and_config(tmp_path):
    app = create_app(tmp_path / 'config.json')
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        assert client.post('/api/director/start').status_code == 400
        assert client.put('/api/config',json={'timing':{'min_seconds':50,'max_seconds':5}}).status_code == 422
        assert client.post('/api/obs/connect',json={'simulated':True},headers={'Origin':'https://evil.example'}).status_code == 403
        assert client.get('/api/config').json()['ai']['has_key'] is False
