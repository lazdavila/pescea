"""Test Escea controller module functionality """
from _typeshed import NoneType
import asyncio
from typing import Any
from pescea.message import MAX_SET_TEMP, MIN_SET_TEMP
import pytest

from logging import exception

from pescea.message import MIN_SET_TEMP, MAX_SET_TEMP, FireplaceMessage, CommandID, ResponseID
from pescea.datagram import MultipleResponses
from pescea.controller import REFRESH_INTERVAL, REQUEST_TIMEOUT, CONNECT_RETRY_TIMEOUT, START_STOP_WAIT_TIME, Fan, Controller
from pescea.discovery import DiscoveryService

class MockFireplaceInstance():
    def __init__(self, addr):
        self._is_on = False
        self._flame_effect = False
        self._fan_boost = False
        self._desired_temp = False
        self._current_temp = False
        self._ip = addr

    async def send_command(self, command: CommandID, data: Any = None, broadcast: bool = False) -> MultipleResponses:
        responses = dict()   # type: MultipleResponses

        await asyncio.sleep(0.1)
        if command == CommandID.FAN_BOOST_OFF:
            self._fan_boost = False
        elif command == CommandID.FAN_BOOST_ON:
            self._fan_boost = True
        elif command == CommandID.FLAME_EFFECT_OFF:
            self._flame_effect = False
        elif command == CommandID.FLAME_EFFECT_ON:
            self._flame_effect= True    
        elif command == CommandID.POWER_ON:
            self._is_on = True
            self._current_temp = MAX_SET_TEMP
        elif command == CommandID.POWER_OFF:
            self._is_on = False
            self._current_temp = MIN_SET_TEMP    
        elif command == CommandID.NEW_SET_TEMP:
            self._desired_temp = data

        responses[self._ip] = FireplaceMessage.mock_response(command.expected_response,
                                    fire_on= self._is_on, fan_boost_on=self._fan_boost, effect_on=self._flame_effect,
                                    desired_temp=self._desired_temp, current_temp=self._current_temp)

        return responses

@pytest.mark.asyncio
async def test_controller_basics(mocker):

    discovery = DiscoveryService()
    device_uid = 1111
    device_ip = '192.168.0.111'

    fireplace = MockFireplaceInstance(device_ip)

    mocker.patch(
        'pescea.datagram.send_command',
        __name__ + '.MockeFireplaceInstance.send_command'
    )

    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()

    assert controller.device_ip == device_uid
    assert controller.device_uid == device_ip
    assert controller.discovery == discovery

    await controller.set_on(True)
    assert controller.is_on

    await controller.set_on(False)
    assert not controller.is_on

    for fan in range(Fan.value):
        await controller.set_fan(fan)
        assert controller.fan == fan

    for temp in range(int(controller.min_temp), int(controller.max_temp)):
        await controller.set_desired_temp(float(temp))
        assert int(controller.desired_temp) == temp

    assert controller.current_temp is not None

# @pytest.mark.asyncio
# async def test_controller_change_address():

#     discovery = DiscoveryService()
#     device_uid = 1111
#     device_ip = '192.168.0.111'

#     fireplace = MockFireplaceInstance(device_ip)

#     mocker.patch(
#         'pescea.datagram.send_command',
#         __name__ + '.MockeFireplaceInstance.send_command'
#     )

#     controller = Controller(discovery, device_uid, device_ip)
#     await controller.initialize()

#     assert controller.device_ip == device_uid
#     assert controller.device_uid == device_ip

#     await controller.refresh_address('192.168.0.222')
#     assert controller.device_ip == '192.168.0.222'
