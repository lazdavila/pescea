import asyncio
import logging

from asyncio import Event, sleep
from asyncio.transports import DatagramTransport
from async_timeout import timeout

import pescea.datagram
from pescea.message import FireplaceMessage, CommandID, ResponseID, expected_response

def get_test_fireplaces():
    """Fixture to return a set of fireplaces to test with"""
    return {
        1111: {
            'IPAddress': '8.8.8.8',
            'HasNewTimers': False,
            'FireIsOn': False,
            'FanBoost': False,
            'FlameEffect': False,
            'DesiredTemp': 19.0,
            'CurrentTemp': 16.0,
            'Responsive': True
        },
        2222: {
            'IPAddress': '8.8.4.4',
            'HasNewTimers': False,
            'FireIsOn': True,
            'FanBoost': False,
            'FlameEffect': True,
            'DesiredTemp': 24.0,
            'CurrentTemp': 22.0,
            'Responsive': True
        },
        33333: {
            'IPAddress': '8.8.8.4',
            'HasNewTimers': True,
            'FireIsOn': False,
            'FanBoost': True,
            'FlameEffect': False,
            'DesiredTemp': 20.0,
            'CurrentTemp': 20.0,
            'Responsive': True
        }
    }

fireplaces = get_test_fireplaces()

def reset_fireplaces():
    global fireplaces
    fireplaces = get_test_fireplaces()

_LOG = logging.getLogger('tests.conftest')  # type: logging.Logger

class PatchedDatagramTransport(DatagramTransport):
    """ Sets up a patched version of DataTransport used to simulate comms to a fireplace.

        Implements sendto and close part of the Datagram Transport.
    
        Simulated responses are generated here, but provided via sends_comms below
    """
    def __init__(self):
        self.command = None
        self.uid = None
        self.responses = []
        self.closed = False
        self.response_is_ready = Event()

    def sendto(self, data, addr=None):
        if self.closed:
            return

        # data is bytearray
        self.command = FireplaceMessage( incoming= data)

        # Prepare responses (broadcast, with multiple responses)
        if self.command.command_id == CommandID.SEARCH_FOR_FIRES:
            for uid in fireplaces:
                if fireplaces[uid]['Responsive'] and (self.uid == 0 or self.uid == uid):
                    self.responses.append((FireplaceMessage.mock_response(response_id= ResponseID.I_AM_A_FIRE, uid=uid), fireplaces[uid]['IPAddress']))

        elif self.uid !=0:
            
            # Update internal simulated state
            if self.command.command_id == CommandID.FAN_BOOST_OFF:
                fireplaces[self.uid]['FanBoost'] = False
            elif self.command.command_id == CommandID.FAN_BOOST_ON:
                fireplaces[self.uid]['FanBoost'] = True
            elif self.command.command_id == CommandID.FLAME_EFFECT_OFF:
                fireplaces[self.uid]['FlameEffect'] = False
            elif self.command.command_id == CommandID.FLAME_EFFECT_ON:
                fireplaces[self.uid]['FlameEffect'] = True    
            elif self.command.command_id == CommandID.POWER_ON:
                fireplaces[self.uid]['FireIsOn'] = True
            elif self.command.command_id == CommandID.POWER_OFF:
                fireplaces[self.uid]['FireIsOn'] = False
            elif self.command.command_id == CommandID.NEW_SET_TEMP:
                fireplaces[self.uid]['DesiredTemp'] = int(self.command.desired_temp)
                fireplaces[self.uid]['CurrentTemp'] = int((self.command.desired_temp + fireplaces[self.uid]['CurrentTemp']) / 2.0)

            if self.command.command_id == CommandID.STATUS_PLEASE:
                self.responses.append((
                    FireplaceMessage.mock_response(
                        response_id= ResponseID.STATUS,
                        uid= self.uid,
                        has_new_timers= fireplaces[self.uid]['HasNewTimers'],
                        fire_on=fireplaces[self.uid]['FireIsOn'], 
                        fan_boost_on=fireplaces[self.uid]['FanBoost'], 
                        effect_on=fireplaces[self.uid]['FlameEffect'], 
                        desired_temp=int(fireplaces[self.uid]['DesiredTemp']),
                        current_temp=int(fireplaces[self.uid]['CurrentTemp'])), 
                    fireplaces[self.uid]['IPAddress']
                ))

            else:
                self.responses.append((FireplaceMessage.mock_response(expected_response(self.command.command_id)), fireplaces[self.uid]['IPAddress']))

        # Notify data is ready to collect
        self.response_is_ready.set()

    def close(self):
        self.closed = True

    @property
    def next_response(self):
        if self.closed or len(self.responses) == 0 \
            or (self.uid != 0 and not fireplaces[self.uid]['Responsive']):
            return None, None

        response = self.responses.pop(0)
        return response[0], response[1]

async def simulate_comms(transport, protocol, broadcast : bool = False, raise_exception : Exception = None):
    """ Handles sending a reply based on command received
    
        Implements the connection_made, datagram_received, error_received
        and connection_lost methods.
        
        The other protocol methods are implemented in PatchedDatagramProtocol above
    """

    if (raise_exception is not None) or (transport.uid == 0 and not broadcast):
        # simulate an exception condition
        if raise_exception is not TimeoutError:
            # simulate exception through the protocol
            protocol.error_received(raise_exception)
        else:
           await sleep(1.2*pescea.datagram.REQUEST_TIMEOUT) # exceed the timeout in request

    else:
        protocol.connection_made(transport)

        await transport.response_is_ready.wait()
        transport.response_is_ready.clear()
        next_response, addr = transport.next_response

        if next_response is not None:
            protocol.datagram_received(next_response, addr)

            if broadcast:
                while True:
                    next_response, addr = transport.next_response
                    if next_response is None:
                        break
                    else:
                        protocol.datagram_received(next_response, addr)

    protocol.connection_lost(raise_exception)

async def simulate_comms_patchable(transport, protocol, broadcast):
    """ Generic pattern, overwritten by tests to generate different results"""
    await simulate_comms(transport, protocol, broadcast)

async def simulate_comms_timeout_error(transport, protocol, broadcast):
    await simulate_comms(transport, protocol, broadcast, raise_exception = TimeoutError)

async def simulate_comms_connection_error(transport, protocol, broadcast):
    await simulate_comms(transport, protocol, broadcast, raise_exception = ConnectionError)

async def patched_create_datagram_endpoint(
        self, protocol_factory,
        local_addr=None, remote_addr=None,
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
    transport.uid = 0
    # if not allow_broadcast:
    for uid in fireplaces:
        if fireplaces[uid]['IPAddress'] == remote_addr[0]:
            transport.uid = uid
            break

    protocol = protocol_factory()

    _LOG.debug(
        'Datagram endpoint remote_addr created: %s',str(remote_addr))

    asyncio.create_task(simulate_comms_patchable(transport, protocol, allow_broadcast))

    return transport, protocol
