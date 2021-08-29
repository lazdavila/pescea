import asyncio

from asyncio import AbstractEventLoop
from asynctest.mock import Mock
from copy import deepcopy
from pytest import fixture
from typing import Any, Dict, List, Tuple

# Pescea imports
from pescea.discovery import DiscoveryService
from pescea.controller import Controller
from pescea.message import CommandID

class MockController(Controller):

    def __init__(self, discovery, device_uid: str,
                 device_ip: str) -> None:

        super().__init__(discovery, device_uid, device_ip)
        from .resources import fireplaces
        self.resources = deepcopy(fireplaces[device_uid])  # type: Dict[str,Any]
        self.sent = []  # type: List[Tuple[str,Any]]
        self.connected = True

    async def _get_resource(self, resource: str):
        """Mock out the network IO for _get_resource."""
        if self.connected:
            result = self.resources.get(resource)
            if result:
                return deepcopy(result)
        raise ConnectionError(
            'Mock resource {} not available'.format(resource))

    async def send_command(self, command: CommandID, data: Any):
        """Mock out the network IO for send_command."""
        if self.connected:
            self.sent.append((command, data))

    async def change_system_state(self, state: str, value: Any) -> None:
        self.resources[state] = value
        # TODO: Force status refresh
        await asyncio.sleep(0)

class MockDiscoveryService(DiscoveryService):

    def __init__(self, loop: AbstractEventLoop = None) -> None:
        super().__init__(loop=loop)
        self._send_broadcasts = Mock()  # type: ignore
        self.datagram_received = Mock()  # type: ignore
        self.connected = True

    def _create_controller(self, device_uid, device_ip):
        return MockController(self, device_uid=device_uid, device_ip=device_ip)

@fixture
def service(event_loop):
    """Fixture to provide a test instance of HASS."""
    service = MockDiscoveryService(event_loop)
    event_loop.run_until_complete(service.start_discovery())

    # service._process_datagram(
    #     b'ASPort_12107,Mac_000000001,IP_8.8.8.8,Escea',
    #     ('8.8.8.8', 12107))
    event_loop.run_until_complete(asyncio.sleep(0.1))

    yield service

    event_loop.run_until_complete(service.close())

