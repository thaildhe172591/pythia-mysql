-- Purpose: the cipher this session's connection is encrypted with; empty
--          when it is not encrypted
-- Binds:   none
-- Returns: VARIABLE_NAME, VALUE
show session status where variable_name in ('Ssl_cipher', 'Ssl_version')
