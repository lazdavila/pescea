import asyncio
import logging

from asyncio import Event, sleep, Semaphore
from asyncio.transports import DatagramTransport
from async_timeout import timeout

from pescea.datagram import CONTROLLER_PORT
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


class SimulatedComms:
    """ Sets up a simulated local/remote UDP endpoint representing a fireplace
    """

    def __init__(self):
        self.command = None
        self.uid = None
        self.responses = []
        self.responses_ready = None
        self.remote_addr = None
        self.broadcast = None
        self.local_addr = None
        self.loop = None

    async def initialize(self, host, port, remote,
        endpoint_factory, loop,
        **kwargs):

        assert port == CONTROLLER_PORT
        if (self.responses_ready is None) or (self.loop != loop):
            self.loop = loop
            self.responses_ready = Semaphore(value=0, loop=loop)

        if remote:
            if kwargs.__contains__('allow_broadcast'):
                self.broadcast = kwargs['allow_broadcast']
            else:
                self.broadcast = False
            self.uid = None            
            for uid in fireplaces:
                if fireplaces[uid]['IPAddress'] == host:
                    self.uid = uid
                    break
            self.remote_addr = host
            assert host is not None

        else:  # local
            self.local_addr = host
            assert host == '0.0.0.0'
            # flush any responses not previously read
            while len(self.responses) > 0:
                self.responses.pop(0)
            while not self.responses_ready.locked():
                await self.responses_ready.acquire()

        _LOG.debug(
            'Datagram endpoint created: (%s, %s)', str(host), str(port))

    def send(self, data):

        # data is bytearray
        self.command = FireplaceMessage(incoming=data)

        # Prepare responses (broadcast, with multiple responses)
        if self.command.command_id == CommandID.SEARCH_FOR_FIRES:
            # It is a broadcast, so our first response is the actual outbound message
            self.responses.append((data, (self.local_addr, CONTROLLER_PORT)))
            self.responses_ready.release()

            for uid in fireplaces:
                if fireplaces[uid]['Responsive'] and (self.uid is None or self.uid == uid):
                    self.responses.append((FireplaceMessage.mock_response(response_id= ResponseID.I_AM_A_FIRE, uid=uid), (fireplaces[uid]['IPAddress'], CONTROLLER_PORT)))
                    self.responses_ready.release()

        elif not self.uid is None and fireplaces[self.uid]['Responsive']:
            
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
                    (fireplaces[self.uid]['IPAddress'], CONTROLLER_PORT)
                ))

            else:
                self.responses.append((FireplaceMessage.mock_response(expected_response(self.command.command_id)), (fireplaces[self.uid]['IPAddress'], CONTROLLER_PORT)))
            
            self.responses_ready.release()

    def close(self):
        pass

    async def receive(self):
        await self.responses_ready.acquire()
        response = self.responses.pop(0)
        return response[0], response[1]

simulated_comms = SimulatedComms()

async def patched_open_datagram_endpoint(
        host, port, remote,
        endpoint_factory, loop,
        **kwargs):
    """Open and return a datagram endpoint.
    The default endpoint factory is the Endpoint class.
    The endpoint can be made local or remote using the remote argument.
    Extra keyword arguments are forwarded to `loop.create_datagram_endpoint`.
    """
    global simulated_comms
    
    await simulated_comms.initialize(host, port, endpoint_factory, remote, loop, **kwargs)
    
    return simulated_comms
