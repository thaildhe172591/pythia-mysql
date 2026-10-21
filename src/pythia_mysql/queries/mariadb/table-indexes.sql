-- Purpose: a table's indexes, as MariaDB keeps them: no functional parts
--          (a virtual column takes their place), and an index the optimizer
--          ignores where MySQL's is invisible
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
       null          as expression,
       case ignored when 'YES' then 'NO' else 'YES' end as visible,
       index_comment as comment
  from information_schema.statistics
 where table_schema = %(s)s
   and table_name = %(n)s
 order by index_name, seq_in_index
