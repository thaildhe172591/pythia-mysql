-- Purpose: the server's version, its build and the database this session is in
-- Binds:   none
-- Returns: VERSION, EDITION, DATABASE_NAME
select version()         as version,
       @@version_comment as edition,
       database()        as database_name
