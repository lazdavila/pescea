"""Test Escea controller module functionality """
import asyncio
from typing import Any
from pescea.message import MAX_SET_TEMP, MIN_SET_TEMP
import pytest

from pescea.message import MIN_SET_TEMP, MAX_SET_TEMP, FireplaceMessage, CommandID, expected_response
from pescea.datagram import MultipleResponses
from pescea.controller import Fan, ControllerState, Controller
from pescea.discovery import DiscoveryService

class MockFireplaceInstance():
    def __init__(self, addr):
        self.is_on = False
        self.flame_effect = False
        self.fan_boost = False
        self.desired_temp = False
        self.current_temp = False
        self.ip = addr
        self.force_no_response = False

test_fireplace = MockFireplaceInstance('192.168.0.111')    

async def patched_send_command(self, command: CommandID, data: Any = None, broadcast: bool = False) -> MultipleResponses:

    if test_fireplace.force_no_response:
        return None

    responses = dict()   # type: MultipleResponses

    await asyncio.sleep(0.1)
    if command == CommandID.FAN_BOOST_OFF:
        test_fireplace.fan_boost = False
    elif command == CommandID.FAN_BOOST_ON:
        test_fireplace.fan_boost = True
    elif command == CommandID.FLAME_EFFECT_OFF:
        test_fireplace.flame_effect = False
    elif command == CommandID.FLAME_EFFECT_ON:
        test_fireplace.flame_effect= True    
    elif command == CommandID.POWER_ON:
        test_fireplace.is_on = True
        test_fireplace.current_temp = MAX_SET_TEMP
    elif command == CommandID.POWER_OFF:
        test_fireplace.is_on = False
        test_fireplace.current_temp = MIN_SET_TEMP    
    elif command == CommandID.NEW_SET_TEMP:
        test_fireplace.desired_temp = data

    responses[test_fireplace.ip] = FireplaceMessage(
                                        incoming =FireplaceMessage.mock_response(
                                                    expected_response(command),
                                                    fire_on= test_fireplace.is_on,
                                                    fan_boost_on=test_fireplace.fan_boost,
                                                    effect_on=test_fireplace.flame_effect,
                                                    desired_temp=test_fireplace.desired_temp,
                                                    current_temp=test_fireplace.current_temp))

    return responses

@pytest.mark.asyncio
async def test_controller_basics(mocker):

    discovery = DiscoveryService()
    device_uid = 1111
    device_ip = '192.168.0.111'
    
    mocker.patch(
        'pescea.datagram.FireplaceDatagram.send_command',
        patched_send_command
    )
    mocker.patch('pescea.controller.ON_OFF_BUSY_WAIT_TIME', 0.2)
    mocker.patch('pescea.controller.REFRESH_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_INTERVAL',0.1)
    mocker.patch('pescea.controller.RETRY_TIMEOUT',0.3)
    mocker.patch('pescea.controller.DISCONNECTED_INTERVAL',0.5)

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
        assert controller.is_on is None
        await asyncio.sleep(0.3)
        assert controller.state == ControllerState.READY

    assert controller.is_on

    await controller.set_on(False)

    # Should again be BUSY waiting
    assert controller.state == ControllerState.BUSY
    assert controller.is_on is None

    await asyncio.sleep(0.3)
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

@pytest.mark.asyncio
async def test_controller_change_address(mocker):

    discovery = DiscoveryService()
    device_uid = 1111
    device_ip = '192.168.0.111'

    mocker.patch(
        'pescea.datagram.FireplaceDatagram.send_command',
        patched_send_command
    )
    mocker.patch('pescea.controller.ON_OFF_BUSY_WAIT_TIME', 0.1)
    mocker.patch('pescea.controller.REFRESH_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_INTERVAL',0.1)
    mocker.patch('pescea.controller.RETRY_TIMEOUT',0.3)
    mocker.patch('pescea.controller.DISCONNECTED_INTERVAL',0.5)

    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()
    assert controller.device_ip == device_ip
    assert controller.state == ControllerState.READY

    new_ip = '192.168.0.222'
    controller.refresh_address(new_ip)
    assert controller.device_ip == new_ip

    # Allow time to poll for status and check still get response
    await asyncio.sleep(0.2)
    assert controller.state == ControllerState.READY
    
@pytest.mark.asyncio
async def test_controller_poll(mocker):

    discovery = DiscoveryService()
    device_uid = 1111
    device_ip = '192.168.0.111'

    mocker.patch(
        'pescea.datagram.FireplaceDatagram.send_command',
        patched_send_command
    )
    mocker.patch('pescea.controller.ON_OFF_BUSY_WAIT_TIME', 0.1)
    mocker.patch('pescea.controller.REFRESH_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_INTERVAL',0.1)
    mocker.patch('pescea.controller.RETRY_TIMEOUT',0.3)
    mocker.patch('pescea.controller.DISCONNECTED_INTERVAL',0.5)

    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()
    assert controller.device_ip == device_ip

    was_on = controller.is_on
    await controller.set_on(True)
    if not was_on:
        # Should still be BUSY waiting
        assert controller.state == ControllerState.BUSY
        assert controller.is_on is None
        await asyncio.sleep(0.2)
        assert controller.state == ControllerState.READY

    assert controller.is_on

    # Change what our more fireplace returns as status
    test_fireplace.is_on = False

    await asyncio.sleep(0.2)
    # Check the poll command has read the changed status
    assert not controller.is_on

        
@pytest.mark.asyncio
async def test_controller_disconnect_reconnect(mocker):

    discovery = DiscoveryService()
    device_uid = 1111
    device_ip = '192.168.0.111'

    mocker.patch(
        'pescea.datagram.FireplaceDatagram.send_command',
        patched_send_command
    )

    mocker.patch('pescea.controller.ON_OFF_BUSY_WAIT_TIME', 0.1)
    mocker.patch('pescea.controller.REFRESH_INTERVAL', 0.1)
    mocker.patch('pescea.controller.RETRY_INTERVAL',0.1)
    mocker.patch('pescea.controller.RETRY_TIMEOUT',0.3)
    mocker.patch('pescea.controller.DISCONNECTED_INTERVAL',0.5)

    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()
    assert controller.device_ip == device_ip
    assert controller.state == ControllerState.READY

    test_fireplace.force_no_response = True

    await asyncio.sleep(0.2)
    assert controller.state == ControllerState.NON_RESPONSIVE

    await asyncio.sleep(0.2)
    assert controller.state == ControllerState.DISCONNECTED

    new_ip = '192.168.0.222'
    controller.refresh_address(new_ip)
    assert controller.device_ip == new_ip

    test_fireplace.force_no_response = False
    await asyncio.sleep(0.3)
    
    assert controller.state == ControllerState.READY