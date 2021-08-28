"""Test Escea discovery service, controller and listeners"""

import asyncio
import pytest
from asyncio import Semaphore, sleep
from pytest import mark
from pprint import PrettyPrinter

from pescea.controller import Fan, ControllerState, Controller
from pescea.discovery import DiscoveryService, Listener, discovery

from .conftest import fireplaces, patched_create_datagram_endpoint

@mark.asyncio
async def test_full_stack(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )

    mocker.patch('pescea.controller.ON_OFF_BUSY_WAIT_TIME', 0.2)
    mocker.patch('pescea.controller.REFRESH_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_TIMEOUT', 0.3)
    mocker.patch('pescea.controller.DISCONNECTED_INTERVAL', 0.5)

    discoveries = Semaphore(value=0)
    disconnections = Semaphore(value=0)
    reconnections = Semaphore(value=0)

    controllers = []

    class TestListener(Listener):
        def controller_discovered(self, _ctrl):
            print("Controller discovered: {0}".format(_ctrl.device_uid))            
            controllers.append(_ctrl)
            discoveries.release()

        def controller_disconnected(self, ctrl, ex):
            print("Controller disconnected: {0}".format(ctrl.device_uid))            
            disconnections.release()

        def controller_reconnected(self, ctrl):
            print("Controller reconnected: {0}".format(ctrl.device_uid))            
            reconnections.release()

    listener = TestListener()

    async with discovery(listener):

        # Expect controller discovered calls, for each fireplace

        for _ in fireplaces:
            await discoveries.acquire()

        pp = PrettyPrinter(depth=6)
        for ctrl in controllers:
            pp.pprint(ctrl)


        # test setting values
        ctrl = controllers[0] # Type: Controller[]

        await ctrl.set_on(True)
        await sleep(0.3)
        assert ctrl.is_on

        for fan in Fan:
            await ctrl.set_fan(fan)
            assert ctrl.fan == fan
            assert ctrl.state == ControllerState.READY

        fireplaces[ctrl.device_uid]["Responsive"] = False
        await disconnections.acquire()
        pp.pprint(fireplaces[ctrl.device_uid])
        assert ctrl.state == ControllerState.DISCONNECTED
            
        # ctrl.refresh_address(new_ip)
        # assert ctrl.device_ip == new_ip

        new_ip = '10.10.10.10'
        fireplaces[ctrl.device_uid]["IPAddress"] = new_ip
        fireplaces[ctrl.device_uid]["Responsive"] = True

        await reconnections.acquire()
        assert ctrl.state == ControllerState.READY
        assert ctrl.device_ip == new_ip

        pp.pprint(ctrl)
