-- Purpose: a table's CHECK constraints, and whether each is enforced
-- Binds:   %(s)s schema, %(n)s table name
-- Returns: NAME, CLAUSE, ENFORCED
select tc.constraint_name as name,
       cc.check_clause    as clause,
       tc.enforced        as enforced
  from information_schema.table_constraints tc
  join information_schema.check_constraints cc
    on cc.constraint_schema = tc.constraint_schema
   and cc.constraint_name = tc.constraint_name
 where tc.table_schema = %(s)s
   and tc.table_name = %(n)s
   and tc.constraint_type = 'CHECK'
 order by tc.constraint_name
