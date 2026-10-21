-- Purpose: the objects in a schema holding a name — tables, views and
--          MariaDB's sequences share one namespace, procedures, functions, triggers and events each
--          have their own — so the walks start from every one of them
-- Binds:   %(s)s schema, %(n)s object name (quoting already removed)
-- Returns: SCHEMA_NAME, NAME, TYPE
select table_schema as schema_name,
       table_name   as name,
       case table_type when 'VIEW' then 'VIEW'
                       when 'SEQUENCE' then 'SEQUENCE'
                       else 'TABLE' end as type
  from information_schema.tables
 where table_schema = %(s)s
   and table_name = %(n)s
union all
select routine_schema, routine_name, routine_type
  from information_schema.routines
 where routine_schema = %(s)s
   and routine_name = %(n)s
union all
select trigger_schema, trigger_name, 'TRIGGER'
  from information_schema.triggers
 where trigger_schema = %(s)s
   and trigger_name = %(n)s
union all
select event_schema, event_name, 'EVENT'
  from information_schema.events
 where event_schema = %(s)s
   and event_name = %(n)s
