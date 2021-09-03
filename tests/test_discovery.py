"""Test Escea discovery service module functionality """

from pytest import mark
from asyncio import sleep

from pescea.controller import Fan, State, Controller
from pescea.discovery import DiscoveryService

from .conftest import fireplaces, patched_open_datagram_endpoint


@mark.asyncio
async def test_service_basics(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    mocker.patch("pescea.discovery.DISCOVERY_SLEEP", 0.3)
    mocker.patch("pescea.discovery.DISCOVERY_RESCAN", 0.1)
    mocker.patch("pescea.controller.ON_OFF_BUSY_WAIT_TIME", 0.2)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_TIMEOUT", 0.3)
    mocker.patch("pescea.controller.DISCONNECTED_INTERVAL", 0.5)
    mocker.patch("pescea.datagram.REQUEST_TIMEOUT", 0.3)

    for f in fireplaces:
        fireplaces[f]["Responsive"] = True

    # Test steps:
    discovery = DiscoveryService()
    await discovery.start_discovery()

    await sleep(1.0)

    # check has fould all controlers
    assert len(discovery.controllers) == len(fireplaces)

    for c in discovery.controllers:
        ctrl = discovery.controllers[c]  # Type: Controller
        assert ctrl.state == State.READY
        assert ctrl.device_ip == fireplaces[ctrl.device_uid]["IPAddress"]
        assert ctrl.is_on == fireplaces[ctrl.device_uid]["FireIsOn"]
        if fireplaces[ctrl.device_uid]["FanBoost"]:
            assert ctrl.fan == Fan.FAN_BOOST
        elif fireplaces[ctrl.device_uid]["FlameEffect"]:
            assert ctrl.fan == Fan.FLAME_EFFECT
        else:
            assert ctrl.fan == Fan.AUTO
        assert ctrl.desired_temp == fireplaces[ctrl.device_uid]["DesiredTemp"]
        assert ctrl.current_temp == fireplaces[ctrl.device_uid]["CurrentTemp"]

    await sleep(0.5)
    # change values in background and check the polling picks it up
    for f in fireplaces:
        fireplaces[f]["CurrentTemp"] = 10.0

    await sleep(0.5)
    for ctrl in discovery.controllers:
        ctrl = discovery.controllers[c]  # Type: Controller
        assert ctrl.current_temp == fireplaces[ctrl.device_uid]["CurrentTemp"]

    await discovery.close()


@mark.asyncio
async def test_controller_updates(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    mocker.patch("pescea.discovery.DISCOVERY_SLEEP", 0.4)
    mocker.patch("pescea.discovery.DISCOVERY_RESCAN", 0.2)
    mocker.patch("pescea.controller.ON_OFF_BUSY_WAIT_TIME", 0.2)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_TIMEOUT", 0.3)
    mocker.patch("pescea.controller.DISCONNECTED_INTERVAL", 0.5)
    mocker.patch("pescea.datagram.REQUEST_TIMEOUT", 0.3)

    # Test steps:
    discovery = DiscoveryService()
    await discovery.start_discovery()

    await sleep(0.5)

    # check has fould all controlers
    assert len(discovery.controllers) == len(fireplaces)

    for c in discovery.controllers:
        ctrl = discovery.controllers[c]  # Type: Controller
        assert ctrl.state == State.READY

        assert ctrl.is_on == fireplaces[ctrl.device_uid]["FireIsOn"]
        await ctrl.set_on(not ctrl.is_on)
        assert ctrl.state == State.BUSY

        if ctrl.fan == Fan.FLAME_EFFECT:
            await ctrl.set_fan(Fan.AUTO)
        elif ctrl.fan == Fan.AUTO:
            await ctrl.set_fan(Fan.FAN_BOOST)
        else:
            await ctrl.set_fan(Fan.FLAME_EFFECT)

        await ctrl.set_desired_temp(ctrl.min_temp)

    await sleep(0.5)

    # change values in background and check the polling picks it up
    for f in fireplaces:
        fireplaces[f]["CurrentTemp"] = 10.0

    await sleep(0.5)

    for c in discovery.controllers:
        ctrl = discovery.controllers[c]  # Type: Controller
        assert ctrl.state == State.READY
        assert ctrl.device_ip == fireplaces[ctrl.device_uid]["IPAddress"]
        assert ctrl.is_on == fireplaces[ctrl.device_uid]["FireIsOn"]
        if fireplaces[ctrl.device_uid]["FanBoost"]:
            assert ctrl.fan == Fan.FAN_BOOST
        elif fireplaces[ctrl.device_uid]["FlameEffect"]:
            assert ctrl.fan == Fan.FLAME_EFFECT
        else:
            assert ctrl.fan == Fan.AUTO
        assert ctrl.desired_temp == fireplaces[ctrl.device_uid]["DesiredTemp"]
        assert ctrl.current_temp == fireplaces[ctrl.device_uid]["CurrentTemp"]

    await discovery.close()


@mark.asyncio
async def test_no_controllers_found(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    mocker.patch("pescea.controller.ON_OFF_BUSY_WAIT_TIME", 0.2)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_TIMEOUT", 0.3)
    mocker.patch("pescea.controller.DISCONNECTED_INTERVAL", 0.6)

    mocker.patch("pescea.discovery.DISCOVERY_SLEEP", 0.3)
    mocker.patch("pescea.discovery.DISCOVERY_RESCAN", 0.1)

    mocker.patch("pescea.datagram.REQUEST_TIMEOUT", 0.1)

    for f in fireplaces:
        fireplaces[f]["Responsive"] = False

    # Test steps:
    discovery = DiscoveryService()
    await discovery.start_discovery()

    await sleep(0.5)

    # check no controllers found
    assert len(discovery.controllers) == 0

    c_count = 0
    for f in fireplaces:
        fireplaces[f]["Responsive"] = True
        c_count += 1
        await sleep(0.5)
        # check controllers found again after a rescan
        assert len(discovery.controllers) == c_count

    fireplaces[next(iter(fireplaces))]["Responsive"] = False
    fireplaces[next(iter(fireplaces))]["IPAddress"] = "11.11.11.11"

    # controllers remain in the list, even after disconnected
    await sleep(0.3)
    assert len(discovery.controllers) == c_count

    await discovery.close()


@mark.asyncio
async def test_search_specific_ip(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    mocker.patch("pescea.controller.ON_OFF_BUSY_WAIT_TIME", 0.2)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_TIMEOUT", 0.3)
    mocker.patch("pescea.controller.DISCONNECTED_INTERVAL", 0.5)

    mocker.patch("pescea.discovery.DISCOVERY_SLEEP", 0.3)
    mocker.patch("pescea.discovery.DISCOVERY_RESCAN", 0.1)

    mocker.patch("pescea.datagram.REQUEST_TIMEOUT", 0.2)

    ip_address = fireplaces[next(iter(fireplaces))]["IPAddress"]
    fireplaces[next(iter(fireplaces))]["Responsive"] = True

    # Test steps:
    discovery = DiscoveryService(ip_addr=ip_address)
    await discovery.start_discovery()

    await sleep(0.5)

    # check only one matching controller found
    assert len(discovery.controllers) == 1

    await discovery.close()
