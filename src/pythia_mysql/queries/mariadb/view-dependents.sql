-- Purpose: the views whose stored definition names an object. MariaDB
--          records no view dependencies, but stores each view's SELECT with
--          every table, view, function and sequence written `schema`.`name`
-- Binds:   %(s)s schema, %(n)s object name
-- Returns: SCHEMA_NAME, NAME, TYPE
select v.table_schema as schema_name, v.table_name as name, 'VIEW' as type
  from information_schema.views v
 where instr(v.view_definition,
             concat('`', replace(%(s)s, '`', '``'), '`.`', replace(%(n)s, '`', '``'), '`')) > 0
   and not (v.table_schema = %(s)s and v.table_name = %(n)s)
 order by 1, 2
