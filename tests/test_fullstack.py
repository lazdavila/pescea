"""Test for controller"""

from asyncio import Event
from pescea import Controller, Listener, discovery
from pytest import raises, mark


async def test_full_stack(event_loop):
    controllers = []
    event = Event()

    class TestListener(Listener):
        def controller_discovered(self, _ctrl):
            controllers.append(_ctrl)
            event.set()

        def controller_reconnected(self, ctrl):
            event.set()
    listener = TestListener()

    async with discovery(listener):
        await event.wait()
        event.clear()

        ctrl = controllers[0]  # type Controller()

        ctrl.dump()

        # test setting values
        await ctrl.set_mode(Controller.Mode.AUTO)

        Controller.CONNECT_RETRY_TIMEOUT = 2

        ctrl._ip = 'bababa'  # pylint: disable=protected-access
        with raises(ConnectionError):
            await ctrl.set_sleep_timer(30)

        # Should reconnect here
        await event.wait()
        event.clear()

        await ctrl.set_mode(Controller.Mode.HEAT)

        ctrl.dump()
