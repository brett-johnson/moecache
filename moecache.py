# Copyright 2012 Mixpanel, Inc.
# Copyright 2014 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

'''
A memcached client with a different shading strategy.

Usage example::

    import moecache

    with moecache.Client([("127.0.0.1", 11211), ("127.0.0.1", 11213)],
                         timeout=1, connect_timeout=5) as mc:
        mc.set("some_key", "Some value")
        value = mc.get("some_key")
        mc.delete("another_key")

.. note::

    If the value to store is of type ``str``, the entry is binary compatible
    with EnyimMemcached; otherwise, the value will be "pickled" with protocol
    version 2 and can only be read by moecache.
'''

import errno
import re
import socket
import bisect
import sys

try:
    from __pypy__.builders import StringBuilder
    import pickle

    class OStringStream(object):
        def __init__(self):
            self.__b = StringBuilder()

        def write(self, s):
            self.__b.append(s)

        def getvalue(self):
            return self.__b.build()

    def pickle_dumps(obj):
        buf = OStringStream()
        pickler = pickle.Pickler(buf, 2)
        pickler.dump(obj)
        return buf.getvalue()

    from cPickle import loads as pickle_loads

except ImportError:
    try:
        from cStringIO import StringIO as OStringStream
        import cPickle

        def pickle_dumps(obj):
            return cPickle.dumps(obj, 2)

        pickle_loads = cPickle.loads

    except ImportError:
        from io import BytesIO as OStringStream
        import pickle

        def pickle_dumps(obj):
            return pickle.dumps(obj, 2)

        pickle_loads = pickle.loads


class ClientException(Exception):
    '''
    Raised when memcached does something we don't expect, or the
    memcached deployment is not compatible with moecache.

    .. note::

       This does not include `socket errors
       <http://docs.python.org/library/socket.html#socket.error>`_.
    '''

    def __init__(self, msg, item=None):
        if item is not None:
            msg += ': ' + repr(item)
        super(ClientException, self).__init__(msg)


class ValidationException(ClientException):
    '''
    Raised when the user input is invalid to this library.
    '''

    def __init__(self, msg, item):
        super(ValidationException, self).__init__(msg, item)


def fnv1a_32(seed=0x811c9dc5):
    def do_hash(s):
        hval = seed
        fnv_32_prime = 0x01000193

        for c in s:
            hval = hval ^ ord(c)
            hval = (hval * fnv_32_prime) & 0xffffffff

        return hval
    return do_hash


def _node_conf(timeout, connect_timeout):

    class Node(object):

        def __init__(self, addr):
            self._addr = addr
            self._socket = None

        def __str__(self):
            return ':'.join((self._addr[0], str(self._addr[1])))

        def __repr__(self):  # pragma: no cover
            return '<moecache.Node %s>' % self

        def connect(self):
            # buffer needed since we always ask for 4096 bytes at a time
            # thus, might read more than the current expected response
            # cleared on every reconnect since old bytes are part of old
            # session and can't be reused
            self._buffer = bytearray()

            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(connect_timeout)

            try:
                self._socket.connect(self._addr)
                self._socket.settimeout(timeout)
            except (socket.error, socket.timeout):
                self._socket = None  # don't want to hang on to bad socket
                raise

        def gets(self, length=None):
            '''
            Return the next length bytes from server, or, when length is
            ``None``, read a response delimited by \r\n and return it
            (including \r\n).

            Use latter only when \r\n is unambiguous -- aka for control
            responses, not data.
            '''
            result = None
            while result is None:
                if length:  # length = 0 is ambiguous, so don't use
                    if len(self._buffer) >= length:
                        result = bytes(self._buffer[:length])
                        self._buffer[:] = self._buffer[length:]
                else:
                    delim_index = self._buffer.find(b'\r\n')
                    if delim_index != -1:
                        result = bytes(self._buffer[:delim_index+2])
                        self._buffer[:] = self._buffer[delim_index+2:]

                if result is None:
                    try:
                        tmp = self._socket.recv(4096)
                    except (socket.error, socket.timeout) as e:
                        self.close()
                        raise e

                    if not tmp:
                        # we handle common close/retry cases in send(command)
                        # however, this can happen if server suddenly goes away
                        # (e.g. restarting memcached under sufficient load)
                        raise socket.error('unexpected socket close on recv')
                    else:
                        self._buffer += tmp
            return result

        def send(self, command):
            '''
            Send command to server and return initial response line.
            Will reopen socket if it got closed (either locally or by
            server).
            '''
            if self._socket:  # try to find out if the socket is still open
                try:
                    self._socket.settimeout(0)
                    self._socket.recv(1, socket.MSG_PEEK)
                    # if recv didn't raise, then the socket was closed or
                    # there is junk in the read buffer, either way, close
                    self.close()
                except socket.error as e:
                    if e.errno == errno.EAGAIN:
                        # this is expected if the socket is still open
                        self._socket.settimeout(timeout)
                    else:
                        self.close()

            if not self._socket:
                self.connect()

            self._socket.sendall(command)
            return self.gets()

        def close(self):
            '''
            Close the socket if opened.

            .. note::

               Sockets are opened the first time a command is run.

            Raises socket errors.
            '''
            if self._socket:
                self._socket.close()
                self._socket = None

    return Node


