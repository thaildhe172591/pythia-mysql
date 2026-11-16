-- Purpose: the server settings check reports beside the session: connection
--          headroom, whether the server forces TLS, the TLS versions it
--          speaks, and whether this session is read-only. Read by name, so
--          a variable a version lacks (have_ssl left in 8.4) is simply
--          absent, never an error
-- Binds:   none
-- Returns: VARIABLE_NAME, VALUE
show variables where variable_name in ('max_connections', 'require_secure_transport',
                                       'tls_version', 'transaction_read_only')
