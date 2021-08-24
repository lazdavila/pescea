"""Test Escea controller module functionality """
import asyncio
from typing import Any
from pescea.message import MAX_SET_TEMP, MIN_SET_TEMP
import pytest

from logging import exception

from pescea.message import MIN_SET_TEMP, MAX_SET_TEMP, FireplaceMessage, CommandID, expected_response
from pescea.datagram import MultipleResponses
from pescea.controller import REFRESH_INTERVAL, REQUEST_TIMEOUT, CONNECT_RETRY_TIMEOUT, START_STOP_WAIT_TIME, Fan, Controller
from pescea.discovery import DiscoveryService

class MockFireplaceInstance():
    def __init__(self, addr):
        self.is_on = False
        self.flame_effect = False
        self.fan_boost = False
        self.desired_temp = False
        self.current_temp = False
        self.ip = addr

test_fireplace = MockFireplaceInstance('192.168.0.111')    

async def patched_send_command(self, command: CommandID, data: Any = None, broadcast: bool = False) -> MultipleResponses:
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

    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()

    assert controller.device_ip == device_ip
    assert controller.device_uid == device_uid
    assert controller.discovery == discovery

    await controller.set_on(True)
    assert controller.is_on

    await controller.set_on(False)
    assert not controller.is_on

    for fan in Fan:
        await controller.set_fan(fan)
        assert controller.fan == fan

    for temp in range(int(controller.min_temp), int(controller.max_temp)):
        await controller.set_desired_temp(float(temp))
        assert int(controller.desired_temp) == temp

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

    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()
    assert controller.device_ip == device_ip

    new_ip = '192.168.0.222'
    controller.refresh_address(new_ip)
    assert controller.device_ip == new_ip

@pytest.mark.asyncio
async def test_controller_poll(mocker):

    discovery = DiscoveryService()
    device_uid = 1111
    device_ip = '192.168.0.111'

    mocker.patch(
        'pescea.datagram.FireplaceDatagram.send_command',
        patched_send_command
    )

    mocker.patch(
        'pescea.controller.REFRESH_INTERVAL',
        0.1
    )

    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()
    assert controller.device_ip == device_ip

    await controller.set_on(True)
    assert controller.is_on

    test_fireplace.is_on = False
    await asyncio.sleep(0.2)
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

    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()
    assert controller.device_ip == device_ip

    force_disconnect
    assert controller.status is None

    new_ip = '192.168.0.222'
    controller.refresh_address(new_ip)
    assert controller.device_ip == new_ip

    assert controler.status is not none