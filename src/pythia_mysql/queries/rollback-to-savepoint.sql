-- Purpose: undo the probing run; MySQL warns (1196) when a table it changed
--          cannot be rolled back
-- Binds:   none
-- Returns: nothing
rollback to savepoint pythia_rehearsal
