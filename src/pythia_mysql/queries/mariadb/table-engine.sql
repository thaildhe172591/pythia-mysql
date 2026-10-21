-- Purpose: a table's storage engine, and whether MariaDB can roll a write to
--          it back; a system-versioned table is a table too
-- Binds:   %(s)s schema, %(n)s table name
-- Returns: ENGINE, TRANSACTIONAL
select t.engine       as engine,
       e.transactions as transactional
  from information_schema.tables t
  left join information_schema.engines e on e.engine = t.engine
 where t.table_schema = %(s)s
   and t.table_name = %(n)s
   and t.table_type in ('BASE TABLE', 'SYSTEM VERSIONED')
