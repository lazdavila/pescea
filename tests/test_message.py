"""Test message encode / decode """

import pytest

from pescea.message import (
    Message,
    CommandID,
    ResponseID,
    MIN_SET_TEMP,
    MAX_SET_TEMP,
    MESSAGE_START_BYTE,
    MESSAGE_END_BYTE,
)


def test_valid_commands():
    # Test creation of every command type
    for command in CommandID:

        if command == CommandID.NEW_SET_TEMP:
            set_temp = MIN_SET_TEMP
        else:
            set_temp = None

        message = Message(command=command, set_temp=set_temp)

        assert message.command_id == command

        if command == CommandID.NEW_SET_TEMP:
            assert message.desired_temp == set_temp

        bytes = message.bytearray_

        assert bytes[0] == MESSAGE_START_BYTE, "Message start byte does not match"
        assert (
            bytes[len(bytes) - 1] == MESSAGE_END_BYTE
        ), "Message end byte does not match"
        assert bytes[1], command.value == "Message command code does not match"

        if command == CommandID.NEW_SET_TEMP:
            assert bytes[2] == 1, "Command data length must equal 1"
        else:
            assert bytes[2] == 0, "Command data length is non zero"


def test_invalid_commands():

    # Test temperatures out of range
    with pytest.raises(ValueError):
        message = Message(command=CommandID.NEW_SET_TEMP, set_temp=MIN_SET_TEMP - 1)

    with pytest.raises(ValueError):
        message = Message(command=CommandID.NEW_SET_TEMP, set_temp=MAX_SET_TEMP + 1)


def test_valid_responses():

    # Test creation of every response type
    for response in ResponseID:

        bytesequence = Message.mock_response(response_id=response)
        message = Message(incoming=bytesequence)

        assert message.response_id == response


def test_fire_status_response():

    # Test every attribute value
    for has_new_timers in (False, True):
        for fire_on in (False, True):
            for fan_boost_on in (False, True):
                for effect_on in (False, True):
                    for desired_temp in range(MIN_SET_TEMP, MAX_SET_TEMP):
                        for current_temp in range(MIN_SET_TEMP, MAX_SET_TEMP):

                            bytesequence = Message.mock_response(
                                response_id=ResponseID.STATUS,
                                has_new_timers=has_new_timers,
                                fire_on=fire_on,
                                fan_boost_on=fan_boost_on,
                                effect_on=effect_on,
                                desired_temp=desired_temp,
                                current_temp=current_temp,
                            )

                            message = Message(incoming=bytesequence)

                            assert message.current_temp == current_temp
                            assert message.desired_temp == desired_temp
                            assert message.flame_effect == effect_on
                            assert message.fan_boost_is_on == fan_boost_on
                            assert message.fire_is_on == fire_on
                            assert message.has_new_timers == has_new_timers


def test_invalid_responses():

    bytesequence = Message.mock_response(
        response_id=ResponseID.STATUS, force_crc_error=True
    )
    with pytest.raises(ValueError):
        message = Message(incoming=bytesequence)

    bytesequence = Message.mock_response(
        response_id=ResponseID.STATUS, force_id_error=True
    )
    with pytest.raises(ValueError):
        message = Message(incoming=bytesequence)

    bytesequence = Message.mock_response(
        response_id=ResponseID.STATUS, force_data_len_error=True
    )
    with pytest.raises(ValueError):
        message = Message(incoming=bytesequence)

    bytesequence = Message.mock_response(
        response_id=ResponseID.STATUS, force_start_byte_error=True
    )
    with pytest.raises(ValueError):
        message = Message(incoming=bytesequence)

    bytesequence = Message.mock_response(
        response_id=ResponseID.STATUS, force_end_byte_error=True
    )
    with pytest.raises(ValueError):
        message = Message(incoming=bytesequence)


def test_i_am_fire_response():

    uid = 123456

    bytesequence = Message.mock_response(response_id=ResponseID.I_AM_A_FIRE, uid=uid)
    message = Message(incoming=bytesequence)

    assert message.serial_number == uid
