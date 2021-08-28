"""Test Escea discovery service module functionality """
import asyncio
import pytest
from pytest import mark

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

    # grab service

    # check has searched for fireplaces

    # check has three fireplaces

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


async def test_controller_updates(mocker):
    # grab service

    # attempt to control each controller

    # shut down each controller
    pass

async def test_no_controllers_found(mocker):
    # grab service

    # check has searched for fireplaces

    # check has three fireplaces

    # attempt to control each controller

    # shut down each controller
    pass


async def test_controller_disconnection(mocker):
    # grab service

    # check has searched for fireplaces

    # check has three fireplaces

    # attempt to control each controller

    # shut down each controller
    pass
