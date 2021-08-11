"""Escea Fireplace UDP messaging module

   Implements simple UDP messages to Fireplace and receiving responses
"""

import asyncio
from asyncio import Lock

from async_timeout import timeout
from typing import Any, List, Dict

from .message import FireplaceMessage

import logging
_LOG = logging.getLogger("pescea.datagram")


class FireplaceDatagram:

    # Port to use for discovery and integration
    CONTROLLER_PORT = 3300    

    REQUEST_TIMEOUT = 5
    """Time to wait for results from server."""

    MultipleResponses = Dict[str, FireplaceMessage]

    def __init__(self, discovery, device_ip: str) -> None:
        """Create a simple datagram client interface.

        Args:
            device_addr: Device network address. Usually specified as IP
                address (can be a broadcast address in the case of fireplace search)

        Raises:
            ConnectionRefusedError: If no Escea fireplace is discovered, or no
                device discovered at the given IP address, or the UID does not match
        """
        self._ip = device_ip
        self._discovery = discovery

        self._fail_exception = None

        self._sending_lock = Lock()

    @property
    def ip(self) -> str:
        """Target IP address"""
        return self._ip

    def set_ip(self, ip_addr: str) -> None:
        """Set the Target IP address
        """
        self._ip = ip_addr

    async def _send_command_async(self, command: FireplaceMessage.CommandID, data: Any = None) -> MultipleResponses:
        """ Send command via UDP

            Returns received responses and IP addresses they come from
        """
        loop = self._discovery.loop
        on_complete = loop.create_future()
        device_ip = self._ip

        message = FireplaceMessage(command = command, set_temp = data)

        responses = dict()   # type: self.MultipleResponses

        class _DatagramProtocol:
            def __init__(self, message, on_complete):
                self.message = message
                self.on_complete = on_complete
                self.transport = None

            def connection_made(self, transport):
                self.transport = transport
                self.transport.sendto(self.message)

            def datagram_received(self, data, addr):
                response = FireplaceMessage(incoming = data)
                if response != self.message.expected_response:
                    _LOG.error(
                            "Message response id: %s does not match command id: %s",
                            response.response_id, command)
                responses[addr] = response
                if command != FireplaceMessage.CommandID.SEARCH_FOR_FIRES:
                    self.transport.close()

            def error_received(self, exc):
                _LOG.warning(
                        "Error receiving for uid=%s failed with exception: %s",
                        self.device_uid, exc.__repr__())

            def connection_lost(self, exc):
                self.on_complete.set_result(True)

        try:
            async with timeout(self.REQUEST_TIMEOUT) as cm:
                transport, _ = await loop.create_datagram_endpoint(
                    lambda: _DatagramProtocol(message.bytearray_of, on_complete),
                    remote_addr=(device_ip, self.CONTROLLER_PORT),
                    allow_broadcast=True)

                # wait for response to be received.
                await on_complete

            if cm.expired:
                if transport:
                    transport.close()
                raise asyncio.TimeoutError()

            on_complete.result()

            return responses

        except (OSError, asyncio.TimeoutError) as ex:
            raise ConnectionError("Unable to send UDP") from ex


    """ The rest of this module is to support testing """

    def dump(self, indent: str = '') -> None:
        tab = "    "
        print(indent + "FireplaceDatagram:")
        print(indent + tab + "Device IP: {0}".format(self._ip))
        print(indent + tab + "Discovery: {0}".format(self._discovery))
        if self._fail_exception is not None:
            print(indent + tab + "Fail Exception: {0}".format(self._fail_exception))
        print(indent + tab + "Sending Lock: {0}".format(self._sending_lock))