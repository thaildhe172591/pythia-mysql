-- Purpose: a table's storage engine, and whether MySQL can roll a write to it
--          back (InnoDB can; MyISAM, MEMORY and the like cannot)
-- Binds:   %(s)s schema, %(n)s table name
-- Returns: ENGINE, TRANSACTIONAL
select t.engine       as engine,
       e.transactions as transactional
  from information_schema.tables t
  left join information_schema.engines e on e.engine = t.engine
 where t.table_schema = %(s)s
   and t.table_name = %(n)s
   and t.table_type = 'BASE TABLE'