class Client(object):
    '''
    Creates an object to hold a moecache session.  The object is also
    a context manager, which automatically closes the sockets when the
    control leaves the :token:`with` statement.

    ``servers`` can be a single server, or a list of servers, where each
    server is a ``(host, port)`` tuple, same as a ``socket`` AF_INET
    address.

    If ``timeout`` is not specified, socket operations may block forever.
    If ``connect_timeout`` is not specified, the ``timeout`` setting will
    also be applied to the socket ``connect()`` operations.
    '''

    is_py3 = sys.version_info[0] == 3

    def __init__(self, servers, timeout=None, connect_timeout=None):
        _node_type = _node_conf(timeout, connect_timeout
                                if connect_timeout is not None
                                else timeout)
        self._nodes = list(map(_node_type, [servers]
                               if type(servers) is tuple else servers))
        self._servers = {}
        self._build_index(self._nodes)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    # key supports ascii sans space and control chars
    # \x21 is !, right after space, and \x7e is -, right before DEL
    # also 1 <= len <= 250 as per the spec
    _valid_key_re = re.compile('^[\x21-\x7e]{1,250}$')

    @classmethod
    def _validate_key(cls, key):
        if not isinstance(key, str):  # avoid bugs subtle and otherwise
            raise ValidationException('key must be str', key)
        m = cls._valid_key_re.match(key)
        if m:
            # in python re, $ matches either end of line or right before
            # \n at end of line. We can't allow latter case, so
            # making sure length matches is simplest way to detect
            if len(m.group(0)) != len(key):
                raise ValidationException('trailing newline', key)
        else:
            raise ValidationException('invalid key', key)

        if Client.is_py3:
            return key.encode()
        else:
            return key

    def _build_index(self, nodes):
        mutations = 100
        keys = []

        for node in nodes:
            tmp_keys = self._generate_keys(node, mutations)
            # XXX old mapping is not dropped
            for key in tmp_keys:
                self._servers[key] = node
            keys.extend(tmp_keys)

        self._keys = sorted(keys)

    # XXX
    # simulate a type of bug -- the hasher is not properly seeded
    # when the first time it's being used
    _uninitialized_hasher = staticmethod(fnv1a_32(0))
    _hasher = staticmethod(fnv1a_32())

    @classmethod
    def _generate_keys(cls, node, n):
        address = str(node)
        # XXX all servers but not the first one use the seeded hasher
        return ([cls._uninitialized_hasher(address + '-0')] +
                [cls._hasher('-'.join((address, str(i))))
                 for i in range(1, n)])

    def _find_node(self, key):
        key_hash = self._uninitialized_hasher(key)
        i = bisect.bisect_left(self._keys, key_hash)

        if i == len(self._keys):
            # largest key uses the first server
            i = 0
        elif i == 0 and self._keys[i] != key_hash:
            # smallest key uses the last server
            i = len(self._keys) - 1

        return self._servers[self._keys[i]]

    def close(self):
        '''
        Closes any opened socket.

        Sockets are automatically closed when the ``Client`` object gets
        out of the context.

        Raises socket errors.
        '''
        for node in self._nodes:
            node.close()

    def delete(self, key):
        '''
        Deletes a key/value pair.

        Raises ``ValidationException`` if ``key`` is invalid.  May also
        raise ``ClientException`` and socket errors.

        .. note:: The postcondition of this operation is that the entry no
            longer exists, so if the key does not exists at the first
            place, nothing happens and the function returns without error.
        '''
        # req  - delete <key> [noreply]\r\n
        # resp - DELETED\r\n
        #        or
        #        NOT_FOUND\r\n
        key_bytes = self._validate_key(key)

        command = b'delete ' + key_bytes + b'\r\n'
        resp = self._find_node(key).send(command)
        if resp != b'DELETED\r\n' and resp != b'NOT_FOUND\r\n':
            raise ClientException('delete failed', resp)

    def get(self, key):
        '''
        Gets a single value.  Returns :token:`None` if the key does not
        exist.

        Raises ``ValidationException`` if ``key`` is invalid.  May also
        raise ``ClientException`` and socket errors.
        '''
        # req  - get <key> [<key> ...]\r\n
        # resp - VALUE <key> <flags> <bytes> [<cas unique>]\r\n
        #        <data block>\r\n (if exists)
        #        [...]
        #        END\r\n
        key_bytes = self._validate_key(key)

        command = b'get ' + key_bytes + b'\r\n'

        val = None
        node = self._find_node(key)
        resp = node.send(command)
        error = None

        # make sure well-formed responses are all consumed
        while resp != b'END\r\n':
            terms = resp.split()
            if len(terms) == 4 and terms[0] == b'VALUE':  # exists
                typecode = int(terms[2]) ^ 0x100
                length = int(terms[3])
                if typecode > 0xff:
                    error = ClientException('not a moecache deployment')
                if terms[1] == key_bytes:
                    received = node.gets(length+2)[:-2]
                    if typecode == 18:
                        if Client.is_py3:
                            val = received.decode()
                        else:
                            val = received
                    elif typecode == 0:
                        val = pickle_loads(received)
                    else:
                        error = ClientException('unsupported data type',
                                                typecode)
                else:
                    error = ClientException('received unwanted response')
            else:
                raise ClientException('get failed', resp)
            resp = node.gets()

        if error is not None:
            # this can happen if a memcached instance contains items set
            # by a previous client
            # leads to subtle bugs, so fail fast
            raise error

        return val

    def set(self, key, val, exptime=0):
        '''
        Sets a key to a value with an optional expire time in seconds
        (0 means don't auto-expire).

        A valid ``key`` is a string with a minimal length of 1 and a
        maximal length of 250, and each character is an ASCII graph
        character (printable except spaces).

        A valid ``exptime`` is a non-negative integer.

        If any of these arguments is invalid, ``ValidationException`` will
        be raise.  May also raise ``ClientException`` and socket errors.
        '''
        # req  - set <key> <flags> <exptime> <bytes> [noreply]\r\n
        #        <data block>\r\n
        # resp - STORED\r\n (or others)
        key_bytes = self._validate_key(key)

        # typically, if val is > 1024**2 bytes server returns:
        #   SERVER_ERROR object too large for cache\r\n
        # however custom-compiled memcached can have different limit
        # so, we'll let the server decide what's too much

        if not isinstance(exptime, int):
            raise ValidationException('exptime not int', exptime)
        elif exptime < 0:
            raise ValidationException('exptime negative', exptime)

        if isinstance(val, str):
            flag = b' 274 '  # 18 | 0x100
            if Client.is_py3:
                sent = val.encode()
            else:
                sent = val
        else:
            flag = b' 256 '  # 0 | 0x100
            sent = pickle_dumps(val)

        buf = OStringStream()
        buf.write(b'set ')
        buf.write(key_bytes)
        buf.write(flag)
        buf.write(str(exptime).encode())
        buf.write(b' ')
        buf.write(str(len(sent)).encode())
        buf.write(b'\r\n')
        buf.write(sent)
        buf.write(b'\r\n')

        command = buf.getvalue()
        resp = self._find_node(key).send(command)
        if resp != b'STORED\r\n':
            raise ClientException('set failed', resp)

    def stats(self, additional_args=None):
        '''
        Aggregates the stats from all the servers.

        ``additional_args`` is a byte string being passed verbatim to the
        servers.  See `the memcached wiki
        <http://code.google.com/p/memcached/wiki/NewCommands#Statistics>`_
        for details or `the spec
        <https://github.com/memcached/memcached/blob/master/doc/protocol.txt>`_
        for even more details.

        Raises ``ClientException`` and socket errors.
        '''
        # req  - stats [additional args]\r\n
        # resp - STAT <name> <value>\r\n (one per result)
        #        END\r\n
        if additional_args is not None:
            if Client.is_py3:
                additional_args = additional_args.encode()
            command = b'stats ' + additional_args + b'\r\n'
        else:
            command = b'stats\r\n'

        def do_stats(node):
            resp = node.send(command)
            result = {}
            while resp != b'END\r\n':
                terms = resp.split()
                if len(terms) == 3 and terms[0] == b'STAT':
                    if Client.is_py3:
                        result[terms[1].decode()] = terms[2].decode()
                    else:
                        result[terms[1]] = terms[2]
                else:
                    raise ClientException('stats failed', resp)
                resp = node.gets()
            return result

        return list(map(do_stats, self._nodes))
