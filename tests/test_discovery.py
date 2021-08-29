"""Test Escea discovery service module functionality """
import asyncio
import pytest
from pytest import mark
from asyncio import sleep

from pescea.controller import Fan, ControllerState, Controller
from pescea.discovery import DiscoveryService

from .conftest import fireplaces, patched_create_datagram_endpoint

@mark.asyncio
async def test_service_basics(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )

    mocker.patch('pescea.controller.ON_OFF_BUSY_WAIT_TIME', 0.2)
    mocker.patch('pescea.controller.REFRESH_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_TIMEOUT', 0.3)
    mocker.patch('pescea.controller.DISCONNECTED_INTERVAL', 0.5)

    discovery = DiscoveryService()
    await discovery.start_discovery()

    await sleep(0.5)

    # check has fould all controlers
    assert len(discovery.controllers) == len(fireplaces)

    for c in discovery.controllers:
        ctrl = discovery.controllers[c] # Type: Controller
        assert ctrl.state == ControllerState.READY
        assert ctrl.device_ip == fireplaces[ctrl.device_uid]['IPAddress']
        assert ctrl.is_on == fireplaces[ctrl.device_uid]['FireIsOn']
        if fireplaces[ctrl.device_uid]['FanBoost']:
            assert ctrl.fan == Fan.FAN_BOOST
        elif fireplaces[ctrl.device_uid]['FlameEffect']:
            assert ctrl.fan == Fan.FLAME_EFFECT
        else:
            assert ctrl.fan == Fan.AUTO
        assert ctrl.desired_temp == fireplaces[ctrl.device_uid]['DesiredTemp']
        assert ctrl.current_temp == fireplaces[ctrl.device_uid]['CurrentTemp']

    # change values in background and check the polling picks it up
    for f in fireplaces:
        fireplaces[f]['CurrentTemp'] = 10.0

    await sleep(0.2)
    for ctrl in discovery.controllers:
        ctrl = discovery.controllers[c] # Type: Controller
        assert ctrl.current_temp == fireplaces[ctrl.device_uid]['CurrentTemp']

    await discovery.close()

@mark.asyncio
async def test_controller_updates(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )

    mocker.patch('pescea.controller.ON_OFF_BUSY_WAIT_TIME', 0.2)
    mocker.patch('pescea.controller.REFRESH_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_TIMEOUT', 0.3)
    mocker.patch('pescea.controller.DISCONNECTED_INTERVAL', 0.5)

    discovery = DiscoveryService()
    await discovery.start_discovery()

    await sleep(0.5)

    # check has fould all controlers
    assert len(discovery.controllers) == len(fireplaces)

    for c in discovery.controllers:
        ctrl = discovery.controllers[c] # Type: Controller
        assert ctrl.state == ControllerState.READY

        assert ctrl.is_on == fireplaces[ctrl.device_uid]['FireIsOn']
        await ctrl.set_on(not ctrl.is_on)
        assert ctrl.state == ControllerState.BUSY

        if ctrl.fan == Fan.FLAME_EFFECT:
            await ctrl.set_fan(Fan.AUTO)
        elif ctrl.fan == Fan.AUTO:
            await ctrl.set_fan(Fan.FAN_BOOST)
        else:
            await ctrl.set_fan(Fan.FLAME_EFFECT)

        await ctrl.set_desired_temp(ctrl.min_temp)

    # change values in background and check the polling picks it up
    for f in fireplaces:
        fireplaces[f]['CurrentTemp'] = 10.0

    await sleep(0.5)

    for c in discovery.controllers:
        ctrl = discovery.controllers[c] # Type: Controller
        assert ctrl.state == ControllerState.READY
        assert ctrl.device_ip == fireplaces[ctrl.device_uid]['IPAddress']
        assert ctrl.is_on == fireplaces[ctrl.device_uid]['FireIsOn']
        if fireplaces[ctrl.device_uid]['FanBoost']:
            assert ctrl.fan == Fan.FAN_BOOST
        elif fireplaces[ctrl.device_uid]['FlameEffect']:
            assert ctrl.fan == Fan.FLAME_EFFECT
        else:
            assert ctrl.fan == Fan.AUTO
        assert ctrl.desired_temp == fireplaces[ctrl.device_uid]['DesiredTemp']
        assert ctrl.current_temp == fireplaces[ctrl.device_uid]['CurrentTemp']

    await discovery.close()

@mark.asyncio
async def test_no_controllers_found(mocker):
    
    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )

    mocker.patch('pescea.controller.ON_OFF_BUSY_WAIT_TIME', 0.2)
    mocker.patch('pescea.controller.REFRESH_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_TIMEOUT', 0.3)
    mocker.patch('pescea.controller.DISCONNECTED_INTERVAL', 0.5)

    for f in fireplaces:
        fireplaces[f]['NonResponsive'] = True

    discovery = DiscoveryService()
    await discovery.start_discovery()

    await sleep(0.5)

    # check no controllers found
    assert len(discovery.controllers) == 0

    await sleep(0.2)
    # check controllers found
    assert len(discovery.controllers) == 3

    fireplaces[next(iter(fireplaces))]['IPAddress'] = '11.11.11.11'

    await sleep(0.2)
    assert len(discovery.controllers) == 2

    fireplaces = test_fireplaces()

    await sleep(0.2)
    # check controllers found
    assert len(discovery.controllers) == 3

    await discovery.close()


async def test_controller_disconnection(mocker):
    # grab service

    # check has searched for fireplaces

    # check has three fireplaces

    # attempt to control each controller

    # shut down each controller
    pass
