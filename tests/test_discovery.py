import pytest

from asynctest.mock import patch
from asyncio import sleep

from pescea import discovery, Controller, Listener
from pescea.discovery import DiscoveryService
from pescea.message import FireplaceMessage

from pytest import raises

from .resources import fireplaces

@pytest.mark.asyncio
@patch.object(DiscoveryService, '_send_broadcast')
async def test_broadcasts_sent(send):
    async with discovery():
        assert send.called


@pytest.mark.asyncio
@patch.object(DiscoveryService, '_send_broadcast')
async def test_rescan(send):
    async with discovery() as service:
        assert not service.is_closed
        assert send.call_count == 1

        await service.rescan()
        await sleep(0)
        assert send.call_count == 2

    assert service.is_closed


@pytest.mark.asyncio
async def test_fail_on_connect(event_loop, caplog):
    from .conftest import MockDiscoveryService

    service = MockDiscoveryService(event_loop)
    service.connected = False

    async with service:
        # TODO: Figure out how to stub this / how would it work now?
        service._datagram.process_received(None, '1.1.1.1')
        await sleep(0)
        await sleep(0)

    assert len(caplog.messages) == 1
    assert caplog.messages[0][:41] == \
        "Can't connect to discovered server at IP "
    assert not service.controllers


@pytest.mark.asyncio
async def test_connection_lost(service, caplog):
    service.connection_lost(IOError("Nonspecific"))
    await sleep(0)

    assert len(caplog.messages) == 1
    assert caplog.messages[0] == \
        "Connection Lost unexpectedly: OSError('Nonspecific')"

    assert service.is_closed


@pytest.mark.asyncio
async def test_discovery(service: DiscoveryService):
    assert len(service.controllers) == len(fireplaces)

    for ctl_uid in list(fireplaces.keys()):

        assert ctl_uid in service.controllers
        controller = service.controllers[ctl_uid]  # type: Controller

        # Check system settings are update on init
        assert controller._system_settings[Controller.DictEntries.DEVICE_UID] == ctl_uid
        assert controller._system_settings[Controller.DictEntries.IP_ADDRESS] == fireplaces[ctl_uid]["IPAddress"]
        assert controller._system_settings[Controller.DictEntries.HAS_NEW_TIMERS] == fireplaces[ctl_uid]["HasNewTimers"]
        assert controller._system_settings[Controller.DictEntries.FIRE_IS_ON] == fireplaces[ctl_uid]["FireIsOn"]
        assert controller._system_settings[Controller.DictEntries.FAN_MODE] == fireplaces[ctl_uid]["FanMode"]
        assert controller._system_settings[Controller.DictEntries.DESIRED_TEMP] == fireplaces[ctl_uid]["DesiredTemp"]
        assert controller._system_settings[Controller.DictEntries.CURRENT_TEMP] == fireplaces[ctl_uid]["CurrentTemp"]

        # check properties work
        assert controller.device_ip == fireplaces[ctl_uid]["IPAddress"]
        assert controller.device_uid == ctl_uid
        assert controller.is_on == fireplaces[ctl_uid]["FireIsOn"]
        assert controller.fan == fireplaces[ctl_uid]["FanMode"]
        assert controller.desired_temp == fireplaces[ctl_uid]["DesiredTemp"]
        assert controller.current_temp == fireplaces[ctl_uid]["CurrentTemp"]
        assert controller.min_temp == FireplaceMessage.MIN_SET_TEMP
        assert controller.max_temp == FireplaceMessage.MAX_SET_TEMP

        # check the methods

        await controller.set_on(not controller.is_on)
        assert controller.is_on != fireplaces[ctl_uid]["FireIsOn"]

        for fan_mode in Controller.Fan:
            await controller.set_fan(fan_mode)
            assert controller.fan == fan_mode

        for desired_temp in range(int(controller.min_temp), int(controller.max_temp)):
            await controller.set_desired_temp(float(desired_temp))
            assert int(controller.desired_temp) == desired_temp

        for test_addr in '1.1.1.1', '2.2.2.2', '3.3.3.3':
            await controller._refresh_address(test_addr)
            assert controller.device_ip == test_addr

        # set settings back to test case values
        await controller.set_on(fireplaces[ctl_uid]["FireIsOn"])
        assert controller.is_on == fireplaces[ctl_uid]["FireIsOn"]

        await controller.set_fan(fireplaces[ctl_uid]["FanMode"])
        assert controller.fan == fireplaces[ctl_uid]["FanMode"]

        await controller.set_desired_temp(fireplaces[ctl_uid]["DesiredTemp"])
        assert controller.desired_temp == fireplaces[ctl_uid]["DesiredTemp"]

        await controller._refresh_address(fireplaces[ctl_uid]["IPAddress"])
        assert controller.device_ip == fireplaces[ctl_uid]["IPAddress"]


