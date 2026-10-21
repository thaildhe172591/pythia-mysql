-- Purpose: triggers as they were created: one by name, or every trigger on
--          a table, in the order they fire (visible only where this account
--          holds the TRIGGER privilege)
-- Binds:   %(s)s schema, %(n)s trigger name or NULL, %(t)s table or NULL
-- Returns: NAME, TIMING, EVENT, TABLE_NAME, ACTION_ORDER, BODY, DEFINER,
--          SQL_MODE
select trigger_name       as name,
       action_timing      as timing,
       event_manipulation as event,
       event_object_table as table_name,
       action_order       as action_order,
       action_statement   as body,
       definer            as definer,
       sql_mode           as sql_mode
  from information_schema.triggers
 where trigger_schema = %(s)s
   and (%(n)s is null or trigger_name = %(n)s)
   and (%(t)s is null or event_object_table = %(t)s)
 order by event_object_table,
          field(event_manipulation, 'INSERT', 'UPDATE', 'DELETE'),
          field(action_timing, 'BEFORE', 'AFTER'),
          action_order
