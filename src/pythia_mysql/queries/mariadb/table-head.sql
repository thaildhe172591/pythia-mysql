-- Purpose: a table's options, as MariaDB keeps them; a system-versioned
--          table is a table too, flagged so ddl says what it leaves out
-- Binds:   %(s)s schema, %(n)s table name
-- Returns: ENGINE, CHARSET, COLLATION, OPTIONS, COMMENT, PARTITIONED, VERSIONED
select t.engine             as engine,
       c.character_set_name as charset,
       t.table_collation    as collation,
       t.create_options     as options,
       t.table_comment      as comment,
       exists (select 1
                 from information_schema.partitions p
                where p.table_schema = t.table_schema
                  and p.table_name = t.table_name
                  and p.partition_name is not null) as partitioned,
       t.table_type = 'SYSTEM VERSIONED' as versioned
  from information_schema.tables t
  left join information_schema.collations c on c.collation_name = t.table_collation
 where t.table_schema = %(s)s
   and t.table_name = %(n)s
   and t.table_type in ('BASE TABLE', 'SYSTEM VERSIONED')
