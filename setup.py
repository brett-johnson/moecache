#!/usr/bin/env python

from distutils.core import setup

setup(name='memcache-client',
      version='0.1',
      description='A minimal pure Python client for Memcached, Kestrel, etc.',
      url='https://github.com/mixpanel/memcache_client',
      py_modules=['memcache', 'mock_memcached', 'test'],
     )
