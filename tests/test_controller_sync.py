"""Regression tests: a missed status reply must not replay stale settings."""
from pytest import fixture, mark

from pescea.controller import Controller
from pescea.discovery import DiscoveryService
from pescea.message import CommandID

from . import conftest
from .conftest import patched_open_datagram_endpoint

UID = 2222  # starts on, flame effect, 24 degrees


@fixture
def sent(mocker):
    """Record every command the controller sends."""
    commands = []
    original = conftest.SimulatedComms.send

    def record(self, data):
        original(self, data)
        commands.append(self.command.command_id)

    mocker.patch.object(conftest.SimulatedComms, "send", record)
    return commands


@fixture
def patched(mocker):
    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )
    mocker.patch("pescea.controller.ON_OFF_BUSY_WAIT_TIME", 0.2)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 60)
    mocker.patch("pescea.controller.RETRY_INTERVAL", 60)
    mocker.patch("pescea.controller.RETRY_TIMEOUT", 600)
    mocker.patch("pescea.controller.DISCONNECTED_INTERVAL", 60)
    mocker.patch("pescea.datagram.REQUEST_TIMEOUT", 0.2)
    fire = conftest.fireplaces[UID]
    saved = dict(fire)
    yield fire
    fire.clear()
    fire.update(saved)


async def _controller():
    controller = Controller(DiscoveryService(), UID, conftest.fireplaces[UID]["IPAddress"])
    await controller.initialize()
    return controller


@mark.asyncio
async def test_missed_status_does_not_relight_fire(patched, sent):
    """The fire is turned off with the app while one status reply is lost.

    The next good status must be adopted, and POWER_ON must never be sent.
    """
    fire = patched
    controller = await _controller()
    assert controller.is_on
    assert controller.state == Controller.State.READY

    fire["Responsive"] = False
    await controller._refresh_system()
    assert controller.state == Controller.State.NON_RESPONSIVE

    # Turned off, flame effect off and a new temperature, from the Escea app.
    fire["FireIsOn"] = False
    fire["FlameEffect"] = False
    fire["DesiredTemp"] = 18.0
    fire["Responsive"] = True
    sent.clear()

    await controller._refresh_system()

    assert controller.state == Controller.State.READY
    assert set(sent) == {CommandID.STATUS_PLEASE}  # only reads, nothing replayed
    assert fire["FireIsOn"] is False
    assert not controller.is_on
    assert controller.desired_temp == 18.0
    assert controller.fan == Controller.Fan.AUTO
    await controller.close()


@mark.asyncio
async def test_reconnect_after_disconnect_adopts_fire_state(patched, sent):
    """A fire last seen on, back after a long outage while off, stays off."""
    fire = patched
    controller = await _controller()

    fire["Responsive"] = False
    await controller._refresh_system()
    controller._last_response = 0  # long ago
    await controller._refresh_system()
    assert controller.state == Controller.State.DISCONNECTED

    fire["FireIsOn"] = False
    fire["Responsive"] = True
    sent.clear()
    await controller._refresh_system()

    assert CommandID.POWER_ON not in sent
    assert fire["FireIsOn"] is False
    assert not controller.is_on
    await controller.close()


@mark.asyncio
async def test_setting_changed_while_unreachable_is_still_sent(patched, sent):
    """A temperature set here while the fire didn't answer is sent on return."""
    fire = patched
    controller = await _controller()

    fire["Responsive"] = False
    await controller._refresh_system()
    assert controller.state == Controller.State.NON_RESPONSIVE

    await controller.set_desired_temp(21)
    assert fire["DesiredTemp"] == 24.0  # not sent yet

    fire["Responsive"] = True
    await controller._refresh_system()

    assert fire["DesiredTemp"] == 21
    assert fire["FireIsOn"] is True
    assert CommandID.POWER_ON not in sent
    await controller.close()
