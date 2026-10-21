-- Purpose: what a view was created with. MySQL keeps the SELECT rewritten,
--          names qualified, never the text as typed.
-- Binds:   %(s)s schema, %(n)s view name
-- Returns: NAME, DEFINITION, CHECK_OPTION, SECURITY, DEFINER
select table_name      as name,
       view_definition as definition,
       check_option    as check_option,
       security_type   as security,
       definer         as definer
  from information_schema.views
 where table_schema = %(s)s
   and table_name = %(n)s
