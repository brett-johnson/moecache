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

import moecache

import socket
import time
import unittest

import helpers


# test memcached client for basic functionality
class TestClient(unittest.TestCase):

    @classmethod
    def setUpClass(c):
        c.memcached, c.port = helpers.start_new_memcached_server()

    @classmethod
    def tearDownClass(c):
        try:
            c.memcached.terminate()
        except:
            print 'for some reason memcached not running'
        c.memcached.wait()

    def setUp(self):
        self.client = moecache.Client(('127.0.0.1', self.port))

    def tearDown(self):
        self.client.close()

    def test_delete(self):
        key = 'delete'
        val = 'YBgGHw'
        self.client.set(key, val)
        mcval = self.client.get(key)
        self.assertEqual(mcval, val)
        self.client.delete(key)
        mcval = self.client.get(key)
        self.assertEqual(mcval, None)

    def test_expire(self):
        key = 'expire'
        val = "uiuokJ"
        self.client.set(key, val, exptime=1)
        time.sleep(2)
        mcval = self.client.get(key)
        self.assertEqual(mcval, None)

    def test_bad_expire(self):
        key = 'expire_bad'

        with helpers.expect(moecache.ValidationException):
            self.client.set(key, 'x', exptime=1.5)

        with helpers.expect(moecache.ValidationException):
            self.client.set(key, 'x', exptime=-1)

    def test_get_bad(self):
        self.assertRaises(Exception, self.client.get, 'get_bad\x84')
        mcval = self.client.get('!' * 250)
        self.assertEqual(mcval, None)
        self.assertRaises(Exception, self.client.get, '!' * 251)
        self.assertRaises(Exception, self.client.get, '')

        # this tests regex edge case specific to the impl
        self.assertRaises(Exception, self.client.get,
                          'get_bad_trailing_newline\n')

    def test_get_unknown(self):
        mcval = self.client.get('get_unknown')
        self.assertEqual(mcval, None)

    def test_set_bad(self):
        key = 'set_bad'
        self.assertRaises(Exception, self.client.set, key, '!' * 1024**2)
        # not sure why 1024**2 - 1 rejected
        self.client.set(key, '!' * (1024**2 - 100))
        self.assertRaises(Exception, self.client.set, '', 'empty key')

    def test_set_get(self):
        key = 'set_get'
        val = "eJsiIU"
        self.client.set(key, val)
        mcval = self.client.get(key)
        self.assertEqual(mcval, val)

    def test_stats(self):
        stats = self.client.stats()
        self.assertEqual(len(stats), 1)
        self.assertIn('total_items', stats[0])

    def test_stats_bad(self):
        with helpers.expect(moecache.ClientException):
            self.client.stats('kirihara')

    def test_bad_flags(self):
        self.client._nodes[0].connect()
        key = 'badflags'
        val = 'xcHJFd'

        def store(flag):
            command = 'set %s %d 60 %d\r\n%s\r\n' % (key, flag, len(val), val)
            self.client._nodes[0]._socket.sendall(command)
            rc = self.client._nodes[0].gets()
            self.assertEqual(rc, 'STORED\r\n')

        store(0)
        with helpers.expect(Exception):
            self.client.get(key)

        store(17 | 0x100)
        with helpers.expect(Exception):
            self.client.get(key)

    def test_str_only(self):
        self.assertRaises(Exception, self.client.set, u'unicode_key', 'sfdhjk')
        self.assertRaises(Exception, self.client.set, 'str_key', u'DFHKfl')


# make sure timeout works by using mock server
# test memcached failing in a variety of ways, coming back vs. not, etc
class TestFailures(unittest.TestCase):

    def test_gone(self):
        mock_memcached, port = helpers.start_new_memcached_server()
        try:
            client = moecache.Client(('127.0.0.1', port))
            key = 'gone'
            val = 'QWMcxh'
            client.set(key, val)

            mock_memcached.terminate()
            mock_memcached.wait()
            mock_memcached = None

            self.assertRaises(Exception, client.get, key)
            client.close()
        finally:
            if mock_memcached:
                mock_memcached.terminate()
                mock_memcached.wait()

    def test_hardfail(self):
        mock_memcached, port = helpers.start_new_memcached_server()
        try:
            client = moecache.Client(('127.0.0.1', port))
            key = 'hardfail'
            val = 'FuOIdn'
            client.set(key, val)

            mock_memcached.kill()  # sends SIGKILL
            mock_memcached.wait()
            mock_memcached, port = helpers.start_new_memcached_server(
                port=port)

            mcval = client.get(key)
            self.assertEqual(mcval, None)  # val lost when restarted
            client.close()
        finally:
            mock_memcached.terminate()
            mock_memcached.wait()


class TestTimeout(unittest.TestCase):

    # make sure mock server works
    def test_set_get(self):
        mock_memcached, port = helpers.start_new_memcached_server(mock=True)
        try:
            client = moecache.Client(('127.0.0.1', port))
            key = 'set_get'
            val = 'DhuWmC'
            client.set(key, val)
            mcval = client.get(key)
            self.assertEqual(val, mcval)
            client.close()
        finally:
            mock_memcached.terminate()
            mock_memcached.wait()

    def test_get_timeout(self):
        mock_memcached, port = helpers.start_new_memcached_server(
            mock=True, additional_args=['--get-delay', '2'])
        try:
            client = moecache.Client(('127.0.0.1', port), timeout=1)
            key = 'get_timeout'
            val = 'cMuBde'
            client.set(key, val)
            # when running unpatched eventlet,
            # the following will fail w/ socket.error, EAGAIN
            self.assertRaises(socket.timeout, client.get, key)
            client.close()
        finally:
            mock_memcached.terminate()
            mock_memcached.wait()


class TestConnectTimeout(unittest.TestCase):

    # to run these tests, you need specify an ip that will not allow tcp
    # from your machine to 11211
    # this is easiest way to test connect timeout, since has to happen at
    # kernel level (iptables etc)

    # appstage01 (external ip is firewalled, internal is not)
    unavailable_ip = '173.193.164.107'

    def test_connect_timeout(self):
        # using normal timeout

        # client usually does lazy connect, but we don't want to confuse
        # connect and non-connect timeout, so connect manually
        with moecache.Client((self.unavailable_ip, 11211), timeout=1) \
                as client:
            self.assertRaises(socket.timeout, client.stats)

    def test_connect_timeout2(self):
        # using connect timeout
        with moecache.Client((self.unavailable_ip, 11211), connect_timeout=1) \
                as client:
            self.assertRaises(socket.timeout, client.stats)
