-- Purpose: the views that call one function: those whose stored definition
--          holds `schema`.`name`( (MariaDB keeps no view routine usage)
-- Binds:   %(s)s its schema, %(n)s its name
-- Returns: SCHEMA_NAME, NAME
select table_schema as schema_name, table_name as name
  from information_schema.views
 where instr(view_definition,
             concat('`', replace(%(s)s, '`', '``'), '`.`', replace(%(n)s, '`', '``'),
                    '`(')) > 0
 order by 1, 2
