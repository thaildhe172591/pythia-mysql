-- Purpose: whether one view still opens, inside a write's transaction:
--          selected with LIMIT 0, which commits nothing. CHECK TABLE says
--          more, but commits the transaction it runs in — the rows a release
--          has rehearsed would land — so it runs only in errors' read session
-- Binds:   none: /*VIEW*/ is the `schema`.`view` pythia quoted
-- Returns: the view's columns, no rows
select * from /*VIEW*/ limit 0
