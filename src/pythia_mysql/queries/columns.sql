-- Purpose: the columns of one table or view, for `cols`
-- Binds:   %(s)s schema, %(n)s table or view name
-- Returns: POSITION, COLUMN_NAME, DATA_TYPE, NULLABLE, COLUMN_DEFAULT, EXTRA,
--          COMMENT
select ordinal_position as position,
       column_name      as column_name,
       column_type      as data_type,
       is_nullable      as nullable,
       column_default   as column_default,
       case when generation_expression <> ''
            then concat(extra, ' AS (', generation_expression, ')')
            else extra end as extra,
       column_comment   as comment
  from information_schema.columns
 where table_schema = %(s)s
   and table_name = %(n)s
 order by ordinal_position
