-- Purpose: a table's CHECK constraints, as MariaDB keeps them: always
--          enforced, and a column-level one named after its column
-- Binds:   %(s)s schema, %(n)s table name
-- Returns: NAME, CLAUSE, ENFORCED, LEVEL
select constraint_name as name,
       check_clause    as clause,
       'YES'           as enforced,
       level           as level
  from information_schema.check_constraints
 where constraint_schema = %(s)s
   and table_name = %(n)s
 order by constraint_name
