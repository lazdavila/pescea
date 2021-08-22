'''

This module attempts to implement the solution suggested in:
https://bugs.python.org/issue23972

'''

import asyncio
import collections
import socket
import sys

from asyncio import futures
from asyncio.log import logger

version = sys.version_info
PY_3_5_plus = version > (3, 5, )


class PatchedLoop(asyncio.SelectorEventLoop):
    '''
    The create_datagram_endpoint method below is a modified version of the
    original in Python 3.6.0.a0 asyncio/base_events.py. However my local
    version of Python is 3.4.1 so the later (3.5+) additions are wrapped in
    a PY_3_5_plus check.

    This version can set the SO_REUSEPORT socket option prior to the call to
    bind. This capability is controlled by some new keyword arguments (e.g.
    reuse_address, reuse_port, and allow_broadcast).
    '''

    @asyncio.coroutine
    def create_datagram_endpoint(self, protocol_factory,
                                 local_addr=None, remote_addr=None, *,
                                 family=0, proto=0, flags=0,
                                 reuse_address=None, reuse_port=None,
                                 allow_broadcast=None, sock=None):
        """Create datagram connection."""
        if sock is None:
            if not (local_addr or remote_addr):
                if family == 0:
                    raise ValueError('unexpected address family')
                addr_pairs_info = (((family, proto), (None, None)),)
            else:
                # join address by (family, protocol)
                addr_infos = collections.OrderedDict()
                for idx, addr in ((0, local_addr), (1, remote_addr)):
                    if addr is not None:
                        assert isinstance(addr, tuple) and len(addr) == 2, (
                            '2-tuple is expected')

                        infos = yield from self.getaddrinfo(
                            *addr, family=family, type=socket.SOCK_DGRAM,
                            proto=proto, flags=flags)
                        if not infos:
                            raise OSError('getaddrinfo() returned empty list')

                        for fam, _, pro, _, address in infos:
                            key = (fam, pro)
                            if key not in addr_infos:
                                addr_infos[key] = [None, None]
                            addr_infos[key][idx] = address

                # each addr has to have info for each (family, proto) pair
                addr_pairs_info = [
                    (key, addr_pair) for key, addr_pair in addr_infos.items()
                    if not ((local_addr and addr_pair[0] is None) or
                            (remote_addr and addr_pair[1] is None))]

                if not addr_pairs_info:
                    raise ValueError('can not get address information')

            exceptions = []

            for ((family, proto),
                 (local_address, remote_address)) in addr_pairs_info:
                sock = None
                r_addr = None
                try:
                    sock = socket.socket(
                        family=family, type=socket.SOCK_DGRAM, proto=proto)
                    if reuse_address:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    if reuse_port:
                        if 'SO_REUSEPORT' in vars(socket):
                            sock.setsockopt(
                                socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                    if allow_broadcast:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    sock.setblocking(False)

                    if local_addr:
                        sock.bind(local_address)
                    if remote_addr:
                        yield from self.sock_connect(sock, remote_address)
                        r_addr = remote_address
                except OSError as exc:
                    if sock is not None:
                        sock.close()
                    exceptions.append(exc)
                except:
                    if sock is not None:
                        sock.close()
                    raise
                else:
                    break
            else:
                raise exceptions[0]
        else:
            if local_addr or remote_addr:
                raise ValueError(
                    'local_addr/remote_addr and sock can not be specified '
                    'at the same time')

        protocol = protocol_factory()
        if PY_3_5_plus:
            waiter = futures.Future(loop=self)
            transport = self._make_datagram_transport(sock, protocol, r_addr,
                                                      waiter)  # python 3.6
        else:
            transport = self._make_datagram_transport(sock, protocol, r_addr)

        if self._debug:
            if local_addr:
                logger.info("Datagram endpoint local_addr=%r remote_addr=%r "
                            "created: (%r, %r)",
                            local_addr, remote_addr, transport, protocol)
            else:
                logger.debug("Datagram endpoint remote_addr=%r created: "
                             "(%r, %r)",
                             remote_addr, transport, protocol)

        if PY_3_5_plus:
            try:
                yield from waiter
            except:
                transport.close()
                raise

        return transport, protocol


class PatchedEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    _loop_factory = PatchedLoop

# Now patch asyncio so we can create UDP sockets that are capable of binding
# to the same port on OSX.
asyncio.SelectorEventLoop = PatchedLoop

# Explicitly set the event loop policy to ensure the patched event 
# loop is used. This patch file should really be imported before any
# calls to asyncio.get_event_loop().
#
asyncio.DefaultEventLoopPolicy = PatchedEventLoopPolicy
asyncio.set_event_loop_policy(PatchedEventLoopPolicy())