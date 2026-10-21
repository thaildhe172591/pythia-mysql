-- Purpose: the parameters of a procedure or function, in order (position 0,
--          a function's return value, is in routine.sql)
-- Binds:   %(s)s schema, %(n)s routine name
-- Returns: ROUTINE_TYPE, POSITION, MODE, NAME, DATA_TYPE, CHARSET
select routine_type       as routine_type,
       ordinal_position   as position,
       parameter_mode     as mode,
       parameter_name     as name,
       dtd_identifier     as data_type,
       character_set_name as charset
  from information_schema.parameters
 where specific_schema = %(s)s
   and specific_name = %(n)s
   and ordinal_position > 0
 order by routine_type, ordinal_position
