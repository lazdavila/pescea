"""Test UDP datagram functionality """
import asyncio

import pytest
from pytest import mark

from pescea.datagram import Datagram
from pescea.message import CommandID

from .conftest import fireplaces, patched_open_datagram_endpoint


@mark.asyncio
async def test_search_for_fires(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    event_loop = asyncio.get_event_loop()
    datagram = Datagram(
        event_loop,
        device_ip="255.255.255.255",
        sending_lock=asyncio.Lock(),
    )

    # Test steps:
    responses = await datagram.send_command(CommandID.SEARCH_FOR_FIRES)

    assert len(responses) == 3
    for addr in responses:
        serial_number = responses[addr].serial_number
        assert fireplaces[serial_number]["IPAddress"] == addr

    # Teardown:
    asyncio.gather(*asyncio.all_tasks())


@mark.asyncio
async def test_get_status(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    event_loop = asyncio.get_event_loop()
    uid = list(fireplaces.keys())[0]
    datagram = Datagram(
        event_loop,
        device_ip=fireplaces[uid]["IPAddress"],
        sending_lock=asyncio.Lock(),
    )

    # Test steps:
    responses = await datagram.send_command(CommandID.STATUS_PLEASE)

    assert len(responses) == 1
    assert (
        responses[fireplaces[uid]["IPAddress"]].fire_is_on
        == fireplaces[uid]["FireIsOn"]
    )
    assert (
        responses[fireplaces[uid]["IPAddress"]].desired_temp
        == fireplaces[uid]["DesiredTemp"]
    )

    # Teardown:
    asyncio.gather(*asyncio.all_tasks())


@mark.asyncio
async def test_timeout_error(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    mocker.patch("pescea.datagram.REQUEST_TIMEOUT", 0.3)

    event_loop = asyncio.get_event_loop()
    uid = list(fireplaces.keys())[0]
    datagram = Datagram(
        event_loop,
        device_ip=fireplaces[uid]["IPAddress"],
        sending_lock=asyncio.Lock(),
    )
    fireplaces[uid]["Responsive"] = False

    # Test steps:
    with pytest.raises(ConnectionError):
        responses = await datagram.send_command(CommandID.STATUS_PLEASE)

    # Teardown6
    fireplaces[uid]["Reponsive"] = True
    asyncio.gather(*asyncio.all_tasks())
