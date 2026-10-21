-- Purpose: objects whose name matches a LIKE pattern, for `ls`
-- Binds:   %(s)s schema, %(p)s LIKE pattern, %(n)s how many rows at most
-- Returns: NAME, TYPE, CREATED, MODIFIED
select o.name, o.type, o.created, o.modified
  from (select table_name  as name,
               case table_type when 'VIEW' then 'VIEW'
                               when 'SEQUENCE' then 'SEQUENCE'
                               else 'TABLE' end as type,
               create_time as created,
               null        as modified
          from information_schema.tables
         where table_schema = %(s)s
           and table_name like %(p)s
        union all
        select routine_name, routine_type, created, last_altered
          from information_schema.routines
         where routine_schema = %(s)s
           and routine_name like %(p)s
        union all
        select trigger_name, 'TRIGGER', created, null
          from information_schema.triggers
         where trigger_schema = %(s)s
           and trigger_name like %(p)s
        union all
        select event_name, 'EVENT', created, last_altered
          from information_schema.events
         where event_schema = %(s)s
           and event_name like %(p)s) o
 order by o.name, o.type
 limit %(n)s
