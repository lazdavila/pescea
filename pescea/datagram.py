"""Escea Fireplace UDP messaging module

   Implements simple UDP messages to Fireplace and receiving responses
"""

import asyncio
import logging

from asyncio import Lock
from asyncio.base_events import BaseEventLoop
from async_timeout import timeout
from typing import Any, Dict

# Pescea imports:
from .message import Message, CommandID, ResponseID, expected_response
from .udp_endpoints import open_local_endpoint, open_remote_endpoint


_LOG = logging.getLogger(__name__)

# Port used for discovery and integration
# (same port is used for replies)
CONTROLLER_PORT = 3300

# Time to wait for results from server
REQUEST_TIMEOUT = 5.0

Responses = Dict[str, Message]


class Datagram:
    """Send UDP Datagrams to fireplace and receive responses"""

    def __init__(
        self, event_loop: BaseEventLoop, device_ip: str, sending_lock: Lock
    ) -> None:
        """Create a simple datagram client interface.

        Args:
            event_loop: loop to use for coroutines
            device_addr: Device network address. Usually specified as IP
                address (can be a broadcast address in the case of fireplace search)
            sending_lock: Provided to attempt to make thread safe

        Raises:
            ConnectionRefusedError: If no Escea fireplace is discovered, or no
                device discovered at the given IP address, or the UID does not match
        """
        self._ip = device_ip
        self._event_loop = event_loop
        self.sending_lock = sending_lock

    @property
    def ip(self) -> str:
        """Target IP address"""
        return self._ip

    def set_ip(self, ip_addr: str) -> None:
        """Change the Target IP address"""
        self._ip = ip_addr

    async def send_command(self, command: CommandID, data: Any = None) -> Responses:
        """Send command via UDP
        Returns received response(s) and IP addresses they come from

        Args:
        - command: Fireplace command (refer Message)
        - data: ignored except for setting desired temperature

        Raises ConnectionError if unable to send command
        """
        message = Message(command=command, set_temp=data)
        responses = dict()  # type: Responses
        broadcast = command == CommandID.SEARCH_FOR_FIRES

        # set up receiver before we send anything
        async with self.sending_lock:
            try:
                local = await open_local_endpoint(
                    "0.0.0.0",
                    CONTROLLER_PORT,
                    loop=self._event_loop,
                    allow_broadcast=broadcast,
                )
                remote = await open_remote_endpoint(
                    self._ip,
                    CONTROLLER_PORT,
                    loop=self._event_loop,
                    allow_broadcast=broadcast,
                )
                remote.send(message.bytearray_)
                remote.close()
                async with timeout(REQUEST_TIMEOUT):
                    while True:

                        data, (addr, _) = await local.receive()
                        response = Message(incoming=data)
                        if response.is_command:
                            if not broadcast:
                                _LOG.error(
                                    "Unexpected command id: %s", response.command_id
                                )
                        else:  # response
                            if response.response_id != expected_response(command):
                                _LOG.debug(
                                    "Message response id: %s does not match command id: %s",
                                    response.response_id,
                                    command,
                                )
                            else:
                                responses[addr] = response
                        if not broadcast:
                            break
            except (asyncio.TimeoutError, ValueError):
                pass
            local.close()

        if len(responses) == 0:
            raise ConnectionError("Unable to send/receive UDP message")

        return responses
