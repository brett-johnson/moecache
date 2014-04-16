moecache Module
===============

.. automodule:: moecache
    :members:
    :exclude-members: ClientException
    :show-inheritance:
    
    .. autoclass:: Client(servers[, hasher[, timeout[, connect_timeout]]])

       .. automethod:: set
       .. automethod:: get
       .. automethod:: delete
       .. automethod:: stats([additional_args])
       .. automethod:: close

    .. autoexception:: ClientException(msg[, item])
