"""Test Escea controller module functionality """
from pytest import mark
import asyncio
from asyncio import sleep

from pescea.controller import Controller
from pescea.discovery import DiscoveryService

from .conftest import fireplaces, patched_open_datagram_endpoint


@mark.asyncio
async def test_controller_basics(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    mocker.patch("pescea.controller.ON_OFF_BUSY_WAIT_TIME", 0.2)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_TIMEOUT", 0.3)
    mocker.patch("pescea.controller.DISCONNECTED_INTERVAL", 0.5)

    discovery = DiscoveryService()
    device_uid = list(fireplaces.keys())[0]
    device_ip = fireplaces[device_uid]["IPAddress"]

    # Test steps:
    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()

    assert controller.device_ip == device_ip
    assert controller.device_uid == device_uid
    assert controller.discovery == discovery
    assert controller.state == Controller.State.READY

    was_on = controller.is_on
    await controller.set_on(False)
    if was_on:
        # Should still be BUSY waiting
        assert controller.state == Controller.State.BUSY
        assert not controller.is_on
        await sleep(0.5)
        assert controller.state == Controller.State.READY

    assert not controller.is_on

    await controller.set_on(True)
    # Should again be BUSY waiting
    assert controller.state == Controller.State.BUSY
    assert controller.is_on

    await sleep(0.5)
    assert controller.state == Controller.State.READY
    assert controller.is_on

    desired_temp = int(controller.desired_temp)

    # Test all Fan transitions
    for from_fan in Controller.Fan:
        for to_fan in Controller.Fan:
            await controller.set_fan(from_fan)
            assert controller.fan == from_fan
            assert controller.state == Controller.State.READY
            # Check no unexpected side effects
            assert controller.is_on
            assert desired_temp == int(controller.desired_temp)

            await controller.set_fan(to_fan)
            assert controller.fan == to_fan
            assert controller.state == Controller.State.READY
            # Check no unexpected side effects
            assert controller.is_on
            assert desired_temp == int(controller.desired_temp)

    fan = controller.fan

    for temp in range(int(controller.min_temp), int(controller.max_temp)):
        await controller.set_desired_temp(float(temp))
        assert int(controller.desired_temp) == temp
        assert controller.state == Controller.State.READY
        # Check no unexpected side effects
        assert controller.is_on
        assert controller.fan == fan

    assert controller.current_temp is not None

    # Teardown:
    await controller.set_on(False)
    await controller.set_fan(Controller.Fan.AUTO)
    await controller.close()
    await sleep(0.2)
    asyncio.gather(*asyncio.all_tasks())


@mark.asyncio
async def test_controller_change_address(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    mocker.patch("pescea.controller.ON_OFF_BUSY_WAIT_TIME", 0.2)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_TIMEOUT", 0.3)
    mocker.patch("pescea.controller.DISCONNECTED_INTERVAL", 0.5)

    mocker.patch("pescea.datagram.REQUEST_TIMEOUT", 0.3)

    discovery = DiscoveryService()
    device_uid = list(fireplaces.keys())[0]
    device_ip = fireplaces[device_uid]["IPAddress"]

    # Test steps:
    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()

    assert controller.device_ip == device_ip
    assert controller.device_uid == device_uid
    assert controller.discovery == discovery
    assert controller.state == Controller.State.READY

    new_ip = "10.10.10.10"
    fireplaces[device_uid]["IPAddress"] = new_ip

    await sleep(0.8)
    assert controller.state == Controller.State.DISCONNECTED

    controller.refresh_address(new_ip)

    # Allow time to poll for status and check still get response
    await sleep(0.3)
    assert controller.state == Controller.State.READY
    assert controller.device_ip == new_ip

    # Teardown:
    await controller.close()
    await sleep(0.2)
    asyncio.gather(*asyncio.all_tasks())


@mark.asyncio
async def test_controller_poll(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    mocker.patch("pescea.controller.ON_OFF_BUSY_WAIT_TIME", 0.2)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_TIMEOUT", 0.3)
    mocker.patch("pescea.controller.DISCONNECTED_INTERVAL", 0.5)

    discovery = DiscoveryService()
    device_uid = list(fireplaces.keys())[0]
    device_ip = fireplaces[device_uid]["IPAddress"]

    # Test steps:
    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()

    assert controller.device_ip == device_ip
    assert controller.device_uid == device_uid
    assert controller.discovery == discovery
    assert controller.state == Controller.State.READY

    was_on = controller.is_on
    await controller.set_on(True)
    if not was_on:
        # Should still be BUSY waiting
        assert controller.state == Controller.State.BUSY
        assert controller.is_on  # Saved, but not yet committed
        await sleep(0.5)
        assert controller.state == Controller.State.READY

    assert controller.is_on

    # Change in the backend what our more fireplace returns
    fireplaces[device_uid]["FireIsOn"] = False

    await sleep(0.2)
    # Check the poll command has read the changed status
    assert not controller.is_on

    # Teardown:
    await controller.close()
    await sleep(0.2)
    asyncio.gather(*asyncio.all_tasks())


@mark.asyncio
async def test_controller_disconnect_reconnect(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    mocker.patch("pescea.controller.ON_OFF_BUSY_WAIT_TIME", 0.2)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_TIMEOUT", 0.2)
    mocker.patch("pescea.controller.DISCONNECTED_INTERVAL", 0.4)
    mocker.patch("pescea.datagram.REQUEST_TIMEOUT", 0.1)

    discovery = DiscoveryService()
    device_uid = list(fireplaces.keys())[0]
    device_ip = fireplaces[device_uid]["IPAddress"]

    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()
    assert controller.device_ip == device_ip
    assert controller.state == Controller.State.READY

    fireplaces[device_uid]["Responsive"] = False

    await sleep(0.2)
    assert controller.state == Controller.State.NON_RESPONSIVE

    await sleep(0.3)
    assert controller.state == Controller.State.DISCONNECTED

    new_ip = fireplaces[list(fireplaces.keys())[-1]]["IPAddress"]
    controller.refresh_address(new_ip)
    assert controller.device_ip == new_ip

    fireplaces[device_uid]["Responsive"] = True
    await sleep(0.6)

    assert controller.state == Controller.State.READY

    # clean shutdown
    await controller.close()
    await sleep(0.6)
    asyncio.gather(*asyncio.all_tasks())


@mark.asyncio
async def test_controller_updates_while_busy(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    mocker.patch("pescea.controller.ON_OFF_BUSY_WAIT_TIME", 0.9)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_TIMEOUT", 0.3)
    mocker.patch("pescea.controller.DISCONNECTED_INTERVAL", 0.8)

    discovery = DiscoveryService()
    device_uid = list(fireplaces.keys())[0]
    device_ip = fireplaces[device_uid]["IPAddress"]

    # Test steps:
    controller = Controller(discovery, device_uid, device_ip)
    await controller.initialize()

    assert controller.device_ip == device_ip
    assert controller.device_uid == device_uid
    assert controller.discovery == discovery
    assert controller.state == Controller.State.READY

    desired_temp = int(controller.desired_temp)
    fan = controller.fan

    if controller.is_on:
        await controller.set_on(False)
        await 1.0

    assert not controller.is_on
    await controller.set_on(True)

    # Test changes while busy and make sure they stick
    assert controller.state == Controller.State.BUSY
    assert int(controller.desired_temp) == desired_temp
    assert controller.fan == fan

    # Test all Fan transitions
    for from_fan in Controller.Fan:
        for to_fan in Controller.Fan:
            await controller.set_fan(from_fan)
            assert controller.fan == from_fan

            # Check no unexpected side effects
            assert controller.state == Controller.State.BUSY
            assert controller.is_on
            assert desired_temp == int(controller.desired_temp)

            await controller.set_fan(to_fan)
            assert controller.fan == to_fan

            # Check no unexpected side effects
            assert controller.state == Controller.State.BUSY
            assert controller.is_on
            assert desired_temp == int(controller.desired_temp)

    fan = controller.fan

    for temp in range(int(controller.min_temp), int(controller.max_temp) + 1):
        await controller.set_desired_temp(float(temp))
        assert int(controller.desired_temp) == temp

        # Check no unexpected side effects
        assert controller.state == Controller.State.BUSY
        assert controller.is_on
        assert controller.fan == fan

    await sleep(1.0)
    # Check values still stick
    assert controller.state == Controller.State.READY
    assert controller.is_on
    assert controller.fan == fan
    assert int(controller.desired_temp) == controller.max_temp

    # Teardown:
    await controller.set_on(False)
    await controller.set_fan(Controller.Fan.AUTO)
    await sleep(1.0)
    await controller.close()
    await sleep(0.2)
    asyncio.gather(*asyncio.all_tasks())
