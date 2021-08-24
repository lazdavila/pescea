"""Test UDP datagram functionality """
import asyncio
import pytest

from asyncio.transports import DatagramTransport
 
from pescea.datagram import REQUEST_TIMEOUT, FireplaceDatagram
from pescea.message import MIN_SET_TEMP, FireplaceMessage, CommandID, ResponseID, expected_response

class PatchedDatagramTransport(DatagramTransport):

    def __init__(self):
        self._command = None
        self._addr = None
        self._responses = []
        self._closed = False

    def sendto(self, data, addr=None):
        if self._closed:
            return

        # data is bytearray
        self._command = FireplaceMessage( incoming= data)
        self._addr = addr

        if self._command.command_id == CommandID.SEARCH_FOR_FIRES:
            self._responses.append((FireplaceMessage.mock_response(response_id= ResponseID.I_AM_A_FIRE, uid=1111), '192.168.0.111'))
            self._responses.append((FireplaceMessage.mock_response(response_id= ResponseID.I_AM_A_FIRE, uid=2222), '192.168.0.222'))
            self._responses.append((FireplaceMessage.mock_response(response_id= ResponseID.I_AM_A_FIRE, uid=3333), '192.168.0.33'))
        elif self._command.command_id == CommandID.STATUS_PLEASE:
            self._responses.append((FireplaceMessage.mock_response(response_id= ResponseID.STATUS, fire_on=True, desired_temp=MIN_SET_TEMP), '192.168.0.111'))
        else:
            self._responses.append((FireplaceMessage.mock_response(expected_response(self._command.command_id)), '192.168.0.111'))

    def close(self):
        self._closed = True

    @property
    def next_response(self):
        if self._closed or len(self._responses) == 0:
            return None, None

        response = self._responses.pop(0)
        return response[0], response[1]

async def simulate_comms(transport, protocol, broadcast : bool = False, raise_exception : Exception = None):
    """ Handles sending a reply based on command received """

    if raise_exception is not None:
        # protocol.error_received(exc)
        # protocol.connection_lost(exc)
        if raise_exception is TimeoutError:
           await asyncio.sleep(2*REQUEST_TIMEOUT) # exceed the timeout in request
        else:
            protocol.error_received(raise_exception)

    else:
        protocol.connection_made(transport)

        while True:
            # Wait for sendto to have been called (then have responses)
            await asyncio.sleep(0.1)
            next_response, addr = transport.next_response
            if next_response is not None:
                break

        protocol.datagram_received(next_response, addr)

        if broadcast:
            while True:
                await asyncio.sleep(0.1)
                next_response, addr = transport.next_response
                if next_response is None:
                    break
                else:
                    protocol.datagram_received(next_response, addr)

    await asyncio.sleep(0.1)
    protocol.connection_lost(None)

async def simulate_comms_patchable(transport, protocol, broadcast):
    """ Generic pattern, overwritten by tests to generate different results"""
    await simulate_comms(transport, protocol, broadcast)

async def simulate_comms_timeout_error(transport, protocol, broadcast):
    await simulate_comms(transport, protocol, broadcast, raise_exception = TimeoutError)

async def simulate_comms_connection_error(transport, protocol, broadcast):
    await simulate_comms(transport, protocol, broadcast, raise_exception = ConnectionError)    

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

    transport = PatchedDatagramTransport()
    protocol = protocol_factory()

    print("Datagram endpoint remote_addr created: "+str(remote_addr))

    asyncio.create_task(simulate_comms_patchable(transport, protocol, allow_broadcast))

    return transport, protocol


@pytest.mark.asyncio
async def test_search_for_fires(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )

    event_loop = asyncio.get_event_loop()

    datagram = FireplaceDatagram(event_loop, device_ip= '255.255.255.255')
    responses = await datagram.send_command(command = CommandID.SEARCH_FOR_FIRES, broadcast=True)
    assert len(responses) == 3
    assert responses['192.168.0.111'].serial_number == 1111
    assert responses['192.168.0.222'].serial_number == 2222
    assert responses['192.168.0.33'].serial_number == 3333
    
@pytest.mark.asyncio
async def test_get_status(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )

    event_loop = asyncio.get_event_loop()

    datagram = FireplaceDatagram(event_loop, device_ip= '192.168.0.111')
    responses = await datagram.send_command(command = CommandID.STATUS_PLEASE)
    assert len(responses) == 1
    assert responses['192.168.0.111'].fire_is_on
    assert responses['192.168.0.111'].desired_temp == MIN_SET_TEMP


@pytest.mark.asyncio
async def test_timeout_error(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )

    mocker.patch(
        __name__ + '.simulate_comms_patchable',
        simulate_comms_timeout_error
    )

    event_loop = asyncio.get_event_loop()

    datagram = FireplaceDatagram(event_loop, device_ip= '192.168.0.111')
    with pytest.raises(asyncio.TimeoutError):
        responses = await datagram.send_command(command = CommandID.STATUS_PLEASE)
    event_loop.stop()

 
@pytest.mark.asyncio
async def test_connection_error(mocker):

    mocker.patch(
        'pescea.datagram.asyncio.BaseEventLoop.create_datagram_endpoint',
        patched_create_datagram_endpoint
    )

    mocker.patch(
        __name__ + '.simulate_comms_patchable',
        simulate_comms_connection_error
    )

    event_loop = asyncio.get_event_loop()

    datagram = FireplaceDatagram(event_loop, device_ip= '192.168.0.111')
    responses = await datagram.send_command(command = CommandID.STATUS_PLEASE)
    assert len(responses) == 0
