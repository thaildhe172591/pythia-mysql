-- Purpose: a sequence as MariaDB prints it: 10.11 has no catalog table for
--          sequences, and SHOW CREATE SEQUENCE carries the AS type, the
--          engine and the comment
-- Binds:   none: /*SEQUENCE*/ is the `schema`.`name` pythia quoted
-- Returns: TABLE, CREATE TABLE
show create sequence /*SEQUENCE*/
