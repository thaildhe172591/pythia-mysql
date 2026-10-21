-- Purpose: the views whose definition holds a text — MySQL keeps a view's
--          SELECT with every column written `schema`.`table`.`column`
-- Binds:   %(p)s LIKE pattern built from the text ('!' escapes)
-- Returns: SCHEMA_NAME, NAME
select table_schema as schema_name, table_name as name
  from information_schema.views
 where lower(view_definition) like lower(%(p)s) escape '!'
 order by 1, 2
