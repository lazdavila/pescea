"""Escea Network Controller module"""

import asyncio
import json
import logging
from asyncio import Lock
from enum import Enum
from typing import Any, Dict, List, Union, Optional

from async_timeout import timeout

from .message import FireplaceMessage

_LOG = logging.getLogger("pescea.controller")

REFRESH_INTERVAL = 30.0 # Seconds between updates - nothing changes quickly with fireplaces

class Controller:
    """Interface to Escea controller"""

    class Fan(Enum):
        """All fan modes"""
        AUTO = 'auto'
        FAN_BOOST = 'fan boost'
        FLAME_EFFECT = 'flame effect'

    # DictValue = Union[str, int, float]
    # ControllerData = Dict[str, DictValue]

    REQUEST_TIMEOUT = 5
    """Time to wait for results from server."""

    CONNECT_RETRY_TIMEOUT = 20
    """Cool-down period for retrying to connect to the controller"""

    START_STOP_WAIT_TIME = 120
    """Time to wait for fireplace to start up / shut down"""

    MIN_TEMP = FireplaceMessage.MIN_TEMP
    MAX_TEMP = FireplaceMessage.MAX_TEMP
    """Target temperature limits"""

    def __init__(self, discovery, device_uid: str,
                 device_ip: str) -> None:
        """Create a controller interface.

        Usually this is called from the discovery service. If neither
        device UID or address are specified, will search network for
        exactly one controller. If UID is specified then the addr is
        ignored.

        Args:
            device_uid: Controller UId as a string (Serial Number of unit)
                If specified, will search the network for a matching device
            device_addr: Device network address. Usually specified as IP
                address

            <<device_pin is listed as a discovery reply from fireplaces,
                but does not seem to be used anywhere>>

        Raises:
            ConnectionAbortedError: If id is not set and more than one Escea
                instance is discovered on the network.
            ConnectionRefusedError: If no Escea discovered, or no Escea
                device discovered at the given IP address or UId
        """
        self._ip = device_ip
        self._discovery = discovery
        self._device_uid = device_uid

        self._system_settings = {}  # type: Controller.ControllerData

        self._initialised = False
        self._fail_exception = None

        self._sending_lock = Lock()

    async def _initialize(self) -> None:
        """Initialize the controller, does not complete until the system is
        initialised."""
        await self._refresh_system(notify=False)

        self._initialised = True

        """ Is this needed:? """
        self.discovery.loop.create_task(self._poll_loop())

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(REFRESH_INTERVAL)

            if self._discovery.is_closed:
                return

            try:
                await self._refresh()
                _LOG.debug("Polling unit %s.", self._device_uid)
            except ConnectionError as ex:
                _LOG.debug("Poll failed due to exception %s.", repr(ex))

    """ New code ... needs to be worked out """

    @property
    def device_ip(self) -> str:
        """IP Address of the unit"""
        return self._ip

    @property
    def device_uid(self) -> str:
        '''UId of the unit'''
        return self._device_uid

    @property
    def discovery(self):
        return self._discovery

    @property
    def is_on(self) -> bool:
        """True if the system is turned on"""
        return self._get_system_state('SysOn') == 'on'

    async def set_on(self, value: bool) -> None:
        """Turn the system on or off."""
        await self._set_system_state(
            'SysOn', 'SystemON', 'on' if value else 'off')

    @property
    def fan(self) -> 'Fan':
        """The current fan level."""
        return self.Fan(self._get_system_state('SysFan'))

    async def set_fan(self, value: Fan) -> None:
        """The fan level. 
           Async method, await to ensure command revieved by system.
        """
        await self._set_system_state(
            'SysFan', 'SystemFAN', value.value)

    @property
    def temp_setpoint(self) -> Optional[float]:
        """fireplace setpoint temperature.
        """
        return float(self._get_system_state('Setpoint')) or None

    async def set_temp_setpoint(self, value: float):
        """fireplace setpoint temperature.
        This is the unit target temp
        Args:
            value: Valid settings are between tempMin and tempMax
            at 1 degree increments
        Raises:
            AttributeError: On setting if the argument value is not valid.
                Can still be set even if the mode isn't appropriate.
        """
        if value % 1.0 != 0:
            raise AttributeError(
                'SetPoint \'{}\' not rounded to nearest degree'.format(value))
        if value < self.temp_min or value > self.temp_max:
            raise AttributeError(
                'SetPoint \'{}\' is out of range'.format(value))
        await self._set_system_state(
            'Setpoint', 'UnitSetpoint', value, str(value))

    @property
    def temp_return(self) -> Optional[float]:
        """The return, or room, air temperature"""
        return float(self._get_system_state('Temp')) or None

    @property
    def temp_min(self) -> float:
        """The minimum valid target (desired) temperature"""
        return float(Controller.TEMP_MIN)

    @property
    def temp_max(self) -> float:
        """The maximum valid target (desired) temperature"""
        return float(Controller.TEMP_MAX)

    # TODO: What is going on here? Get the response command?
    async def _refresh_system(self, notify: bool = True) -> None:
        """Refresh the system settings."""
        values = await self._get_resource('SystemSettings')
        if self._device_uid != values['ControllerDeviceUId']:
            _LOG.error("_refresh_system called with unmatching device ID")
            return

        self._system_settings = values

        if notify:
            self._discovery.controller_update(self)

    def _refresh_address(self, address):
        """Called from discovery to update the address"""
        self._ip = address
        # Signal to the retry connection loop to have another go.
        if self._fail_exception:
            self._discovery.create_task(self._retry_connection())

    def _get_system_state(self, state):
        self._ensure_connected()
        return self._system_settings.get(state)

    async def _set_system_state(self, state, command, value):
        if self._system_settings[state] == value:
            return

        async with self._sending_lock:
            await self._send_command_async(command, value)

            # Need to refresh immediately after setting.
            try:
                await self._refresh_system()
            except ConnectionError:
                pass

    def _ensure_connected(self) -> None:
        if self._fail_exception:
            raise ConnectionError("Unable to connect to the controller") \
                from self._fail_exception

    def _failed_connection(self, ex):
        if self._fail_exception:
            self._fail_exception = ex
            return
        self._fail_exception = ex
        if not self._initialised:
            return
        self._discovery.controller_disconnected(self, ex)

    async def _retry_connection(self) -> None:
        _LOG.info(
            "Attempting to reconnect to server uid=%s ip=%s",
            self.device_uid, self.device_ip)

        try:
            await self._refresh(notify=False)

            self._fail_exception = None

            self._discovery.controller_update(self)
            self._discovery.controller_reconnected(self)
        except ConnectionError as ex:
            # Expected, just carry on.
            _LOG.warning(
                "Reconnect attempt for uid=%s failed with exception: %s",
                self.device_uid, ex.__repr__())

    async def _get_resource(self, resource: str):
        try:
            session = self._discovery.session
            async with session.get(
                    'http://%s/%s' % (self.device_ip, resource),
                    timeout=Controller.REQUEST_TIMEOUT) as response:
                return await response.json(content_type=None)
        except (asyncio.TimeoutError, aiohttp.ClientError) as ex:
            self._failed_connection(ex)
            raise ConnectionError("Unable to connect to the controller") \
                from ex

    async def _send_command_async(self, command: str, data: Any):
        # For some reason aiohttp fragments post requests, which causes
        # the server to fail disgracefully. Implimented rough and dirty
        # HTTP POST client.
        loop = self.discovery.loop
        on_complete = loop.create_future()
        device_ip = self.device_ip

        class _PostProtocol(asyncio.Protocol):
            def connection_made(self, transport):
                body = json.dumps({command: data}).encode()
                header = (
                    "POST /" + command + " HTTP/1.1\r\n" +
                    "Host: " + device_ip + "\r\n" +
                    "Content-Length: " + str(len(body)) + "\r\n" +
                    "\r\n").encode()
                _LOG.debug(
                    "Writing message to " + device_ip + body.decode())
                transport.write(header + body)
                self.transport = transport

            def data_received(self, data):
                self.transport.close()
                response = data.decode()  # type: str
                lines = response.split('\r\n', 1)
                if not lines:
                    return
                parts = lines[0].split(' ')
                if(len(parts) != 3):
                    return
                if int(parts[1]) != 200:
                    on_complete.set_exception(
                        aiohttp.ClientResponseError(
                            None, None,
                            status=int(parts[1]),
                            message=parts[2]))
                else:
                    on_complete.set_result(True)

        try:
            async with timeout(Controller.REQUEST_TIMEOUT) as cm:
                transport, _ = await loop.create_connection(  # type: ignore
                    lambda: _PostProtocol(),
                    self.device_ip, 80)  # mypy: ignore

                # wait for response to be recieved.
                await on_complete

            if cm.expired:
                if transport:
                    transport.close()
                raise asyncio.TimeoutError()

            on_complete.result()

        except (OSError, asyncio.TimeoutError, aiohttp.ClientError) as ex:
            self._failed_connection(ex)
            raise ConnectionError("Unable to connect to controller") from ex
