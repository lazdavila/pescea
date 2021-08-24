"""Escea Fireplace UDP messaging module

   Implements simple UDP messages to Fireplace and receiving responses
"""

import asyncio

from asyncio import  Future, DatagramTransport
from asyncio.base_events import BaseEventLoop

from async_timeout import timeout
from typing import Any, Dict

# Pescea imports:
from .message import FireplaceMessage, CommandID

import logging
_LOG = logging.getLogger("pescea.datagram")

# Port to use for discovery and integration
CONTROLLER_PORT = 3300

# Time to wait for results from server
REQUEST_TIMEOUT = 6

class FireplaceDatagram:
    """ Send UDP Datagrams to fireplace and receive responses """

    MultipleResponses = Dict[str, FireplaceMessage]

    def __init__(self, event_loop: BaseEventLoop, device_ip: str) -> None:
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

        self._sending_lock = asyncio.Lock()

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
        """
        loop = self._event_loop
        on_complete = loop.create_future()
        device_ip = self._ip

        message = FireplaceMessage(command=command, set_temp=data)

        responses = dict()   # type: self.MultipleResponses

        class _DatagramProtocol:
            def __init__(self, message : FireplaceMessage, on_complete: Future):
                self._message = message
                self._on_complete = on_complete
                self._transport = None

            def connection_made(self, transport: DatagramTransport):
                self._transport = transport
                self._transport.sendto(self._message.bytearray_)

            def datagram_received(self, data, addr):
                response = FireplaceMessage(incoming=data)
                if response.response_id != self._message.expected_response:
                    _LOG.error(
                        "Message response id: %s does not match command id: %s",
                        response.response_id, self._message.command_id)
                responses[addr] = response
                if command != CommandID.SEARCH_FOR_FIRES:
                    self._transport.close()

            def error_received(self, exc):
                _LOG.warning(
                    "Error sending command=%s failed with exception: %s",
                    self._message.command_id, str(exc))

            def connection_lost(self, exc):
                self._on_complete.set_result(True)

        try:
            async with timeout(REQUEST_TIMEOUT) as cm:
                transport, _ = await loop.create_datagram_endpoint(
                    lambda: _DatagramProtocol(message, on_complete),
                    remote_addr=(device_ip, CONTROLLER_PORT),
                    allow_broadcast=broadcast)

                # wait for response to be received.
                await on_complete

            if cm.expired:
                if transport:
                    transport.close()
                raise TimeoutError()

            on_complete.result()

            return responses

        except (OSError, TimeoutError) as ex:
            raise ConnectionError("Unable to send UDP") from ex

    """ The rest of this module is to support testing """

    def dump(self, indent: str = '') -> None:
        tab = "    "
        print(indent + "FireplaceDatagram:")
        print(indent + tab + "Device IP: {0}".format(self._ip))
        print(indent + tab + "Event Loop: {0}".format(self._event_loop))
        if self._fail_exception is not None:
            print(indent + tab +
                  "Fail Exception: {0}".format(self._fail_exception))
        print(indent + tab + "Sending Lock: {0}".format(self._sending_lock))
