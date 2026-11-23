import asyncio
import logging
import sys
import types
from unittest.mock import patch

from backend.core import RealOBS


def test_real_obs_registers_scene_lifecycle_events():
    async def scenario():
        calls=[]
        class Req:
            def __init__(self,**kwargs): self.base_client=types.SimpleNamespace(ws=types.SimpleNamespace(close=lambda:None))
        class Ev:
            def __init__(self,**kwargs): self.callback=types.SimpleNamespace(register=lambda f:calls.extend(x.__name__ for x in f))
            def disconnect(self): pass
        import obsws_python
        with patch.object(obsws_python,'ReqClient',Req),patch.object(obsws_python,'EventClient',Ev):
            o=RealOBS(); await o.connect('localhost',4455,'test',lambda *x:None);await o.disconnect()
        assert {'on_scene_created','on_scene_removed','on_scene_name_changed','on_scene_list_changed','on_current_scene_collection_changed'} <= set(calls)
    asyncio.run(scenario())
