-- Purpose: what MariaDB's catalog says depends on an object: the triggers on
--          a table and the tables whose foreign keys reference it. MariaDB
--          keeps no view usage tables: views are read in their definitions
--          (view-dependents.sql)
-- Binds:   %(s)s schema, %(n)s object name, %(t)s its type
-- Returns: SCHEMA_NAME, NAME, TYPE
select trigger_schema as schema_name, trigger_name as name, 'TRIGGER' as type
  from information_schema.triggers
 where event_object_schema = %(s)s
   and event_object_table = %(n)s
   and %(t)s = 'TABLE'
union
select constraint_schema, table_name, 'TABLE'
  from information_schema.referential_constraints
 where unique_constraint_schema = %(s)s
   and referenced_table_name = %(n)s
   and %(t)s = 'TABLE'
   and not (constraint_schema = %(s)s and table_name = %(n)s)
 order by 1, 2
