-- Purpose: what MariaDB's catalog says an object depends on: a trigger's
--          table and the tables a table's foreign keys reference. What a
--          view reads is in its definition (view-dependencies.sql)
-- Binds:   %(s)s schema, %(n)s object name, %(t)s its type
-- Returns: SCHEMA_NAME, NAME, TYPE
select event_object_schema as schema_name, event_object_table as name, 'TABLE' as type
  from information_schema.triggers
 where trigger_schema = %(s)s
   and trigger_name = %(n)s
   and %(t)s = 'TRIGGER'
union
select unique_constraint_schema, referenced_table_name, 'TABLE'
  from information_schema.referential_constraints
 where constraint_schema = %(s)s
   and table_name = %(n)s
   and %(t)s = 'TABLE'
   and not (unique_constraint_schema = %(s)s and referenced_table_name = %(n)s)
 order by 1, 2
