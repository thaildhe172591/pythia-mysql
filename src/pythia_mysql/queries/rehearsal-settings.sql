-- Purpose: bound how long a write waits on a lock: a row lock (a rehearsal's
--          data change) or a table's metadata lock (DDL), 5 seconds each
-- Binds:   none
-- Returns: nothing
set session innodb_lock_wait_timeout = 5, session lock_wait_timeout = 5
