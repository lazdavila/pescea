"""Test Escea controller module functionality """
import pytest
from pytest import mark
from asyncio import sleep

from pescea.controller import Fan, ControllerState, Controller
from pescea.discovery import DiscoveryService

from .conftest import fireplaces, patched_create_datagram_endpoint

@mark.asyncio
async def test_controller_basics(mocker):

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
    device_uid = list(fireplaces.keys())[0]
    device_ip = fireplaces[device_uid]["IPAddress"]

    # Test steps:
    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()

    assert controller.device_ip == device_ip
    assert controller.device_uid == device_uid
    assert controller.discovery == discovery
    assert controller.state == ControllerState.READY

    was_on = controller.is_on
    await controller.set_on(True)
    if not was_on:
        # Should still be BUSY waiting
        assert controller.state == ControllerState.BUSY
        assert controller.is_on #saved the setting
        await sleep(0.5)
        assert controller.state == ControllerState.READY

    assert controller.is_on

    await controller.set_on(False)
    # Should again be BUSY waiting
    assert controller.state == ControllerState.BUSY
    assert not controller.is_on # saved the setting

    await sleep(0.5)
    assert controller.state == ControllerState.READY
    assert not controller.is_on

    for fan in Fan:
        await controller.set_fan(fan)
        assert controller.fan == fan
        assert controller.state == ControllerState.READY

    for temp in range(int(controller.min_temp), int(controller.max_temp)):
        await controller.set_desired_temp(float(temp))
        assert int(controller.desired_temp) == temp
        assert controller.state == ControllerState.READY

    assert controller.current_temp is not None

    # clean shutdown
    controller.close()
    await sleep(0.2)

@mark.asyncio
async def test_controller_change_address(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )
    
    mocker.patch('pescea.controller.ON_OFF_BUSY_WAIT_TIME', 0.2)
    mocker.patch('pescea.controller.REFRESH_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_INTERVAL',0.1)
    mocker.patch('pescea.controller.RETRY_TIMEOUT',0.3)
    mocker.patch('pescea.controller.DISCONNECTED_INTERVAL',0.5)

    discovery = DiscoveryService()
    device_uid = list(fireplaces.keys())[0]
    device_ip = fireplaces[device_uid]["IPAddress"]

    # Test steps:
    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()

    assert controller.device_ip == device_ip
    assert controller.device_uid == device_uid
    assert controller.discovery == discovery
    assert controller.state == ControllerState.READY

    new_ip = '192.168.0.222'
    controller.refresh_address(new_ip)
    assert controller.device_ip == new_ip

    # Allow time to poll for status and check still get response
    await sleep(0.2)
    assert controller.state == ControllerState.READY
    assert controller.device_ip == new_ip

    # clean shutdown
    controller.close()
    await sleep(0.2)

@mark.asyncio
async def test_controller_poll(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )
    
    mocker.patch('pescea.controller.ON_OFF_BUSY_WAIT_TIME', 0.2)
    mocker.patch('pescea.controller.REFRESH_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_INTERVAL',0.1)
    mocker.patch('pescea.controller.RETRY_TIMEOUT',0.3)
    mocker.patch('pescea.controller.DISCONNECTED_INTERVAL',0.5)

    discovery = DiscoveryService()
    device_uid = list(fireplaces.keys())[0]
    device_ip = fireplaces[device_uid]["IPAddress"]

    # Test steps:
    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()

    assert controller.device_ip == device_ip
    assert controller.device_uid == device_uid
    assert controller.discovery == discovery
    assert controller.state == ControllerState.READY

    was_on = controller.is_on
    await controller.set_on(True)
    if not was_on:
        # Should still be BUSY waiting
        assert controller.state == ControllerState.BUSY
        assert controller.is_on # Saved, but not yet committed
        await sleep(0.5)
        assert controller.state == ControllerState.READY

    assert controller.is_on

    # Change in the backend what our more fireplace returns
    fireplaces[device_uid]["FireIsOn"] = False

    await sleep(0.5)
    # Check the poll command has read the changed status
    assert not controller.is_on

    # clean shutdown
    controller.close()
    await sleep(0.2)
        
@mark.asyncio
async def test_controller_disconnect_reconnect(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )
    
    mocker.patch('pescea.controller.REQUEST_TIMEOUT', 0.08)   
    mocker.patch('pescea.controller.ON_OFF_BUSY_WAIT_TIME', 0.2)
    mocker.patch('pescea.controller.REFRESH_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_TIMEOUT', 0.2)
    mocker.patch('pescea.controller.DISCONNECTED_INTERVAL', 0.3)

    discovery = DiscoveryService()
    device_uid = list(fireplaces.keys())[0]
    device_ip = fireplaces[device_uid]["IPAddress"]

    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()
    assert controller.device_ip == device_ip
    assert controller.state == ControllerState.READY

    fireplaces[device_uid]["Responsive"] = False

    await sleep(0.1)
    assert controller.state == ControllerState.NON_RESPONSIVE

    await sleep(0.2)
    assert controller.state == ControllerState.DISCONNECTED

    new_ip = fireplaces[list(fireplaces.keys())[-1]]["IPAddress"]
    controller.refresh_address(new_ip)
    assert controller.device_ip == new_ip

    fireplaces[device_uid]["Responsive"] = True
    await sleep(0.4)
    
    assert controller.state == ControllerState.READY

    # clean shutdown
    controller.close()
    await sleep(0.2)