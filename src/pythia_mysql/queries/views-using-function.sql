-- Purpose: the views that call one function
-- Binds:   %(s)s its schema, %(n)s its name
-- Returns: SCHEMA_NAME, NAME
select table_schema as schema_name, table_name as name
  from information_schema.view_routine_usage
 where specific_schema = %(s)s
   and specific_name = %(n)s
 order by 1, 2
