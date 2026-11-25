import json
import os

from fastapi.testclient import TestClient
from backend.main import create_app


def test_short_key_is_rejected_and_not_stored(tmp_path, monkeypatch):
    if os.name == 'nt':
        return
    secrets = tmp_path/'secrets.json'
    monkeypatch.setenv('AI_DIRECTOR_SECRETS_FILE', str(secrets))
    app = create_app(tmp_path/'settings.json')
    with TestClient(app, base_url='http://127.0.0.1:8765') as c:
        r = c.post('/api/ai/key', json={'provider':'opencode','key':'sk-corto'})
        assert r.status_code == 422
        assert 'incompleta' in r.text
        assert not secrets.exists()


def test_key_is_trimmed_and_reported_without_value(tmp_path, monkeypatch):
    if os.name == 'nt':
        return
    secrets = tmp_path/'secrets.json'
    monkeypatch.setenv('AI_DIRECTOR_SECRETS_FILE', str(secrets))
    key = 'sk-opencode-abcdefghijklmnop'
    app = create_app(tmp_path/'settings.json')
    with TestClient(app, base_url='http://127.0.0.1:8765') as c:
        r = c.post('/api/ai/key', json={'provider':'opencode','key':f'  {key}\n'})
        assert r.status_code == 200, r.text
        assert r.json()['length'] == len(key)
        assert key not in r.text
        assert json.loads(secrets.read_text())['opencode'] == key
        config = c.get('/api/config').json()
        assert config['ai']['key_status']['opencode'] is True
        assert key not in json.dumps(config)


def test_key_saved_after_startup_is_picked_up_without_restart(tmp_path, monkeypatch):
    if os.name == 'nt':
        return
    secrets = tmp_path/'secrets.json'
    monkeypatch.setenv('AI_DIRECTOR_SECRETS_FILE', str(secrets))
    app = create_app(tmp_path/'settings.json')
    with TestClient(app, base_url='http://127.0.0.1:8765') as c:
        assert c.get('/api/config').json()['ai']['key_status']['opencode'] is False
        secrets.write_text(json.dumps({'opencode':'sk-written-later-abcdefghij'}))
        os.chmod(secrets, 0o600)
        assert c.get('/api/config').json()['ai']['key_status']['opencode'] is True
