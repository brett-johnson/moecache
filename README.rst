**moecache** is a pure python client for memcached.  Its binary
protocol and shading strategy are compatible with EnyimMemcached
(a C# memcached client), so that you are can read/write an
EnyimMemcached-managed memcached deployment in Python.

The project is forked from **memcache_client**, a minimal and robust
python memcached client from Mixpanel, Inc.

The API looks very similar to the other memcached clients:

::

    import moecache

    with moecache.Client([("127.0.0.1", 11211), ("127.0.0.1", 11213)],
                         timeout=1, connect_timeout=5) as mc:
        mc.set("some_key", "Some value")
        value = mc.get("some_key")
        mc.delete("another_key")
