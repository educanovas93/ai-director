import json
import os
import stat

from backend import main as backend_main


def test_linux_credentials_persist_in_private_file(tmp_path, monkeypatch):
    if os.name == 'nt':
        return
    secrets = tmp_path/'secrets.json'
    monkeypatch.setenv('AI_DIRECTOR_SECRETS_FILE', str(secrets))
    backend_main._secure_store('sk-opencode-test', 'opencode')
    assert backend_main._secure_load('opencode') == 'sk-opencode-test'
    assert backend_main._secure_load('deepseek') == ''
    assert stat.S_IMODE(secrets.stat().st_mode) == 0o600
    assert 'sk-opencode-test' in secrets.read_text()
    # A second provider keeps the first one instead of overwriting the file.
    backend_main._secure_store('sk-deepseek-test', 'deepseek')
    data = json.loads(secrets.read_text())
    assert data == {'opencode': 'sk-opencode-test', 'deepseek': 'sk-deepseek-test'}


def test_environment_variable_wins_over_stored_file(tmp_path, monkeypatch):
    if os.name == 'nt':
        return
    secrets = tmp_path/'secrets.json'
    secrets.write_text(json.dumps({'opencode': 'file-key'}))
    monkeypatch.setenv('AI_DIRECTOR_SECRETS_FILE', str(secrets))
    monkeypatch.setenv('OPENCODE_API_KEY', 'env-key')
    assert backend_main._secure_load('opencode') == 'env-key'
