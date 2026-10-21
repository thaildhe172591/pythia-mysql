-- Purpose: make every transaction of this session read-only: MySQL then
--          refuses INSERT, UPDATE, DELETE and every DDL statement (error
--          1792) — the read commands' second line of defence
-- Binds:   none
-- Returns: nothing
set session transaction read only
