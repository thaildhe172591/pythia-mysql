-- Purpose: a table's foreign keys, one row per column, in key order
-- Binds:   %(s)s schema, %(n)s table name
-- Returns: NAME, COLUMN_NAME, REF_SCHEMA, REF_TABLE, REF_COLUMN, ON_UPDATE,
--          ON_DELETE
select k.constraint_name         as name,
       k.column_name             as column_name,
       k.referenced_table_schema as ref_schema,
       k.referenced_table_name   as ref_table,
       k.referenced_column_name  as ref_column,
       r.update_rule             as on_update,
       r.delete_rule             as on_delete
  from information_schema.key_column_usage k
  join information_schema.referential_constraints r
    on r.constraint_schema = k.constraint_schema
   and r.constraint_name = k.constraint_name
   and r.table_name = k.table_name
 where k.table_schema = %(s)s
   and k.table_name = %(n)s
 order by k.constraint_name, k.ordinal_position
