"""Test UDP datagram functionality """

from asyncio.transports import DatagramTransport
import pytest

import asyncio
 
from pescea.datagram import FireplaceDatagram, FireplaceMessage, CommandID

@pytest.mark.asyncio
async def test_datagram_send(mocker):

    class PatchedDatagramTransport(DatagramTransport):

        def __init__(self):
            self._command = None
            self._addr = None
            self._responses = []

        def sendto(self, data, addr=None):
            # data is bytearray
            self._command = FireplaceMessage( incoming= data)
            self._addr = addr

            if self._command.command_id == CommandID.SEARCH_FOR_FIRES:
                self._responses.append(FireplaceMessage.mock_response(self._command.expected_response, uid=1111))
                self._responses.append(FireplaceMessage.mock_response(self._command.expected_response, uid=2222))
                self._responses.append(FireplaceMessage.mock_response(self._command.expected_response, uid=3333))
            else:
                self._responses.append(FireplaceMessage.mock_response(self._command.expected_response))

        def close(self):
            return

        @property
        def next_response(self) -> FireplaceMessage:
            if len(self._responses) > 0:
                return self._responses.pop(0)

    async def patched_create_datagram_endpoint(
            self, protocol_factory,
            local_addr=None, remote_addr=None, *,
            family=0, proto=0, flags=0,
            reuse_address=None, reuse_port=None,
            allow_broadcast=None, sock=None):
        """A coroutine which creates a datagram endpoint.

        This method will try to establish the endpoint in the background.
        When successful, the coroutine returns a (transport, protocol) pair.

        protocol_factory must be a callable returning a protocol instance.

        socket family AF_INET, socket.AF_INET6 or socket.AF_UNIX depending on
        host (or family if specified), socket type SOCK_DGRAM.

        allow_broadcast tells the kernel to allow this endpoint to send
        messages to the broadcast address.
        """
        assert remote_addr is not None

        protocol = protocol_factory()
        transport = PatchedDatagramTransport()

        print("Datagram endpoint remote_addr created: "+str(remote_addr))
        # yield transport, protocol

        protocol.connection_made(transport)

        while True:
            await asyncio.sleep(0.2)
            next_response = transport.next_response
            if next_response is not None:
                break

        protocol.datagram_received(next_response, remote_addr)

        while True:
            await asyncio.sleep(0.2)
            next_response = transport.next_response
            if next_response is None:
                break
            else:
                protocol.datagram_received(next_response, remote_addr)

        # protocol.error_received(exc)
        # protocol.connection_lost(exc)

    event_loop = asyncio.get_event_loop()

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )

    datagram = FireplaceDatagram(event_loop, device_ip= '255.255.255.255')
    responses = await datagram.send_command(command = CommandID.SEARCH_FOR_FIRES)
    assert responses is None
