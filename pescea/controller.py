"""Escea Network Controller module"""

import asyncio
import logging
from asyncio import Lock
from enum import Enum
from typing import Dict, Union, Optional

from .message import FireplaceMessage
from .datagram import FireplaceDatagram

_LOG = logging.getLogger("pescea.controller")

REFRESH_INTERVAL = 30.0 # Seconds between updates - nothing changes quickly with fireplaces

class Controller:
    """Interface to Escea controller"""

    class Fan(Enum):
        """All fan modes"""
        FLAME_EFFECT = 'FlameEffect'
        AUTO = 'Auto'
        FAN_BOOST = 'FanBoost'

    # DictValue = Union[str, int, float]
    # ControllerData = Dict[str, DictValue]

    class DictEntries(Enum):
        """Available controller attributes"""
        IP_ADDRESS = "IPAddress"
        DEVICE_UID = "DeviceUId"
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
    """Cool-down period for retrying to connect to the fireplace"""

    # TODO: Figure out what needs to be done (show "Waiting"?)
    START_STOP_WAIT_TIME = 120
    """Time to wait for fireplace to start up / shut down"""

    MIN_TEMP = FireplaceMessage.MIN_SET_TEMP
    MAX_TEMP = FireplaceMessage.MAX_SET_TEMP
    """Target temperature limits"""

    def __init__(self, discovery, device_uid: str,
                 device_ip: str) -> None:
        """Create a controller interface.

        Usually this is called from the discovery service.

        Args:
            device_uid: Controller UId as a string (Serial Number of unit)
            device_addr: Device network address. Usually specified as IP
                address

        Raises:
            ConnectionAbortedError: If address is not set and more than one Escea fireplace
                instance is discovered on the network.
            ConnectionRefusedError: If no Escea fireplace is discovered, or no
                device discovered at the given IP address, or the UID does not match
        """
        self._discovery = discovery

        """ System settings:
            on / off
            fan mode
            set temperature
            current temperature
        """
        self._system_settings = {}  # type: Controller.ControllerData
        self._system_settings[self.DictEntries.IP_ADDRESS] = device_ip
        self._system_settings[self.DictEntries.DEVICE_UID] = device_uid


        self._initialised = False
        self._fail_exception = None

        self._sending_lock = Lock()

        self._datagram = FireplaceDatagram(self.discovery, device_ip)

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
                await self._refresh_system()
                _LOG.debug("Polling unit %s.", self._system_settings[self.DictEntries.DEVICE_UID])
            except ConnectionError as ex:
                _LOG.debug("Poll failed due to exception %s.", repr(ex))

    @property
    def device_ip(self) -> str:
        """IP Address of the unit"""
        return self._system_settings[self.DictEntries.IP_ADDRESS]

    @property
    def device_uid(self) -> str:
        """UId of the unit (serial number)"""
        return self._system_settings[self.DictEntries.DEVICE_UID]

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
    def fan(self):
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
    def current_temp(self) -> Optional[float]:
        """The room air temperature"""
        return float(self._get_system_state(self.DictEntries.CURRENT_TEMP)) or None

    @property
    def min_temp(self) -> float:
        """The minimum valid target (desired) temperature"""
        return float(Controller.MIN_TEMP)

    @property
    def max_temp(self) -> float:
        """The maximum valid target (desired) temperature"""
        return float(Controller.MAX_TEMP)

    async def _refresh_system(self, notify: bool = True) -> None:
        """Refresh the system settings."""
        response = await self.request_status()
        if response.response_id == FireplaceMessage.ResponseID.STATUS:
            self._system_settings[self.DictEntries.HAS_NEW_TIMERS] = response.has_new_timers
            self._system_settings[self.DictEntries.FIRE_IS_ON] = response.fire_is_on
            self._system_settings[self.DictEntries.DESIRED_TEMP] = response.desired_temp
            self._system_settings[self.DictEntries.CURRENT_TEMP] = response.current_temp
            if response.fan_boost_is_on:
                self._system_settings[self.DictEntries.FAN_MODE] = Controller.Fan.FAN_BOOST
            elif response.fire_effect_on:
                self._system_settings[self.DictEntries.FAN_MODE] = Controller.Fan.FLAME_EFFECT
            else:
                self._system_settings[self.DictEntries.FAN_MODE] = Controller.Fan.AUTO
        if notify:
            self._discovery.controller_update(self)

    async def request_status(self) -> FireplaceMessage:
        try:
            async with self._datagram._send_command_async(
                        FireplaceMessage.CommandID.STATUS_PLEASE) as responses:
                await responses
                _, response = next(iter(responses)) # just expecting one
                return response
        except (asyncio.TimeoutError) as ex:
            self._failed_connection(ex)
            raise ConnectionError("Unable to connect to the fireplace") \
                from ex

    def _refresh_address(self, address):
        """Called from discovery to update the address"""
        self._system_settings[self.DictEntries.IP_ADDRESS] = address
        self._datagram.set_ip(address)
        # Signal to the retry connection loop to have another go.
        if self._fail_exception:
            self._discovery.create_task(self._retry_connection())

    def _get_system_state(self, state):
        self._ensure_connected()
        return self._system_settings[state]

    async def _set_system_state(self, state, value):
        if self._system_settings[state] == value:
            return

        if state == self.DictEntries.FIRE_IS_ON:
            if value:
                command = FireplaceMessage.CommandID.POWER_ON
            else:
                command = FireplaceMessage.CommandID.POWER_OFF

        elif state == self.DictEntries.DESIRED_TEMP:
            command = FireplaceMessage.CommandID.NEW_SET_TEMP

        else:
            # Fan is implemented via separate FLAME_EFFECT and FAN_BOOST commands
            # Any change will take one or two separate commands:
            # PART 1 -
            #
            # To AUTO:
            # 1. If currently FAN_BOOST, turn off FAN_BOOST
            #    else (currently FLAME_EFFECT), turn off FLAME_EFFECT
            if value == self.fan.AUTO:
                if self._system_settings[state] == self.fan.FAN_BOOST:
                    command = FireplaceMessage.CommandID.FAN_BOOST_OFF
                else:
                    command = FireplaceMessage.CommandID.FLAME_EFFECT_OFF

            # To FAN_BOOST:
            # 1. If currently FLAME_EFFECT, turn off FLAME_EFFECT
            # 2. Turn on FAN_BOOST
            elif value == self.fan.FAN_BOOST:
                if self._system_settings[state] == self.fan.FLAME_EFFECT:
                    command = FireplaceMessage.CommandID.FLAME_EFFECT_OFF      

            # To FLAME_EFFECT:
            # 1. If currently FAN_BOOST, turn off FAN_BOOST
            # 2. Turn on FLAME_EFFECT
            else:
                if self._system_settings[state] == self.fan.FAN_BOOST:
                    command = FireplaceMessage.CommandID.FAN_BOOST_OFF 

        async with self._sending_lock:
            await self._datagram._send_command_async(command, value)

        if (state == self.DictEntries.FAN_MODE) and (value == self.Fan.AUTO):
            # Fan is implemented via separate FLAME_EFFECT and FAN_BOOST commands
            # Any change will take one or two separate commands:
            # PART 2 -
            #
            # To FAN_BOOST:
            # 1. If currently FLAME_EFFECT, turn off FLAME_EFFECT
            # 2. Turn on FAN_BOOST
            if value == self.fan.FAN_BOOST:
                command = FireplaceMessage.CommandID.FAN_BOOST_ON      

            # To FLAME_EFFECT:
            # 1. If currently FAN_BOOST, turn off FAN_BOOST
            # 2. Turn on FLAME_EFFECT
            else:
                command = FireplaceMessage.CommandID.FLAME_EFFECT_ON 

            async with self._sending_lock:
                await self._datagram._send_command_async(command, value)


        # Need to refresh immediately after setting.
        try:
            await self._refresh_system()
        except ConnectionError:
            pass

    def _ensure_connected(self) -> None:
        if self._fail_exception:
            raise ConnectionError("Unable to connect to the fireplace") \
                from self._fail_exception

    def _failed_connection(self, ex):
        if self._fail_exception:
            self._fail_exception = ex
            return
        self._fail_exception = ex
        if not self._initialised:
            return
        self._discovery.controller_disconnected(self, ex)

    """ The remaining methods are for test purposes only """
    
    def dump(self, indent: str = '') -> None:
        tab = "    "
        print(indent + "Controller:")
        print(indent + tab + "Discovery: {0}".format(self._discovery))
        print(indent + tab + "Settings: {0}".format(self._system_settings))
        print(indent + tab + "Initialised: {0}".format(self._initialised))
        if self._fail_exception is not None:
            print(indent + tab + "Fail Exception: {0}".format(self._fail_exception))
        self._datagram.dump( indent = indent + tab)