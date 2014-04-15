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

import random
import unittest

import helpers


# test moecache client-side sharding
class TestSharding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servers = map(helpers.start_new_memcached_server,
                          random.sample(range(11213, 11314), 4))

    @classmethod
    def tearDownClass(cls):
        for memcached, _ in cls.servers:
            try:
                memcached.terminate()
            except:
                print 'for some reason memcached not running'
            else:
                memcached.wait()

    def setUp(self):
        self.client = moecache.Client([('127.0.0.1', port)
                                       for _, port in self.servers])

    def tearDown(self):
        self.client.close()

    def test_random(self):
        pairs = [(helpers.random_key(), str(n)) for n in range(100)]
        visible_pairs = dict(pairs).items()

        for k, v in pairs:
            self.client.set(k, v, exptime=60)

        for k, v in visible_pairs:
            cached_v = self.client.get(k)
            self.assertEqual(cached_v, v)

        for k, _ in visible_pairs:
            self.client.delete(k)

        for k, _ in visible_pairs:
            self.assertIsNone(self.client.get(k))

    def test_stats(self):
        stats = self.client.stats('items')
        self.assertEqual(stats, [{}] * 4)
