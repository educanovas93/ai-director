from fastapi.testclient import TestClient
from backend.main import create_app, server_bind


def test_private_binding_allows_only_designated_interface(monkeypatch):
    monkeypatch.setenv('AI_DIRECTOR_BIND_HOST','10.208.99.128')
    monkeypatch.setenv('AI_DIRECTOR_PORT','80')
    assert server_bind()==('10.208.99.128',80)
    monkeypatch.setenv('AI_DIRECTOR_BIND_HOST','0.0.0.0')
    try: server_bind()
    except ValueError: pass
    else: assert False, 'must not bind public interfaces'


def test_private_address_http_and_ws_origin_guard(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_DIRECTOR_BIND_HOST','10.208.99.128')
    monkeypatch.setenv('AI_DIRECTOR_PORT','8765')
    app=create_app(tmp_path/'settings.json')
    with TestClient(app,base_url='http://10.208.99.128:8765') as client:
        assert client.get('/api/status').status_code==200
        assert client.post('/api/obs/connect',json={'simulated':True},headers={'Origin':'http://10.208.99.128:8765'}).status_code==200
        assert client.post('/api/director/start',headers={'Origin':'http://evil.example'}).status_code==403
        assert client.post('/api/director/start',headers={'Origin':'http://10.208.99.128:1234'}).status_code==403
        with client.websocket_connect('ws://10.208.99.128:8765/ws/status',headers={'Origin':'http://10.208.99.128:8765'}) as ws:
            assert ws.receive_json()['simulated'] is True


def test_private_reverse_proxy_port_can_use_exact_ip_url(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_DIRECTOR_BIND_HOST','10.208.99.128')
    monkeypatch.setenv('AI_DIRECTOR_PORT','8765')
    monkeypatch.setenv('AI_DIRECTOR_PUBLIC_PORT','80')
    app=create_app(tmp_path/'settings.json')
    with TestClient(app,base_url='http://10.208.99.128') as client:
        assert client.get('/api/status').status_code==200
        assert client.post('/api/director/start',headers={'Origin':'http://10.208.99.128'}).status_code==400
        assert client.post('/api/director/start',headers={'Origin':'http://evil.example'}).status_code==403
        with client.websocket_connect('ws://10.208.99.128/ws/status',headers={'Origin':'http://10.208.99.128'}) as ws:
            assert ws.receive_json()['state']=='stopped'
