"""Test Escea connected to local network (skip unless have one available) """

from asyncio import Semaphore, sleep
from pytest import mark
from pprint import PrettyPrinter

from pescea.controller import Controller, ON_OFF_BUSY_WAIT_TIME
from pescea.discovery import Listener, discovery_service


@mark.skip
@mark.asyncio
async def test_live_fireplace(mocker):
    """Will only work on networks with real fireplaces"""

    # speed up the test a bit:

    mocker.patch("pescea.datagram.REQUEST_TIMEOUT", 2.0)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 10.0)
    mocker.patch("pescea.controller.NOTIFY_REFRESH_INTERVAL", 15.0)

    # Test steps
    class TestListener(Listener):
        def __init__(self):
            self.discoveries = Semaphore(value=0)
            self.disconnections = {}
            self.reconnections = {}
            self.updates = {}
            self.controllers = {}
            self.pp = PrettyPrinter(depth=4)

        def controller_discovered(self, ctrl: Controller):
            uid = ctrl.device_uid
            print("Controller discovered: ", uid)
            self.pp.pprint(ctrl._system_settings)
            self.disconnections[uid] = Semaphore(value=0)
            self.reconnections[uid] = Semaphore(value=0)
            self.updates[uid] = Semaphore(value=0)
            self.controllers[uid] = ctrl
            self.discoveries.release()

        def controller_disconnected(self, ctrl: Controller, ex):
            uid = ctrl.device_uid
            print("Controller disconnected: ", uid)
            self.pp.pprint(ctrl._system_settings)
            self.disconnections[uid].release()

        def controller_reconnected(self, ctrl: Controller):
            uid = ctrl.device_uid
            print("Controller reconnected: ", uid)
            self.pp.pprint(ctrl._system_settings)
            self.reconnections[uid].release()

        def controller_update(self, ctrl: Controller):
            uid = ctrl.device_uid
            print("Controller updated: ", uid)
            self.pp.pprint(ctrl._system_settings)
            self.updates[uid].release()

    listener = TestListener()

    async with discovery_service(listener):

        # Expect controller discovered calls, for each fireplace

        await listener.discoveries.acquire()

        for c in listener.controllers:
            ctrl = listener.controllers[c]  # Type: Controller
            uid = ctrl.device_uid

            await listener.updates[uid].acquire()

            assert ctrl.state == Controller.State.READY

            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            print("Requesting Turn On")
            # only play with an 'off' fireplace for testing
            await ctrl.set_on(True)
            # wait to start up
            await sleep(ON_OFF_BUSY_WAIT_TIME)

            # test still updating
            await listener.updates[uid].acquire()
            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            assert ctrl.is_on

            for fan in Controller.Fan:
                print("Requesting set Fan to: ", fan)
                await ctrl.set_fan(fan)
                await sleep(2.0)
                await listener.updates[uid].acquire()
                while not listener.updates[uid].locked():
                    await listener.updates[uid].acquire()

                assert ctrl.fan == fan

            print("Requesting desired temperature of: ", ctrl.min_temp)
            await ctrl.set_desired_temp(ctrl.min_temp)
            await sleep(2.0)
            await listener.updates[uid].acquire()
            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            assert int(ctrl.desired_temp) == int(ctrl.min_temp)

            print("Requesting desired temperature of: ", ctrl.max_temp)
            await ctrl.set_desired_temp(ctrl.max_temp)
            await sleep(2.0)
            await listener.updates[uid].acquire()
            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            assert int(ctrl.desired_temp) == int(ctrl.max_temp)

            # reset to reasonable values and turn off

            print("Requesting set Fan to: AUTO")
            await ctrl.set_fan(Controller.Fan.AUTO)
            await sleep(2.0)
            await listener.updates[uid].acquire()
            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            assert ctrl.fan == Controller.Fan.AUTO

            print("Requesting desired temperature of: ", 20.0)
            await ctrl.set_desired_temp(20.0)
            await sleep(2.0)
            await listener.updates[uid].acquire()
            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            assert int(ctrl.desired_temp) == 20

            print("Requesting Turn OFF")
            await ctrl.set_on(False)
            await sleep(ON_OFF_BUSY_WAIT_TIME)
            await listener.updates[uid].acquire()
            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            assert not ctrl.is_on