@pytest.mark.asyncio
async def test_ip_addr_change(service: DiscoveryService, caplog):
    assert len(service.controllers) == len(fireplaces)

    for ctl_uid in list(fireplaces.keys()):

        assert ctl_uid in service.controllers
        controller = service.controllers[ctl_uid]  # type: Controller

        assert controller._system_settings[Controller.DictEntries.DEVICE_UID] == ctl_uid
        assert controller._system_settings[Controller.DictEntries.IP_ADDRESS] == fireplaces[ctl_uid]["IPAddress"]

        for test_addr in '1.1.1.1', '2.2.2.2', '3.3.3.3':

            # TODO: How to patch response so the address is changed
            service._datagram.process_received(FireplaceMessage.dummy_response(
                FireplaceMessage.ResponseID.I_AM_A_FIRE, uid=ctl_uid), test_addr)
            await sleep(0)

            assert controller.device_ip == test_addr


@pytest.mark.asyncio
async def test_reconnect(service, caplog):
    controller = service.controllers['000000001']  # type: Controller
    assert controller.device_uid == '000000001'
    assert controller.power_on == True

    controller.connected = False

    assert caplog.messages[0][:30] == \
        "Connection to fireplace lost:"
    assert not controller.sent

    controller.connected = True
    service._process_datagram(
        b'ASPort_12107,Mac_000000001,0000011234',
        ('8.8.8.8', 3300))

    await sleep(0.1)

    # Reconnect OK
    assert caplog.messages[1][:23] == \
        "Fireplace reconnected:"
    await controller.power_on == True


@pytest.mark.asyncio
async def test_reconnect_listener(service):
    controller = service.controllers['000000001']  # type: Controller

    calls = []

    class TestListener(Listener):
        def controller_discovered(self, ctrl: Controller) -> None:
            calls.append(('discovered', ctrl))

        def controller_disconnected(
                self, ctrl: Controller, ex: Exception) -> None:
            calls.append(('disconnected', ctrl, ex))

        def controller_reconnected(self, ctrl: Controller) -> None:
            calls.append(('reconnected', ctrl))
    listener = TestListener()

    service.add_listener(listener)
    await sleep(0)

    assert len(calls) == 1
    assert calls[-1] == ('discovered', controller)

    controller.connected = False
    with raises(ConnectionError):
        await controller.set_mode(Controller.Mode.COOL)

    assert len(calls) == 2
    assert calls[-1][0:2] == ('disconnected', controller)

    controller.connected = True
    service._process_datagram(
        b'ASPort_12107,Mac_000000001,IP_8.8.8.8,Escea,iLight,iDrate',
        ('8.8.8.8', 12107))
    await sleep(0.1)

    assert len(calls) == 3
    assert calls[-1] == ('reconnected', controller)

    service._process_datagram(
        b'ASPort_12107,Mac_000000002,IP_8.8.8.4,Escea,iLight,iDrate',
        ('8.8.8.8', 12107))
    await sleep(0.1)
    controller2 = service.controllers['000000002']  # type: Controller

    assert len(calls) == 4
    assert calls[-1] == ('discovered', controller2)

    service.remove_listener(listener)

    controller.connected = False
    with raises(ConnectionError):
        await controller.set_mode(Controller.Mode.COOL)

    assert len(calls) == 4
