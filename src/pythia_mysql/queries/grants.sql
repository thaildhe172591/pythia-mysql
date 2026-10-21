-- Purpose: what this account holds, its active roles' privileges merged in:
--          MySQL hides from an account the routines, triggers and events it
--          holds no privilege to see, so the blind spots are read from here
-- Binds:   none
-- Returns: one GRANT statement per row
show grants
