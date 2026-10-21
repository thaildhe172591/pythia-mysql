-- Purpose: what one object depends on, as MySQL records it: the tables,
--          views and functions a view reads (UNRESOLVED when one is gone),
--          the table a trigger is on, the tables a table's foreign keys
--          point at
-- Binds:   %(s)s the object's schema, %(n)s its name, %(t)s its type
-- Returns: SCHEMA_NAME, NAME, TYPE
select u.table_schema as schema_name, u.table_name as name,
       case t.table_type when 'VIEW' then 'VIEW'
                         when 'BASE TABLE' then 'TABLE'
                         else 'UNRESOLVED' end as type
  from information_schema.view_table_usage u
  left join information_schema.tables t
         on t.table_schema = u.table_schema and t.table_name = u.table_name
 where u.view_schema = %(s)s
   and u.view_name = %(n)s
   and %(t)s = 'VIEW'
union
select r.specific_schema, r.specific_name, 'FUNCTION'
  from information_schema.view_routine_usage r
 where r.table_schema = %(s)s
   and r.table_name = %(n)s
   and %(t)s = 'VIEW'
union
select event_object_schema, event_object_table, 'TABLE'
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
