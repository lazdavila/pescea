"""Test Escea discovery service, controller and listeners"""

from asyncio import Semaphore, sleep
from datetime import datetime
from pytest import mark

from pescea.controller import Controller
from pescea.discovery import Listener, discovery_service

from .conftest import fireplaces, patched_open_datagram_endpoint


@mark.asyncio
async def test_full_stack(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    mocker.patch("pescea.discovery.DISCOVERY_SLEEP", 0.4)
    mocker.patch("pescea.discovery.DISCOVERY_RESCAN", 0.2)
    mocker.patch("pescea.controller.ON_OFF_BUSY_WAIT_TIME", 0.5)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_TIMEOUT", 0.3)
    mocker.patch("pescea.controller.DISCONNECTED_INTERVAL", 0.5)
    mocker.patch("pescea.controller.NOTIFY_REFRESH_INTERVAL", 0.3)
    mocker.patch("pescea.datagram.REQUEST_TIMEOUT", 0.2)

    for f in fireplaces:
        fireplaces[f]["Responsive"] = True

    # Test steps:
    class TestListener(Listener):
        def __init__(self):
            self.controllers = {}
            self.discoveries = {}
            self.disconnections = {}
            self.reconnections = {}
            self.updates = {}

            for f in fireplaces:
                self.discoveries[f] = Semaphore(value=0)
                self.disconnections[f] = Semaphore(value=0)
                self.reconnections[f] = Semaphore(value=0)
                self.updates[f] = Semaphore(value=0)

        def controller_discovered(self, ctrl: Controller):
            print(datetime.now().time(), " Controller discovered: ", ctrl.device_uid)
            self.controllers[ctrl.device_uid] = ctrl
            self.discoveries[ctrl.device_uid].release()

        def controller_disconnected(self, ctrl: Controller, ex):
            print(datetime.now().time(), " Controller disconnected: ", ctrl.device_uid)
            self.disconnections[ctrl.device_uid].release()

        def controller_reconnected(self, ctrl: Controller):
            print(datetime.now().time(), " Controller reconnected: ", ctrl.device_uid)
            self.reconnections[ctrl.device_uid].release()

        def controller_update(self, ctrl: Controller):
            print(datetime.now().time(), " Controller updated: {0}", ctrl.device_uid)
            self.updates[ctrl.device_uid].release()

    listener = TestListener()

    async with discovery_service(listener):

        # Expect controller discovered calls, for each fireplace

        for uid in fireplaces:
            await listener.discoveries[uid].acquire()
            await listener.updates[uid].acquire()

        for c in listener.controllers:
            ctrl = listener.controllers[c]  # Type: Controller
            uid = ctrl.device_uid

            assert ctrl.state == Controller.State.READY

            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            # test toggling power
            new_on = not ctrl.is_on
            await ctrl.set_on(new_on)
            await sleep(0.05)

            # test still updating
            await listener.updates[uid].acquire()
            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            assert ctrl.state == Controller.State.BUSY
            await sleep(0.6)

            assert ctrl.state == Controller.State.READY
            assert ctrl.is_on == new_on

            await ctrl.set_on(True)
            await sleep(0.6)
            await listener.updates[uid].acquire()
            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            for fan in Controller.Fan:
                await ctrl.set_fan(fan)

                # test still updating
                await listener.updates[uid].acquire()
                while not listener.updates[uid].locked():
                    await listener.updates[uid].acquire()

                assert ctrl.fan == fan
                assert ctrl.is_on

            # test fireplace non-responsive
            fireplaces[ctrl.device_uid]["Responsive"] = False
            await sleep(0.3)
            # check not getting any more updates
            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()
            await sleep(0.3)
            assert listener.updates[uid].locked()

            await listener.disconnections[ctrl.device_uid].acquire()
            assert ctrl.state == Controller.State.DISCONNECTED
            assert listener.updates[uid].locked()

            # test scan and IP address change
            new_ip = "10.10.10." + str(ctrl.device_uid % 256)
            fireplaces[ctrl.device_uid]["IPAddress"] = new_ip
            fireplaces[ctrl.device_uid]["Responsive"] = True

            await listener.reconnections[ctrl.device_uid].acquire()
            assert ctrl.state == Controller.State.READY
            assert ctrl.device_ip == new_ip
            await listener.updates[uid].acquire()


@mark.asyncio
async def test_multiple_listeners(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    mocker.patch("pescea.discovery.DISCOVERY_SLEEP", 0.4)
    mocker.patch("pescea.discovery.DISCOVERY_RESCAN", 0.2)
    mocker.patch("pescea.controller.ON_OFF_BUSY_WAIT_TIME", 0.5)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_TIMEOUT", 0.3)
    mocker.patch("pescea.controller.DISCONNECTED_INTERVAL", 0.5)
    mocker.patch("pescea.controller.NOTIFY_REFRESH_INTERVAL", 0.3)
    mocker.patch("pescea.datagram.REQUEST_TIMEOUT", 0.2)

    mocker.patch("pescea.datagram.REQUEST_TIMEOUT", 0.5)

    for f in fireplaces:
        fireplaces[f]["Responsive"] = True

    # Test steps:
    class TestListener(Listener):
        def __init__(self):
            self.controllers = {}
            self.discoveries = {}
            self.disconnections = {}
            self.reconnections = {}
            self.updates = {}

            for f in fireplaces:
                self.discoveries[f] = Semaphore(value=0)
                self.disconnections[f] = Semaphore(value=0)
                self.reconnections[f] = Semaphore(value=0)
                self.updates[f] = Semaphore(value=0)

        def controller_discovered(self, ctrl: Controller):
            print(datetime.now().time(), " Controller discovered: ", ctrl.device_uid)
            self.controllers[ctrl.device_uid] = ctrl
            self.discoveries[ctrl.device_uid].release()

        def controller_disconnected(self, ctrl: Controller, ex):
            print(datetime.now().time(), " Controller disconnected: ", ctrl.device_uid)
            self.disconnections[ctrl.device_uid].release()

        def controller_reconnected(self, ctrl: Controller):
            print(datetime.now().time(), " Controller reconnected: ", ctrl.device_uid)
            self.reconnections[ctrl.device_uid].release()

        def controller_update(self, ctrl: Controller):
            print(datetime.now().time(), " Controller updated: ", ctrl.device_uid)
            self.updates[ctrl.device_uid].release()

    listeners = {}

    for i in range(3):
        listeners[i] = TestListener()

    async with discovery_service(listeners[0]) as disco:

        for i in range(1, 3):
            await sleep(0.1)
            disco.add_listener(listeners[i])

        for uid in fireplaces:
            for l in listeners:
                # check every listener found about every controller
                # irrespective of when it was added
                lstner = listeners[l]
                await lstner.discoveries[uid].acquire()
                await lstner.updates[uid].acquire()
                assert len(lstner.controllers) == 3

        # test fireplace non-responsive
        fplace = next(iter(fireplaces))
        fireplaces[fplace]["Responsive"] = False

        for l in listeners:
            # check not getting any more updates
            lstner = listeners[l]
            while not lstner.updates[fplace].locked():
                await lstner.updates[fplace].acquire()
            await sleep(0.3)
            assert lstner.updates[fplace].locked()

            await lstner.disconnections[fplace].acquire()

        # test scan and IP address change
        new_ip = "10.10.10." + str(fplace % 256)
        fireplaces[fplace]["IPAddress"] = new_ip
        fireplaces[fplace]["Responsive"] = True

        for l in listeners:
            # check notified reconnection
            lstner = listeners[l]
            await lstner.reconnections[fplace].acquire()
            await lstner.updates[fplace].acquire()


@mark.asyncio
async def test_updates_while_busy(mocker):

    mocker.patch(
        "pescea.udp_endpoints.open_datagram_endpoint", patched_open_datagram_endpoint
    )

    mocker.patch("pescea.discovery.DISCOVERY_SLEEP", 0.4)
    mocker.patch("pescea.discovery.DISCOVERY_RESCAN", 0.2)
    mocker.patch("pescea.controller.ON_OFF_BUSY_WAIT_TIME", 1.2)
    mocker.patch("pescea.controller.REFRESH_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_INTERVAL", 0.1)
    mocker.patch("pescea.controller.RETRY_TIMEOUT", 0.3)
    mocker.patch("pescea.controller.DISCONNECTED_INTERVAL", 1.6)
    mocker.patch("pescea.controller.NOTIFY_REFRESH_INTERVAL", 0.2)
    mocker.patch("pescea.datagram.REQUEST_TIMEOUT", 0.2)

    for f in fireplaces:
        fireplaces[f]["Responsive"] = True

    # Test steps:
    class TestListener(Listener):
        def __init__(self):
            self.controllers = {}
            self.discoveries = {}
            self.disconnections = {}
            self.reconnections = {}
            self.updates = {}

            for f in fireplaces:
                self.discoveries[f] = Semaphore(value=0)
                self.disconnections[f] = Semaphore(value=0)
                self.reconnections[f] = Semaphore(value=0)
                self.updates[f] = Semaphore(value=0)

        def controller_discovered(self, ctrl: Controller):
            print(datetime.now().time(), " Controller discovered: ", ctrl.device_uid)
            self.controllers[ctrl.device_uid] = ctrl
            self.discoveries[ctrl.device_uid].release()

        def controller_disconnected(self, ctrl: Controller, ex):
            print(datetime.now().time(), " Controller disconnected: ", ctrl.device_uid)
            self.disconnections[ctrl.device_uid].release()

        def controller_reconnected(self, ctrl: Controller):
            print(datetime.now().time(), " Controller reconnected: ", ctrl.device_uid)
            self.reconnections[ctrl.device_uid].release()

        def controller_update(self, ctrl: Controller):
            print(datetime.now().time(), " Controller updated: ", ctrl.device_uid)
            self.updates[ctrl.device_uid].release()

    listener = TestListener()

    async with discovery_service(listener):

        # Expect controller discovered calls, for each fireplace

        for uid in fireplaces:
            await listener.discoveries[uid].acquire()
            await listener.updates[uid].acquire()

        for c in listener.controllers:
            ctrl = listener.controllers[c]  # Type: Controller
            uid = ctrl.device_uid

            print(datetime.now().time(), " Testing controller: ", uid)

            assert ctrl.state == Controller.State.READY

            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            if ctrl.is_on:
                await ctrl.set_on(False)
                await sleep(1.6)

            assert ctrl.state == Controller.State.READY
            assert not ctrl.is_on

            print(datetime.now().time(), " Turning on: ", uid)
            await ctrl.set_on(True)

            # test changes while state is BUSY
            await listener.updates[uid].acquire()
            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            assert ctrl.state == Controller.State.BUSY
            for fan in Controller.Fan:
                print(
                    datetime.now().time(),
                    " Commanding controller ",
                    uid,
                    " fan to: ",
                    fan,
                )
                await ctrl.set_fan(fan)

                # test still updating
                while not listener.updates[uid].locked():
                    await listener.updates[uid].acquire()

                print(
                    datetime.now().time(),
                    " Controller ",
                    uid,
                    " reports fan is: ",
                    ctrl.fan,
                )
                assert ctrl.fan == fan
                assert ctrl.is_on
                assert ctrl.state == Controller.State.BUSY

            # Check final value survives after exiting BUSY mode
            assert ctrl.state == Controller.State.BUSY
            fan = ctrl.fan
            assert ctrl.is_on

            await sleep(1.6)

            await listener.updates[uid].acquire()
            while not listener.updates[uid].locked():
                await listener.updates[uid].acquire()

            assert ctrl.state == Controller.State.READY
            assert ctrl.fan == fan
            assert ctrl.is_on
