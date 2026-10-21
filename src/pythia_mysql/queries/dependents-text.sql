-- Purpose: the procedures, functions, triggers and events, in every schema
--          but MySQL's own, whose body holds a name — leads the caller
--          confirms word by word, since MySQL records nothing of them
-- Binds:   %(p)s LIKE pattern built from the name ('!' escapes)
-- Returns: SCHEMA_NAME, NAME, TYPE, DEFINITION
select routine_schema as schema_name, routine_name as name, routine_type as type,
       routine_definition as definition
  from information_schema.routines
 where routine_schema not in ('mysql', 'sys', 'performance_schema', 'information_schema')
   and lower(routine_definition) like lower(%(p)s) escape '!'
union all
select trigger_schema, trigger_name, 'TRIGGER', action_statement
  from information_schema.triggers
 where trigger_schema not in ('mysql', 'sys', 'performance_schema', 'information_schema')
   and lower(action_statement) like lower(%(p)s) escape '!'
union all
select event_schema, event_name, 'EVENT', event_definition
  from information_schema.events
 where event_schema not in ('mysql', 'sys', 'performance_schema', 'information_schema')
   and lower(event_definition) like lower(%(p)s) escape '!'
 order by 1, 2
