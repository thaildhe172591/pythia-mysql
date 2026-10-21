-- Purpose: the tables, views, sequences and functions a view's stored
--          definition names: MariaDB writes each one `schema`.`name`
-- Binds:   %(s)s schema, %(n)s view name
-- Returns: SCHEMA_NAME, NAME, TYPE
select o.schema_name, o.name, o.type
  from (select table_schema as schema_name, table_name as name,
               case table_type when 'VIEW' then 'VIEW'
                               when 'SEQUENCE' then 'SEQUENCE'
                               else 'TABLE' end as type
          from information_schema.tables
         where table_schema not in ('mysql', 'sys', 'performance_schema', 'information_schema')
        union all
        select routine_schema, routine_name, routine_type
          from information_schema.routines
         where routine_type = 'FUNCTION'
           and routine_schema not in ('mysql', 'sys', 'performance_schema',
                                      'information_schema')) o
  join information_schema.views v
    on v.table_schema = %(s)s
   and v.table_name = %(n)s
 where instr(v.view_definition,
             concat('`', replace(o.schema_name, '`', '``'), '`.`',
                    replace(o.name, '`', '``'), '`')) > 0
   and not (o.schema_name = %(s)s and o.name = %(n)s)
 order by 1, 2
