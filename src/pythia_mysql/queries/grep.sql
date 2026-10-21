-- Purpose: the code of a schema — routine, trigger and event bodies, view
--          definitions — holding a text, in any case; the lines that hold
--          it are picked out by the caller
-- Binds:   %(s)s schema, %(p)s LIKE pattern built from the text ('!' escapes)
-- Returns: UNIT, TYPE, DEFINITION
select o.unit, o.type, o.definition
  from (select routine_name as unit, routine_type as type,
               routine_definition as definition
          from information_schema.routines
         where routine_schema = %(s)s
        union all
        select table_name, 'VIEW', view_definition
          from information_schema.views
         where table_schema = %(s)s
        union all
        select trigger_name, 'TRIGGER', action_statement
          from information_schema.triggers
         where trigger_schema = %(s)s
        union all
        select event_name, 'EVENT', event_definition
          from information_schema.events
         where event_schema = %(s)s) o
 where lower(o.definition) like lower(%(p)s) escape '!'
 order by o.unit, o.type
