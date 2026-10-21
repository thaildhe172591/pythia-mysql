-- Purpose: what an event was created with (visible only where this account
--          holds the EVENT privilege)
-- Binds:   %(s)s schema, %(n)s event name
-- Returns: NAME, EVENT_TYPE, EXECUTE_AT, INTERVAL_VALUE, INTERVAL_FIELD,
--          STARTS, ENDS, ON_COMPLETION, STATUS, COMMENT, DEFINER, BODY,
--          SQL_MODE, TIME_ZONE
select event_name       as name,
       event_type       as event_type,
       execute_at       as execute_at,
       interval_value   as interval_value,
       interval_field   as interval_field,
       starts           as starts,
       ends             as ends,
       on_completion    as on_completion,
       status           as status,
       event_comment    as comment,
       definer          as definer,
       event_definition as body,
       sql_mode         as sql_mode,
       time_zone        as time_zone
  from information_schema.events
 where event_schema = %(s)s
   and event_name = %(n)s
