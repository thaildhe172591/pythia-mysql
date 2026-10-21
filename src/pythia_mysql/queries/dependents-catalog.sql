-- Purpose: what depends on one object, as MySQL records it: views that read
--          a table or view, views that call a function, the triggers on a
--          table, tables whose foreign keys point at it. A procedure,
--          function, trigger or event body is recorded nowhere: the caller
--          searches those by name.
-- Binds:   %(s)s the object's schema, %(n)s its name, %(t)s its type
-- Returns: SCHEMA_NAME, NAME, TYPE
select u.view_schema as schema_name, u.view_name as name, 'VIEW' as type
  from information_schema.view_table_usage u
 where u.table_schema = %(s)s
   and u.table_name = %(n)s
   and %(t)s in ('TABLE', 'VIEW')
union
select r.table_schema, r.table_name, 'VIEW'
  from information_schema.view_routine_usage r
 where r.specific_schema = %(s)s
   and r.specific_name = %(n)s
   and %(t)s = 'FUNCTION'
union
select trigger_schema, trigger_name, 'TRIGGER'
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
