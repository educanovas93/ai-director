from fastapi.testclient import TestClient
from backend.main import create_app


def test_profile_scene_weights_are_isolated(tmp_path):
    app=create_app(tmp_path/'c.json')
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        c.post('/api/obs/connect',json={'simulated':True})
        assert c.put('/api/scenes/sim-2',json={'weight':9}).status_code==200
        assert c.post('/api/profiles',json={'action':'load','name':'Charla'}).status_code==200
        assert c.put('/api/scenes/sim-2',json={'weight':2}).status_code==200
        assert c.post('/api/profiles',json={'action':'load','name':'Concierto'}).status_code==200
        assert next(s['weight'] for s in c.get('/api/scenes').json()['scenes'] if s['id']=='sim-2')==9
