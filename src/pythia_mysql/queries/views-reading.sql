-- Purpose: the views that read one table or view
-- Binds:   %(s)s its schema, %(n)s its name
-- Returns: SCHEMA_NAME, NAME
select view_schema as schema_name, view_name as name
  from information_schema.view_table_usage
 where table_schema = %(s)s
   and table_name = %(n)s
 order by 1, 2
