-- Purpose: where an unqualified name lands: the session's default database
-- Binds:   none
-- Returns: CURRENT_SCHEMA
select database() as current_schema
