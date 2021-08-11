from asyncio import sleep, AbstractEventLoop
from typing import Any, Dict, List, Tuple
from copy import deepcopy

from asynctest.mock import Mock
from aiohttp import ClientSession

from pescea.controller import Controller
from pescea.discovery import DiscoveryService

from pytest import fixture

class MockController(Controller):

    def __init__(self, discovery, device_uid: str, device_ip: str, is_v2) -> None:
        super().__init__(discovery, device_uid, device_ip, is_v2)
        from .resources import SYSTEMS
        self.resources = deepcopy(SYSTEMS[device_uid])  # type: Dict[str,Any]
        self.sent = []  # type: List[Tuple[str,Any]]
        self.connected = True

    async def _get_resource(self, resource: str):
        """Mock out the network IO for _get_resource."""
        self._check_connected()
        result = self.resources.get(resource)
        if result:
            return deepcopy(result)
        raise ConnectionError(
            "Mock resource '{}' not available".format(resource))

    async def _send_command_async(self, command: str, data: Any):
        """Mock out the network IO for _send_command."""
        self._check_connected()
        self.sent.append((command, data))

    async def change_system_state(self, state: str, value: Any) -> None:
        self.resources['SystemSettings'][state] = value
        self.discovery._process_datagram(
           b'changedsystem', ('8.8.8.8', 12107))
        await sleep(0)

class MockDiscoveryService(DiscoveryService):

    def __init__(self, loop: AbstractEventLoop = None,
                 session: ClientSession = None) -> None:
        super().__init__(loop=loop)
        self._send_broadcasts = Mock()  # type: ignore
        self.datagram_received = Mock()  # type: ignore
        self.connected = True

    def _create_controller(self, device_uid, device_ip, is_v2):
        return MockController(self, device_uid=device_uid, device_ip=device_ip, is_v2=is_v2)


@fixture
def service(event_loop):
    """Fixture to provide a test instance of HASS."""
    service = MockDiscoveryService(event_loop)
    event_loop.run_until_complete(service.start_discovery())

    service._process_datagram(
        b'ASPort_12107,Mac_000000001,IP_8.8.8.8,Escea,iLight,iDrate',
        ('8.8.8.8', 12107))
    event_loop.run_until_complete(sleep(0.1))

    yield service

    event_loop.run_until_complete(service.close())