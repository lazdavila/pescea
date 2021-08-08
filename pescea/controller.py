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

    class DictEntries(Enum):
        """Available controller attributes"""
        HAS_NEW_TIMERS = "HasNewTimers"
        FIRE_IS_ON = "FireIsOn"
        FAN_MODE = "FanMode"
        DESIRED_TEMP = "DesiredTemp"
        CURRENT_TEMP = "CurrentTemp"

    DictValue = Union[str, int, float, bool, Fan]
    ControllerData = Dict[DictEntries, DictValue]

    REQUEST_TIMEOUT = 5
    """Time to wait for results from server."""

    CONNECT_RETRY_TIMEOUT = 20
    """Cool-down period for retrying to connect to the controller"""

    # TODO: Figure out what needs to be done (show "Waiting"?)
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
        exactly one controller. If address is specified then the UID is
        ignored.

        Args:
            device_uid: Controller UId as a string (Serial Number of unit)
            device_addr: Device network address. Usually specified as IP
                address


        Raises:
            ConnectionAbortedError: If address is not set and more than one Escea
                instance is discovered on the network.
            ConnectionRefusedError: If no Escea fireplace is discovered, or no
                device discovered at the given IP address, or the UID does not match
        """
        self._ip = device_ip
        self._discovery = discovery
        self._device_uid = device_uid

        """ System settings:
            on / off
            fan mode
            set temperature
            current temperature
        """
        self._system_settings = {}  # type: Controller.ControllerData

        self._initialised = False
        self._fail_exception = None

        self._sending_lock = Lock()

    async def _initialize(self) -> None:
        """Initialize the controller, does not complete until the system is
        initialised."""

        await self._refresh_system(notify=False)

        self._initialised = True

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

    @property
    def device_ip(self) -> str:
        """IP Address of the unit"""
        return self._ip

    @property
    def device_uid(self) -> str:
        """UId of the unit (serial number)"""
        return self._device_uid

    @property
    def discovery(self):
        return self._discovery

    @property
    def is_on(self) -> bool:
        """True if the system is turned on"""
        return self._get_system_state(self.DictEntries.FIRE_IS_ON) == True

    async def set_on(self, value: bool) -> None:
        """Turn the system on or off.
           Async method, await to ensure command revieved by system.
           Note: After systems receives on or off command, must wait several minutes to be actioned
        """
        await self._set_system_state(self.DictEntries.FIRE_IS_ON, value)

    @property
    def fan(self) -> 'Fan':
        """The current fan level."""
        return self.Fan(self._get_system_state(self.DictEntries.FAN_MODE))

    async def set_fan(self, value: Fan) -> None:
        """The fan level. 
           Async method, await to ensure command revieved by system.
        """
        await self._set_system_state(self.DictEntries.FAN_MODE, value)

    @property
    def desired_temp(self) -> Optional[float]:
        """fireplace DesiredTemp temperature.
        """
        return float(self._get_system_state(self.DictEntries.DESIRED_TEMP))

    async def set_desired_temp(self, value: float):
        """fireplace DesiredTemp temperature.
        This is the unit target temp
        Args:
            value: Valid settings are in range MIN_TEMP..MAX_TEMP
            at 1 degree increments (will be rounded)
        Raises:
            AttributeError: On setting if the argument value is not valid.
                Can still be set even if the mode isn't appropriate.
        """
        degrees = round(value)
        if degrees < Controller.MIN_TEMP or degrees > Controller.MAX_TEMP:
            raise AttributeError(
                'Desired Temp \'{}\' is out of range'.format(degrees))
        await self._set_system_state(self.DictEntries.DESIRED_TEMP, degrees)

    @property
    def room_temp(self) -> Optional[float]:
        """The room air temperature"""
        return float(self._get_system_state(self.DictEntries.CURRENT_TEMP)) or None

    @property
    def temp_min(self) -> float:
        """The minimum valid target (desired) temperature"""
        return float(Controller.TEMP_MIN)

    @property
    def temp_max(self) -> float:
        """The maximum valid target (desired) temperature"""
        return float(Controller.TEMP_MAX)

    async def _refresh_system(self, notify: bool = True) -> None:
        """Refresh the system settings."""
        values = await self.request_status()
        self._system_settings = values
        if notify:
            self._discovery.controller_update(self)

    async def request_status(self):
        try:
            async with self._send_command_async(
                    self, FireplaceMessage.CommandID.STATUS_PLEASE) as response:
                return await response
        except (asyncio.TimeoutError) as ex:
            self._failed_connection(ex)
            raise ConnectionError("Unable to connect to the controller") \
                from ex

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

    # TODO: What to do on failed connection - UDP does not guarantee delivery 
    # so it is expected... should mark it as disconnected if we get X failures
    # ... how to code that up?

    def _failed_connection(self, ex):
        if self._fail_exception:
            self._fail_exception = ex
            return
        self._fail_exception = ex
        if not self._initialised:
            return
        self._discovery.controller_disconnected(self, ex)


    
    async def _send_command_async(self, command: FireplaceMessage.CommandID, data: Any) -> Dict:
        """ Send command via UDP

            Returns received data (for STATUS_PLEASE command)
        """
        loop = self.discovery.loop
        on_complete = loop.create_future()
        device_ip = self.device_ip

        controller_data = {}

        message = FireplaceMessage(command, data)

        class _DatagramProtocol:
            def __init__(self, message, on_complete):
                self.message = message
                self.on_complete = on_complete
                self.transport = None

            def connection_made(self, transport):
                self.transport = transport
                self.transport.sendto(self.message)

            def datagram_received(self, data, addr):
                response = FireplaceMessage(data)
                if response != message.expected_response:
                    _LOG.warning(
                            "Message response id: %s does not match command id: %s",
                            response.response_id, command)
                if response.response_id == FireplaceMessage.ResponseID.STATUS:
                    self.controller_data = { 
                        Controller.DictEntries.HAS_NEW_TIMERS : response.has_new_timers,
                        Controller.DictEntries.FIRE_IS_ON: response.fire_is_on,
                        Controller.DictEntries.DESIRED_TEMP: response.desired_temp,
                        Controller.DictEntries.CURRENT_TEMP: response.current_temp
                    }
                    if response.fan_boost_is_on:
                        self.controller_data += {Controller.DictEntries.FAN_MODE, Controller.Fan.FAN_BOOST}
                    elif response.fire_effect_on:
                        self.controller_data += {Controller.DictEntries.FAN_MODE, Controller.Fan.FLAME_EFFECT}
                    else:
                        self.controller_data += {Controller.DictEntries.FAN_MODE, Controller.Fan.AUTO}
                self.transport.close()

            def error_received(self, exc):
                _LOG.warning(
                        "Error receiving for uid=%s failed with exception: %s",
                        self.device_uid, exc.__repr__())

            def connection_lost(self, exc):
                self.on_complete.set_result(True)

        try:
            async with timeout(Controller.REQUEST_TIMEOUT) as cm:
                transport, _ = await loop.create_datagram_endpoint(
                    lambda: _DatagramProtocol(FireplaceMessage(message, data), on_complete),
                    remote_addr=(device_ip, FireplaceMessage.CONTROLLER_PORT))

                # wait for response to be recieved.
                await on_complete

            if cm.expired:
                if transport:
                    transport.close()
                raise asyncio.TimeoutError()

            on_complete.result()

            return controller_data

        except (OSError, asyncio.TimeoutError) as ex:
            self._failed_connection(ex)
            raise ConnectionError("Unable to send UDP to controller") from ex