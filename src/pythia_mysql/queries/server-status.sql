-- Purpose: connection headroom on the server: how many are connected now,
--          the most ever at once (and when, on MySQL), and how many were
--          refused at the max_connections cap since the server started
-- Binds:   none
-- Returns: VARIABLE_NAME, VALUE
show global status where variable_name in ('Threads_connected', 'Max_used_connections',
                                           'Max_used_connections_time',
                                           'Connection_errors_max_connections')
