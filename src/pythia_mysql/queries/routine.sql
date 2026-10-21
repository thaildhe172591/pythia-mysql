-- Purpose: what a procedure or function was created with: its body as
--          written (NULL unless this account defined it, or holds
--          SHOW_ROUTINE or a global SELECT), and the clauses around it
-- Binds:   %(s)s schema, %(n)s routine name
-- Returns: TYPE, NAME, RETURNS, RETURNS_CHARSET, IS_DETERMINISTIC,
--          DATA_ACCESS, SECURITY, COMMENT, DEFINER, SQL_MODE, LANGUAGE, BODY,
--          SCHEMA_CHARSET
select r.routine_type       as type,
       r.routine_name       as name,
       r.dtd_identifier     as returns,
       r.character_set_name as returns_charset,
       r.is_deterministic   as is_deterministic,
       r.sql_data_access    as data_access,
       r.security_type      as security,
       r.routine_comment    as comment,
       r.definer            as definer,
       r.sql_mode           as sql_mode,
       r.external_language  as language,
       r.routine_definition as body,
       s.default_character_set_name as schema_charset
  from information_schema.routines r
  join information_schema.schemata s on s.schema_name = r.routine_schema
 where r.routine_schema = %(s)s
   and r.routine_name = %(n)s
 order by r.routine_type desc
