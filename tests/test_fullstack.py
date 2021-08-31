"""Test Escea discovery service, controller and listeners"""

import pytest
from asyncio import Semaphore, sleep
from pytest import mark
from pprint import PrettyPrinter

from pescea.controller import Fan, ControllerState
from pescea.discovery import Listener, discovery_service

from .conftest import fireplaces, patched_create_datagram_endpoint, reset_fireplaces

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

    mocker.patch('pescea.datagram.REQUEST_TIMEOUT', 0.5)

    discoveries = Semaphore(value=0)
    disconnections = Semaphore(value=0)
    reconnections = Semaphore(value=0)

    controllers = []

    for f in fireplaces:
        fireplaces[f]['Responsive'] = True

    class TestListener(Listener):
        def controller_discovered(self, ctrl):
            print('Controller discovered: {0}'.format(ctrl.device_uid))            
            controllers.append(ctrl)
            discoveries.release()

        def controller_disconnected(self, ctrl, ex):
            print('Controller disconnected: {0}'.format(ctrl.device_uid))            
            disconnections.release()

        def controller_reconnected(self, ctrl):
            print('Controller reconnected: {0}'.format(ctrl.device_uid))            
            reconnections.release()

    listener = TestListener()

    async with discovery_service(listener):

        # Expect controller discovered calls, for each fireplace

        for _ in fireplaces:
            await discoveries.acquire()

        for ctrl in controllers:

            assert ctrl.state == ControllerState.READY

            # test toggling power
            new_on = not ctrl.is_on
            await ctrl.set_on(new_on)
            await sleep(0.05)
            assert ctrl.state == ControllerState.BUSY
            await sleep(0.3)
            assert ctrl.state == ControllerState.READY
            assert ctrl.is_on == new_on

            await ctrl.set_fan(Fan.AUTO)
            assert ctrl.fan == Fan.AUTO

            fireplaces[ctrl.device_uid]['Responsive'] = False

            await disconnections.acquire()
            assert ctrl.state == ControllerState.DISCONNECTED

            new_ip = '10.10.10.'+str(ctrl.device_uid % 256)
            fireplaces[ctrl.device_uid]['IPAddress'] = new_ip
            fireplaces[ctrl.device_uid]['Responsive'] = True
            
            await reconnections.acquire()
            assert ctrl.state == ControllerState.READY
            assert ctrl.device_ip == new_ip