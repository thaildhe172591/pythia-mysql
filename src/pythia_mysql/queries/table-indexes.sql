-- Purpose: a table's indexes, one row per key part, in key order
-- Binds:   %(s)s schema, %(n)s table name
-- Returns: NAME, NON_UNIQUE, SEQ, COLUMN_NAME, SUB_PART, DIRECTION,
--          INDEX_TYPE, EXPRESSION, VISIBLE, COMMENT
select index_name    as name,
       non_unique    as non_unique,
       seq_in_index  as seq,
       column_name   as column_name,
       sub_part      as sub_part,
       collation     as direction,
       index_type    as index_type,
       expression    as expression,
       is_visible    as visible,
       index_comment as comment
  from information_schema.statistics
 where table_schema = %(s)s
   and table_name = %(n)s
 order by index_name, seq_in_index
