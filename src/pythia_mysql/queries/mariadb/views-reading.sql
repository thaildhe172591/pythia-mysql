-- Purpose: the views that read one table, view, sequence or function: those
--          whose stored definition names it `schema`.`name` (MariaDB keeps
--          no view usage)
-- Binds:   %(s)s its schema, %(n)s its name
-- Returns: SCHEMA_NAME, NAME
select table_schema as schema_name, table_name as name
  from information_schema.views
 where instr(view_definition,
             concat('`', replace(%(s)s, '`', '``'), '`.`', replace(%(n)s, '`', '``'), '`')) > 0
   and not (table_schema = %(s)s and table_name = %(n)s)
 order by 1, 2
