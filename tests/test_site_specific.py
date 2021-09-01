"""Test Escea site specific configuration """

import pytest
from asyncio import Semaphore, sleep
from pytest import mark
from pprint import PrettyPrinter

from pescea.controller import Controller, Fan, ControllerState
from pescea.discovery import Listener, discovery_service

@mark.asyncio
async def test_site_specific():
    """Will only work on networks with real fireplaces"""

    class TestListener(Listener):

        def __init__( self ):
            self.discoveries = Semaphore(value=0)
            self.disconnections = {}
            self.reconnections = {}
            self.updates = {}
            self.controllers = {}
            self.pp = PrettyPrinter(depth=4)      

        def controller_discovered(self, ctrl: Controller):
            uid = ctrl.device_uid
            print('Controller discovered: {0}'.format(uid))    
            self.pp.pprint(ctrl._system_settings)
            self.disconnections[uid] = Semaphore(value=0)
            self.reconnections[uid] = Semaphore(value=0)
            self.updates[uid] = Semaphore(value=0)                    
            self.controllers[uid] = ctrl
            self.discoveries.release()

        def controller_disconnected(self, ctrl: Controller, ex):
            uid = ctrl.device_uid
            print('Controller disconnected: {0}'.format(uid))            
            self.pp.pprint(ctrl._system_settings)
            self.disconnections[uid].release()

        def controller_reconnected(self, ctrl: Controller):
            uid = ctrl.device_uid
            print('Controller reconnected: {0}'.format(uid))            
            self.pp.pprint(ctrl._system_settings)
            self.reconnections[uid].release()

        def controller_update(self, ctrl: Controller):
            uid = ctrl.device_uid
            print('Controller updated: {0}'.format(uid))            
            self.pp.pprint(ctrl._system_settings)
            self.updates[uid].release()

    listener = TestListener()

    async with discovery_service(listener):

        # Expect controller discovered calls, for each fireplace

        await listener.discoveries.acquire()

        for c in listener.controllers:
            ctrl = listener.controllers[c] # Type: Controller
            uid = ctrl.device_uid
        
            await listener.updates[uid].acquire()

            assert ctrl.state == ControllerState.READY

            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()



            # test still updating
            await listener.updates[uid].acquire()
            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()