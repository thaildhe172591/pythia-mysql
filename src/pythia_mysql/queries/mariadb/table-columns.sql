-- Purpose: a table's columns, as MariaDB keeps them: COLUMN_DEFAULT is
--          already SQL (a string quoted, NULL written 'NULL', an expression
--          as it is), and there is no SRS id
-- Binds:   %(s)s schema, %(n)s table name
-- Returns: NAME, TYPE, NULLABLE, DEFAULT_VALUE, EXTRA, GENERATION, CHARSET,
--          COLLATION, COMMENT, SRS_ID
select column_name           as name,
       column_type           as type,
       is_nullable           as nullable,
       column_default        as default_value,
       extra                 as extra,
       generation_expression as generation,
       character_set_name    as charset,
       collation_name        as collation,
       column_comment        as comment,
       null                  as srs_id
  from information_schema.columns
 where table_schema = %(s)s
   and table_name = %(n)s
 order by ordinal_position
