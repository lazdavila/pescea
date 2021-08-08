"""Escea Fireplace Message module"""

import logging
from enum import Enum
from typing import Any, Dict, List, Union, Optional

_LOG = logging.getLogger("pescea.message")

class FireplaceMessage:

    """ Implements messages to and from the fireplace.
        Refer to Escea Fireplace LAN Comms Spec for details.
    """
    # Port to use for discovery and integration
    CONTROLLER_PORT = 3300

    # The same message structure is used for commands and responses:
    MESSAGE_LENGTH = 15
    MSG_OFFSET_START_BYTE = 0  # Byte 1: Start Byte code
    MSG_OFFSET_ID = 1          # Byte 2: Command / Response ID
    MSG_OFFSET_DATA_LENGTH = 2 # Byte 3: Data Length
    MSG_OFFSET_DATA_START = 3  # Byte 4..13: Data (0 filled / don'tcare after Data Length)
    MSG_OFFSET_DATA_END = 12
    MSG_OFFSET_CRC = 13        # Byte 14: CRC (Sum Bytes 2 to 13, overflowing on 256)
    MSG_OFFSET_END_BYTE = 14   # Byte 15: End Byte code

    # Data structure for STATUS response:
    DATA_OFFSET_TIMERS = 0       # Data Byte 1: (boolean) Fireplace has new timers (not used)
    DATA_OFFSET_FIRE_ON = 1      # Data Byte 2: (boolean) Fire is On
    DATA_OFFSET_BOOST_ON = 2     # Data Byte 3: (boolean) Fan Boost is on
    DATA_OFFSET_EFFECT_ON = 3    # Data Byte 4: (boolean) Flame Effect is on
    DATA_OFFSET_DESIRED_TEMP = 4 # Data Byte 5: (unsigned int) Desired Temperature
    DATA_OFFSET_CURRENT_TEMP = 5 # Data Byte 6: (unsigned int) Room Temperature

    # Data structure for I_AM_A_FIRE response:
    DATA_OFFSET_SERIAL = 0       # Data Bytes 1..4: (Unsigned Long, big Endian) Serial Number (use for UID)
    DATA_OFFSET_PIN = 4          # Data Byte 5..6: (Unsigned Long, big Endian) PIN (not used)

    # Preconfigured start/end characters:
    MESSAGE_START_BYTE = b'\x47'
    MESSAGE_END_BYTE = b'\x46'

    # Valid command identifiers:
    class CommandID(Enum):
        STATUS_PLEASE = b'\x31'
        POWER_ON = b'\x39'
        POWER_OFF = b'\x3a'
        SEARCH_FOR_FIRES = b'\x50'
        FAN_BOOST_ON = b'\x37'
        FAN_BOOST_OFF = b'\x38'
        FLAME_EFFECT_ON = b'\x56'
        FLAME_EFFECT_OFF = b'\x55'
        NEW_SET_TEMP = b'\x57'

    class ResponseID(Enum):
        STATUS = b'\x80'
        POWER_ON_ACK = b'\x8d'
        POWER_OFF_ACK = b'\x8f'
        FAN_BOOST_ON_ACK = b'\x8a'
        FAN_BOOST_OFF_ACK = b'\x8b'
        FLAME_EFFECT_ON_ACK = b'\x61'
        FLAME_EFFECT_OFF_ACK = b'\x60'
        NEW_SET_TEMP_ACK = b'\x66'
        I_AM_A_FIRE = b'\x99'


    # Acceptable limits when commanding NEW_SET_TEMP:
    MIN_SET_TEMP = 4
    MAX_SET_TEMP = 30

    def _initialise_data (self) -> None:
        """Default all attributes
        """
        self._id = None
        self._has_new_timers = None
        self._fan_boost_on = None
        self._effect_on = None
        self._desired_temp = None
        self._current_temp = None
        self._serial = None
        self._pin = None
        self._bytearray = None
        self._crc_sum = None

    def __init__(self, command: CommandID, set_temp: int = 20) -> None:
        """ Create a command (outgoing) message.
            The parameter *set_temp* only applies to command *NEW_SET_TEMP*
            Use the property bytearray_of to get the bytes to send.
        """
        self._initialise_data(self)

        self._id = command
        self._desired_temp = set_temp # Only used for NEW_SET_TEMP

        # Build outgoing message:

        self._bytearray = bytearray(self.MESSAGE_LENGTH)

        self._bytearray[self.MSG_OFFSET_START_BYTE] = self.MESSAGE_START_BYTE
        self._bytearray[self.MSG_OFFSET_END_BYTE] = self.MESSAGE_END_BYTE
        
        self._bytearray[self.MSG_OFFSET_ID] = self._id

        if self._id == self.CommandID.NEW_SET_TEMP:
            self._bytearray[self.MSG_OFFSET_DATA_LENGTH] = 1 # For the desired temperature (rest have no data)
            self._bytearray[self.MSG_OFFSET_DATA_START] = self._desired_temp

        # Calculate CRC
        self._crc_sum = 0
        for i in range(self.MSG_OFFSET_ID,self.MSG_OFFSET_DATA_END):
            self._crc_sum += self._bytearray[i]
        self._crc_sum = self._crc_sum % 255
        self._bytearray[self.MSG_OFFSET_CRC] = self._crc_sum
    
    def __init__(self, incoming: bytearray) -> None:
        """Create a response Message from incoming buffer
        
        Raises:
            ValueError if message content does not match specification
        """
        self._initialise_data(self)

        self._bytearray = incoming

        # Check message integrity
        if incoming.count != self.MESSAGE_LENGTH:
            raise ValueError('Message:'+bytearray+' Has incorrect message length: '+ incoming.count)


        if incoming[self.MSG_OFFSET_START_BYTE] != self.MESSAGE_START_BYTE:
            raise ValueError('Message:'+bytearray+' Has Invalid message start byte: ' + incoming[self.MESSAGE_START_BYTE])

        if incoming[self.MSG_OFFSET_END_BYTE] != self.MESSAGE_END_BYTE:
            raise ValueError('Message:'+bytearray+' Has Invalid message end byte: '+ incoming[self.MSG_OFFSET_END_BYTE])     

        # Check CRC
        self._crc_sum = 0
        for i in range(self.MSG_OFFSET_ID,self.MSG_OFFSET_DATA_END):
            self._crc_sum += incoming[i]

        self._crc_sum = self._crc_sum % 255
        if self._crc_sum != incoming[self.MSG_OFFSET_CRC]:
            raise ValueError('Message:'+bytearray+' Has Invalid CRC:' + incoming[self.MSG_OFFSET_CRC] + ' Expecting:'+ self._crc_sum)    

        self._id = self.ResponseID(incoming[self.MSG_OFFSET_ID])

        # Extract data
        if (self._id) == self.ResponseID.STATUS:
            if incoming[self.MSG_OFFSET_DATA_LENGTH] != 6:
                raise ValueError('Message:'+bytearray+' Has Invalid Data Length:' + incoming[self.MSG_OFFSET_DATA_LENGTH] + ' Expecting:'+ 6)   
            self._has_new_timers = bool(incoming[self.MSG_OFFSET_DATA_START+self.DATA_OFFSET_TIMERS])
            self._fire_on = bool(incoming[self.MSG_OFFSET_DATA_START+self.DATA_OFFSET_FIRE_ON])
            self._fan_boost_on = bool(incoming[self.MSG_OFFSET_DATA_START+self.DATA_OFFSET_BOOST_ON])
            self._effect_on = bool(incoming[self.MSG_OFFSET_DATA_START+self.DATA_OFFSET_EFFECT_ON])
            self._desired_temp = int(incoming[self.MSG_OFFSET_DATA_START+self.DATA_OFFSET_DESIRED_TEMP])
            self._current_temp = int(incoming[self.MSG_OFFSET_DATA_START+self.DATA_OFFSET_CURRENT_TEMP])

        elif (self._id) == self.ResponseID.I_AM_A_FIRE:
            if incoming[self.MSG_OFFSET_DATA_LENGTH] != 6:
                raise ValueError('Message:'+bytearray+' Has Invalid Data Length:' + incoming[self.MSG_OFFSET_DATA_LENGTH] + ' Expecting:'+ 6)
            self.serial = int.from_bytes(incoming[self.MSG_OFFSET_DATA_START+self.DATA_OFFSET_SERIAL:self.MSG_OFFSET_DATA_START+self.DATA_OFFSET_SERIAL+3], byteorder='big', signed=False)
            self._pin = int.from_bytes(incoming[self.MSG_OFFSET_DATA_START+self.DATA_OFFSET_PIN:self.MSG_OFFSET_DATA_START+self.DATA_OFFSET_PIN+1], byteorder='big', signed=False)

        else:
            if int(incoming[self.MSG_OFFSET_DATA_LENGTH]) != 0:
                 raise ValueError('Message:'+bytearray+' Has Invalid Data Length:' + int(incoming[self.MSG_OFFSET_DATA_LENGTH]) + ' Expecting:'+ 0)               

    @property
    def response_id(self) -> ResponseID:
        return self._id

    @property
    def has_new_timers(self) -> bool:
        return self._has_new_timers

    @property
    def fire_is_on(self) -> bool:
        return self._fire_on
    @property
    def fan_boost_is_on(self) -> bool:
        return self._fan_boost_on

    @property
    def flame_effect(self) -> bool:
        return self._effect_on

    @property
    def desired_temp(self) -> int:
        return self._desired_temp

    @property
    def current_temp(self) -> int:
        return self._current_temp

    @property
    def serial_number(self) -> int:
        return self._serial

    @property
    def pin(self) -> int:
        return self._pin

    @property
    def crc(self) -> int:
        return self.crc

    @property
    def expected_response(self) -> ResponseID:
        if self._id == self.CommandID.STATUS_PLEASE:
            return self.ResponseID.STATUS
        elif self._id == self.CommandID.POWER_ON:
            return self.ResponseID.POWER_ON_ACK
        elif self._id == self.CommandID.POWER_OFF:
            return self.ResponseID.POWER_OFF_ACK
        elif self._id == self.CommandID.SEARCH_FOR_FIRES:
            return self.ResponseID.I_AM_A_FIRE
        elif self._id == self.CommandID.FAN_BOOST_ON:
            return self.ResponseID.FAN_BOOST_ON_ACK
        elif self._id == self.CommandID.FAN_BOOST_OFF:
            return self.ResponseID.FAN_BOOST_OFF_ACK
        elif self._id == self.CommandID.FLAME_EFFECT_ON:
            return self.ResponseID.FLAME_EFFECT_ON_ACK
        elif self._id == self.CommandID.FLAME_EFFECT_OFF:
            return self.ResponseID.FLAME_EFFECT_OFF_ACK
        elif self._id == self.CommandID.NEW_SET_TEMP:
            return self.ResponseID.NEW_SET_TEMP_ACK
        else:
            raise(ValueError)

    @property
    def bytearray_of(self) -> bytearray:
        return self._bytearray
       