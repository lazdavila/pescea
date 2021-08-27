"""Test UDP datagram functionality """
import asyncio
import pytest
from pytest import mark

from asyncio.transports import DatagramTransport
 
from pescea.datagram import FireplaceDatagram
from pescea.message import MIN_SET_TEMP, CommandID

from .conftest import fireplaces, \
                      simulate_comms_timeout_error, simulate_comms_connection_error, \
                      patched_create_datagram_endpoint

@mark.asyncio
async def test_search_for_fires(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )

    event_loop = asyncio.get_event_loop()
    datagram = FireplaceDatagram(event_loop, device_ip= '255.255.255.255')

    # Test step:
    responses = await datagram.send_command(command = CommandID.SEARCH_FOR_FIRES, broadcast=True)

    assert len(responses) == 3
    for addr in responses:
        serial_number = responses[addr].serial_number
        assert fireplaces[serial_number]["IPAddress"] == addr

@mark.asyncio
async def test_get_status(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )

    event_loop = asyncio.get_event_loop()
    uid = list(fireplaces.keys())[0]
    datagram = FireplaceDatagram(event_loop, device_ip= fireplaces[uid]["IPAddress"])

    # Test step:
    responses = await datagram.send_command(command = CommandID.STATUS_PLEASE)

    assert len(responses) == 1
    assert responses[fireplaces[uid]["IPAddress"]].fire_is_on == fireplaces[uid]["FireIsOn"]
    assert responses[fireplaces[uid]["IPAddress"]].desired_temp == fireplaces[uid]["DesiredTemp"]

@mark.asyncio
async def test_timeout_error(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )

    mocker.patch(
        'tests.conftest.simulate_comms_patchable',
        simulate_comms_timeout_error
    )

    event_loop = asyncio.get_event_loop()
    uid = list(fireplaces.keys())[0]

    # Test step:
    datagram = FireplaceDatagram(event_loop, device_ip= fireplaces[uid]["IPAddress"])

    with pytest.raises(asyncio.TimeoutError):
        responses = await datagram.send_command(command = CommandID.STATUS_PLEASE)
    event_loop.stop()

 
@pytest.mark.asyncio
async def test_connection_error(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )

    mocker.patch(
        'tests.conftest.simulate_comms_patchable',
        simulate_comms_connection_error
    )

    event_loop = asyncio.get_event_loop()
    uid = list(fireplaces.keys())[0]

    # Test step:
    datagram = FireplaceDatagram(event_loop, device_ip= fireplaces[uid]["IPAddress"])

    responses = await datagram.send_command(command = CommandID.STATUS_PLEASE)
    assert len(responses) == 0
