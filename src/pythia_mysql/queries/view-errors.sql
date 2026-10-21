-- Purpose: the views of a schema — one, or every one — that no longer work:
--          MySQL marks a view invalid when what it reads is dropped or
--          altered away, and information_schema then shows the error it
--          would raise (1356) where a valid view's comment says VIEW
-- Binds:   %(s)s schema, %(n)s one view's name, or NULL for all
-- Returns: NAME, MESSAGE
select table_name    as name,
       table_comment as message
  from information_schema.tables
 where table_schema = %(s)s
   and table_type = 'VIEW'
   and (%(n)s is null or table_name = %(n)s)
   and table_comment <> 'VIEW'
 order by table_name
