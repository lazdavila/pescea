"""Escea Network Controller module"""

import logging
import asyncio

from enum import Enum
from typing import Dict, Union, Optional
from time import time

# Pescea imports:
from pescea.message import FireplaceMessage, CommandID, ResponseID, MIN_SET_TEMP, MAX_SET_TEMP, expected_response
from pescea.datagram import FireplaceDatagram

_LOG = logging.getLogger("pescea.controller")

# Time to wait for results from UDP command to server
REQUEST_TIMEOUT = 5

# Seconds between updates under normal conditions
#  - nothing changes quickly with fireplaces
REFRESH_INTERVAL = 30.0

# Retry rate when first get disconnected
RETRY_INTERVAL = 10.0

# Timeout to stop retrying and reduce poll rate (and notify Discovery)
RETRY_TIMEOUT = 60.0

# Time to wait when have been disconnected longer than RETRY_TIMOUT
DISCONNECTED_INTERVAL = 300.0

# Time to wait for fireplace to start up / shut down
# - Commands are stored, but not sent to the fireplace until it has settled
ON_OFF_BUSY_WAIT_TIME = 120

class ControllerState(Enum):
    """ Controller states:

        Under normal operations:
            The Controller is READY:
                - The Controller sends commands directly to the Fireplace
                - The Controller polls at REFRESH_INTERVAL
        When toggling the fire power:
            The Controller remains BUSY for ON_OFF_BUSY_WAIT_TIME:
                - The Controller buffers requests but does not send to the Fireplace
        When responses are missed (expected as we are using UDP datagrams):
            The Controller is NON_RESPONSIVE
                - The Controller will poll at a (quicker) retry rate
        When there are no comms for a prolonged period:
            The Controller enters DISCONNECTED state
                - The Controller will continue to poll at a reduced rate
                - The Controller buffers requests but cannot send to the Fireplace
    """
    BUSY = "BusyWaiting"
    READY = "Ready"
    NON_RESPONSIVE = "NonResponsive"
    DISCONNECTED = "Disconnected"

class Fan(Enum):
    """All fan modes"""
    FLAME_EFFECT = 'FlameEffect'
    AUTO = 'Auto'
    FAN_BOOST = 'FanBoost'

class DictEntries(Enum):
    """Available controller attributes - Internal Use Only"""
    IP_ADDRESS = "IPAddress"
    DEVICE_UID = "DeviceUId"
    CONTROLLER_STATE = "ControllerState"
    HAS_NEW_TIMERS = "HasNewTimers"
    FIRE_IS_ON = "FireIsOn"
    FAN_MODE = "FanMode"
    DESIRED_TEMP = "DesiredTemp"
    CURRENT_TEMP = "CurrentTemp"

