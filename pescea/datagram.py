"""Escea Fireplace UDP messaging module

   Implements simple UDP messages to Fireplace and receiving responses
"""

import asyncio
import sys
import socket

from asyncio import Lock
from asyncio.base_events import BaseEventLoop

from .udp_endpoints import open_local_endpoint, open_remote_endpoint

from async_timeout import timeout
from typing import Any, Dict

# Pescea imports:
from .message import FireplaceMessage, CommandID, ResponseID, expected_response

import logging
_LOG = logging.getLogger('pescea.datagram')

# Port to use for discovery and integration
CONTROLLER_PORT = 3300

# Time to wait for results from server
REQUEST_TIMEOUT = 5

MultipleResponses = Dict[str, FireplaceMessage]

class FireplaceDatagram:
    """ Send UDP Datagrams to fireplace and receive responses """

    def __init__(self, event_loop: BaseEventLoop, device_ip: str, sending_lock: Lock) -> None:
        """Create a simple datagram client interface.

        Args:
            device_addr: Device network address. Usually specified as IP
                address (can be a broadcast address in the case of fireplace search)

        Raises:
            ConnectionRefusedError: If no Escea fireplace is discovered, or no
                device discovered at the given IP address, or the UID does not match
        """
        self._ip = device_ip
        self._event_loop = event_loop
        self._fail_exception = None
        self.sending_lock = sending_lock

    @property
    def ip(self) -> str:
        """Target IP address"""
        return self._ip

    def set_ip(self, ip_addr: str) -> None:
        """Set the Target IP address
        """
        self._ip = ip_addr

    async def send_command(self, command: CommandID, data: Any = None, broadcast: bool = False) -> MultipleResponses:
        """ Send command via UDP

            Returns received responses and IP addresses they come from

            Raises ConnectionError if unable to send command
        """
        message = FireplaceMessage(command=command, set_temp=data)
        responses = dict()   # type: MultipleResponses

        # set up receiver before we send anything
        async with self.sending_lock:
            try:
                local = await open_local_endpoint('0.0.0.0', CONTROLLER_PORT, loop=self._event_loop, allow_broadcast=broadcast)  
                remote = await open_remote_endpoint(self._ip, CONTROLLER_PORT, loop=self._event_loop, allow_broadcast=broadcast)
                remote.send(message.bytearray_)      
                remote.close()
                async with timeout(REQUEST_TIMEOUT):
                    while True:

                        data, (addr, _) = await local.receive()
                        response = FireplaceMessage(incoming=data)
                        if response.is_command:
                            if not broadcast:
                                _LOG.error(
                                    'Unexpected command id: %s',
                                    response.command_id)
                        else: # response
                            if response.response_id != expected_response(command):
                                _LOG.debug(
                                    'Message response id: %s does not match command id: %s',
                                    response.response_id, command)
                            else:
                                responses[addr] = response
                        if command != CommandID.SEARCH_FOR_FIRES:
                            break
            except asyncio.TimeoutError:
                pass
            local.close()

        if len(responses) == 0:
            raise ConnectionError('Unable to send/receive UDP message')

        return responses
