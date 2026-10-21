-- Purpose: a table's comment, as a write to it snapshots and reads it back
-- Binds:   %(s)s schema, %(n)s table name
-- Returns: COMMENT
select table_comment as comment
  from information_schema.tables
 where table_schema = %(s)s
   and table_name = %(n)s
   and table_type = 'BASE TABLE'
