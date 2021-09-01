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
            self.disconnections = Semaphore(value=0)
            self.reconnections = Semaphore(value=0)
            self.updates = Semaphore(value=0)
            self.controllers = {}      

        def controller_discovered(self, ctrl: Controller):
            print('Controller discovered: {0}'.format(ctrl.device_uid))            
            self.controllers[ctrl.device_uid] = ctrl
            self.discoveries.release()

        def controller_disconnected(self, ctrl: Controller, ex):
            print('Controller disconnected: {0}'.format(ctrl.device_uid))            
            self.disconnections.release()

        def controller_reconnected(self, ctrl: Controller):
            print('Controller reconnected: {0}'.format(ctrl.device_uid))            
            self.reconnections.release()

        def controller_update(self, ctrl: Controller):
            print('Controller updated: {0}'.format(ctrl.device_uid))            
            self.updates.release()

    listener = TestListener()

    async with discovery_service(listener):

        # Expect controller discovered calls, for each fireplace

        await listener.discoveries.acquire()
        # await listener.updates.acquire()

        for c in listener.controllers:
            ctrl = listener.controllers[c] # Type: Controller
            uid = ctrl.device_uid

            assert ctrl.state == ControllerState.READY

            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            pp = PrettyPrinter(depth = 4)
            pp.pprint(ctrl)

            # test still updating
            await listener.updates[uid].acquire()
            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()