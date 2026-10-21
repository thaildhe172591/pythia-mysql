-- Purpose: the code of a schema `errors` cannot check: MySQL resolves the
--          names inside a procedure, function, trigger or event only when
--          it runs
-- Binds:   %(s)s schema
-- Returns: NAME, TYPE
select routine_name as name, routine_type as type
  from information_schema.routines
 where routine_schema = %(s)s
union all
select trigger_name, 'TRIGGER'
  from information_schema.triggers
 where trigger_schema = %(s)s
union all
select event_name, 'EVENT'
  from information_schema.events
 where event_schema = %(s)s
 order by 1, 2