class Controller:
    """Interface to Escea controller"""

    DictValue = Union[str, int, float, bool, Fan]
    ControllerData = Dict[DictEntries, DictValue]

    def __init__(self, discovery, device_uid: str,
                 device_ip: str) -> None:
        """Create a controller interface.

        Usually this is called from the discovery service.

        Args:
            device_uid: Controller UId as a string (Serial Number of unit)
            device_addr: Device network address. Usually specified as IP
                address
        """


        """ System settings:
            on / off
            fan mode
            set temperature
            current temperature
        """
        self._discovery = discovery
        self._system_settings = {}  # type: Controller.ControllerData
        self._system_settings[DictEntries.IP_ADDRESS] = device_ip
        self._system_settings[DictEntries.DEVICE_UID] = device_uid

        self._sending_lock = asyncio.Lock()
        self._datagram = FireplaceDatagram(self._discovery.loop, device_ip)

        self._initialised = False        

    async def initialize(self) -> None:
        """ Initialize the controller, does not complete until the firplace has
            been contacted and current settings read.
        """

        # Under normal operations, the Controller state is READY
        self._state = ControllerState.READY
        self._last_response = 0.0 # Used to track last valid message received
        self._busy_end_time = 0.0 # Used to track when exit BUSY state

        # Use to exit poll_loop when told to
        self._closed = False

        # Read current state of fireplace
        await self._refresh_system(notify=False)

        self._initialised = True

        # Start regular polling for status updates
        self._discovery.loop.create_task(self._poll_loop())

    def close(self):
        """Signal loop to exit"""
        self._closed = True

    async def _poll_loop(self) -> None:
        """ Regularly poll for status update from fireplace.
            If Disconnected, retry based on how long ago we last had an update.
            If Disconnected for a long time, let Discovery know we are giving up.
        """
        while not self._closed:

            await self._refresh_system()

            _LOG.debug("Polling unit %s at address %s (current state is %s)",
                self._system_settings[DictEntries.DEVICE_UID],
                self._system_settings[DictEntries.IP_ADDRESS],
                self._state)

            if self._state == ControllerState.READY:
                sleep_time = REFRESH_INTERVAL
            elif self._state == ControllerState.NON_RESPONSIVE:
                sleep_time = RETRY_INTERVAL
            elif self._state == ControllerState.DISCONNECTED:
                sleep_time = DISCONNECTED_INTERVAL
            elif self._state == ControllerState.BUSY:
                sleep_time = max(self._busy_end_time - time(), 0.0)

            await asyncio.sleep(sleep_time)

    @property
    def device_ip(self) -> str:
        """IP Address of the unit"""
        return self._system_settings[DictEntries.IP_ADDRESS]

    @property
    def device_uid(self) -> str:
        """UId of the unit (serial number)"""
        return self._system_settings[DictEntries.DEVICE_UID]

    @property
    def discovery(self):
        return self._discovery

    @property
    def state(self) -> Optional[ControllerState]:
        """True if the system is turned on"""
        return self._state

    @property
    def is_on(self) -> Optional[bool]:
        """True if the system is turned on"""
        return self._get_system_state(DictEntries.FIRE_IS_ON) or None

    async def set_on(self, value: bool) -> None:
        """Turn the system on or off.
           Async method, await to ensure command revieved by system.
           Note: After systems receives on or off command, must wait several minutes to be actioned
        """
        await self._set_system_state(DictEntries.FIRE_IS_ON, value)

    @property
    def fan(self) -> Optional[Fan]:
        """The current fan level."""
        return self._get_system_state(DictEntries.FAN_MODE) or None

    async def set_fan(self, value: Fan) -> None:
        """The fan level. 
           Async method, await to ensure command revieved by system.
        """
        await self._set_system_state(DictEntries.FAN_MODE, value)

    @property
    def desired_temp(self) -> Optional[float]:
        """fireplace DesiredTemp temperature.
        """
        return float(self._get_system_state(DictEntries.DESIRED_TEMP)) or None

    async def set_desired_temp(self, value: float):
        """Fireplace DesiredTemp temperature.

            This is the unit target temp
            Args:
                value: Valid settings are in range MIN_TEMP..MAX_TEMP
                at 1 degree increments (will be rounded)
        """
        degrees = round(value)
        if degrees < MIN_SET_TEMP or degrees > MAX_SET_TEMP:
            _LOG.error("Desired Temp %s is out of range (%s-%s)", degrees, MIN_SET_TEMP, MAX_SET_TEMP)
            return

        await self._set_system_state(DictEntries.DESIRED_TEMP, degrees)

    @property
    def current_temp(self) -> Optional[float]:
        """The room air temperature"""
        return float(self._get_system_state(DictEntries.CURRENT_TEMP)) or None

    @property
    def min_temp(self) -> float:
        """The minimum valid target (desired) temperature"""
        return float(MIN_SET_TEMP)

    @property
    def max_temp(self) -> float:
        """The maximum valid target (desired) temperature"""
        return float(MAX_SET_TEMP)

    async def _refresh_system(self, notify: bool = True) -> None:
        """ Request fresh status from the fireplace.

            This is also where state changes are handled
            Approach:

                if current state BUSY (not timed out) -> return

                request status

                New status received:
                    if prior state READY
                        update local system settings from received message
                    else (prior state must be DISCONNECTED / NON_RESPONSIVE / BUSY (timeout))
                        sync buffered commands to fireplace
                        new state READY
                        if prior state DISCONNECTED:
                            notify discovery reconnected

                No status received:
                    prior state *ANY*
                        if time since last response < RETRY_TIMEOUT
                            new state NON_RESPONSIVE
                        else
                            notify discovery disconnected
                            new state DISCONNECTED
        """
        if self._state == ControllerState.BUSY and time() < self._busy_end_time:
            return

        prior_state = self._state
        response = await self._request_status()
        if (response is not None) and (response.response_id == ResponseID.STATUS):
            # We have a valid response - the controller is communicating

            # These values are readonly, so copy them in any case
            self._system_settings[DictEntries.HAS_NEW_TIMERS] = response.has_new_timers
            self._system_settings[DictEntries.CURRENT_TEMP]   = response.current_temp

            if prior_state == ControllerState.READY:

                # Normal operation, update our internal values
                self._system_settings[DictEntries.DESIRED_TEMP]   = response.desired_temp
                if response.fan_boost_is_on:
                    self._system_settings[DictEntries.FAN_MODE]   = Fan.FAN_BOOST
                elif response.flame_effect:
                    self._system_settings[DictEntries.FAN_MODE]   = Fan.FLAME_EFFECT
                else:
                    self._system_settings[DictEntries.FAN_MODE]   = Fan.AUTO
                self._system_settings[DictEntries.FIRE_IS_ON]     = response.fire_is_on

                if notify:
                    self._discovery.controller_update(self)

            else:

                # We have come back to READY state.
                # We need to try to sync the fireplace settings with our internal copies

                if response.desired_temp != self._system_settings[DictEntries.DESIRED_TEMP]:
                    await self._set_system_state(DictEntries.DESIRED_TEMP, self._system_settings[DictEntries.DESIRED_TEMP], sync=True)

                if (response.fan_boost_is_on != (self._system_settings[DictEntries.FAN_MODE] == Fan.FAN_BOOST)) \
                        or  (response.flame_effect != (self._system_settings[DictEntries.FAN_MODE] == Fan.FLAME_EFFECT)):
                    await self._set_system_state(DictEntries.FAN_MODE, self._system_settings[DictEntries.FAN_MODE], sync=True)

                # Do power last
                if response.fire_is_on != self._system_settings[DictEntries.FIRE_IS_ON]:
                    # This will also set the BUSY state
                    await self._set_system_state(DictEntries.FIRE_IS_ON, self._system_settings[DictEntries.FIRE_IS_ON], sync=True )
                else:
                    self._state = ControllerState.READY

                if prior_state == ControllerState.DISCONNECTED:
                    self._discovery.controller_reconnected(self)                    

        else:
            # No / invalid response, need to check if we need to change state
            if time() - self._last_response < RETRY_TIMEOUT:
                self._state = ControllerState.NON_RESPONSIVE
            else:
                self._state = ControllerState.DISCONNECTED
                self._discovery.controller_disconnected(self, TimeoutError)

    async def _request_status(self) -> FireplaceMessage:
        try:
            async with self._sending_lock:
                responses = await self._datagram.send_command(CommandID.STATUS_PLEASE)
            if (len(responses) > 0):
                this_response = next(iter(responses)) # only expecting one
                if responses[this_response].response_id == expected_response(CommandID.STATUS_PLEASE):
                    # all good
                    self._last_response = time()
                    return responses[this_response]
            # If we get here... did not receive a response or not valid
            self._state = ControllerState.NON_RESPONSIVE
            return

        except (TimeoutError) as ex:
            return None

    def refresh_address(self, address):
        """Called from discovery to update the address"""
        if self._system_settings[DictEntries.IP_ADDRESS] == address:
            return

        self._datagram.set_ip(address)
        self._system_settings[DictEntries.IP_ADDRESS] = address

        # If we are DISCONNECTED, then reset the time change so we poll a bit quicker
        if self._state == ControllerState.DISCONNECTED:
            self._state_changed = time()

    def _get_system_state(self, state: DictEntries):
        return self._system_settings[state]

    async def _set_system_state(self, state: DictEntries, value, sync: bool = False):

        # ignore if we are not forcing the synch, and value matches already
        if (not sync) and (self._system_settings[state] == value):
            return

        # save the new value internally
        self._system_settings[state] = value

        if self._state != ControllerState.READY:
            # We've saved the new value.... just can't send it to the controller yet
            return

        command = None

        if state == DictEntries.FIRE_IS_ON:
            if value:
                command = CommandID.POWER_ON
            else:
                command = CommandID.POWER_OFF

        elif state == DictEntries.DESIRED_TEMP:
            command = CommandID.NEW_SET_TEMP

        elif state == DictEntries.FAN_MODE:

            # Fan is implemented via separate FLAME_EFFECT and FAN_BOOST commands
            # Any change will take one or two separate commands:
            # PART 1 -
            #
            # To AUTO:
            # 1. If currently FAN_BOOST, turn off FAN_BOOST
            #    else (currently FLAME_EFFECT), turn off FLAME_EFFECT
            if value == Fan.AUTO:
                if self._system_settings[state] == Fan.FAN_BOOST:
                    command = CommandID.FAN_BOOST_OFF
                else:
                    command = CommandID.FLAME_EFFECT_OFF

            # To FAN_BOOST:
            # 1. If currently FLAME_EFFECT, turn off FLAME_EFFECT
            # 2. Turn on FAN_BOOST
            elif value == Fan.FAN_BOOST:
                if self._system_settings[state] == Fan.FLAME_EFFECT:
                    command = CommandID.FLAME_EFFECT_OFF

            # To FLAME_EFFECT:
            # 1. If currently FAN_BOOST, turn off FAN_BOOST
            # 2. Turn on FLAME_EFFECT
            elif value == Fan.FLAME_EFFECT:
                if self._system_settings[state] == Fan.FAN_BOOST:
                    command = CommandID.FAN_BOOST_OFF

        else:
            raise(AttributeError, "Unexpected state: {0}".format(state))

        if command is not None:
            async with self._sending_lock:
                responses = await self._datagram.send_command(command, value)
            if (len(responses) > 0) \
                    and (responses[next(iter(responses))].response_id == expected_response(command)):
                # all good
                self._last_response = time()
            else:
                # not the expected response, or got no response
                self._state = ControllerState.NON_RESPONSIVE
                return

        if (state == DictEntries.FAN_MODE) and (value != Fan.AUTO):
            # Fan is implemented via separate FLAME_EFFECT and FAN_BOOST commands
            # Any change will take one or two separate commands:
            # PART 2 -
            #
            # To FAN_BOOST:
            # 1. If currently FLAME_EFFECT, turn off FLAME_EFFECT
            # 2. Turn on FAN_BOOST
            if value == Fan.FAN_BOOST:
                command = CommandID.FAN_BOOST_ON

            # To FLAME_EFFECT:
            # 1. If currently FAN_BOOST, turn off FAN_BOOST
            # 2. Turn on FLAME_EFFECT
            else:
                command = CommandID.FLAME_EFFECT_ON

            async with self._sending_lock:
                responses = await self._datagram.send_command(command, value)
            if (len(responses) > 0) \
                    and (responses[next(iter(responses))].response_id == expected_response(command)):
                # all good
                self._last_response = time()
            else:
                # not the expected response, or got no response
                self._state = ControllerState.NON_RESPONSIVE
                return

        # Need to refresh immediately after setting (unless synching, then poll loop will update)
        if not sync:
            await self._refresh_system()

        # If get here, and just toggled the fireplace power... need to wait for a while
        if state == DictEntries.FIRE_IS_ON:
            self._state = ControllerState.BUSY
            self._busy_end_time = time() + ON_OFF_BUSY_WAIT_TIME

    """ The remaining methods are for test purposes only """

    def dump(self, indent: str = '') -> None:
        tab = "    "
        print(indent + "Controller:")
        print(indent + tab + "Discovery: {0}".format(self._discovery))
        print(indent + tab + "Settings: {0}".format(self._system_settings))
        print(indent + tab + "Initialised: {0}".format(self._initialised))
        if self._fail_exception is not None:
            print(indent + tab +
                  "Fail Exception: {0}".format(self._fail_exception))
        self._datagram.dump(indent=indent + tab)
