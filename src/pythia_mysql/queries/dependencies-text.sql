-- Purpose: the tables, views and routines, in every schema but MySQL's own,
--          whose name a body holds — candidates the caller confirms word by
--          word (an '_' in a name matches any character here)
-- Binds:   %(b)s the body of a procedure, function, trigger or event
-- Returns: SCHEMA_NAME, NAME, TYPE
select o.schema_name, o.name, o.type
  from (select table_schema as schema_name, table_name as name,
               case table_type when 'VIEW' then 'VIEW' else 'TABLE' end as type
          from information_schema.tables
         where table_schema not in ('mysql', 'sys', 'performance_schema', 'information_schema')
        union all
        select routine_schema, routine_name, routine_type
          from information_schema.routines
         where routine_schema not in ('mysql', 'sys', 'performance_schema', 'information_schema')) o
 where lower(%(b)s) like concat('%%', lower(o.name), '%%')
 order by 1, 2
