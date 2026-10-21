-- Purpose: the views errors checks with CHECK TABLE: MariaDB marks none of
--          them invalid in its catalog
-- Binds:   %(s)s schema, %(n)s one view's name, or null for every view
-- Returns: NAME
select table_name as name
  from information_schema.tables
 where table_schema = %(s)s
   and table_type = 'VIEW'
   and (%(n)s is null or table_name = %(n)s)
 order by table_name
