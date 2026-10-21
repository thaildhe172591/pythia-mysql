-- Purpose: every view MySQL marks invalid now, in every schema but its own —
--          read before a DDL statement and after it
-- Binds:   none
-- Returns: SCHEMA_NAME, NAME, MESSAGE
select table_schema  as schema_name,
       table_name    as name,
       table_comment as message
  from information_schema.tables
 where table_type = 'VIEW'
   and table_comment <> 'VIEW'
   and table_schema not in ('mysql', 'sys', 'performance_schema', 'information_schema')
 order by 1, 2
