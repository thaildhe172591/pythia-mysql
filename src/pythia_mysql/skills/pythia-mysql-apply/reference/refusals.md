# Refusals and the way forward

`pythia-mysql apply` refuses what it cannot rehearse, predict or undo
honestly. Each refusal exits 1 and writes nothing. Relay the reason, then
offer the way forward below — never run the statement another way.

| Refused | Why | Way forward |
|---|---|---|
| Several statements in one file, or text after a stored program's body | each is previewed, approved and journaled on its own; under `;` a program takes its whole file | one file per statement, applied in order — or `pythia-mysql deploy` for data |
| `CALL`, `DO`, `PREPARE` / `EXECUTE` | runs code that can do anything | apply the statements it would run, or the developer runs it by hand |
| `DECLARE`, `IF`, `WHILE`, `BEGIN ... END` outside a stored program | MySQL runs them only inside one | put the logic in a procedure and apply that |
| `WITH ... UPDATE/DELETE` | hides which rows it touches | a plain UPDATE or DELETE |
| `UPDATE`/`DELETE` with `IGNORE`, `ORDER BY ... LIMIT`, several tables, a join, `USING`, a subquery, `PARTITION`, unbalanced parentheses | its rows cannot be read and shown before it runs | a WHERE clause over the table's own columns |
| a write to a MyISAM, MEMORY or other non-transactional table | MySQL cannot roll it back, so it cannot be rehearsed | convert the table to InnoDB, or a DBA writes it by hand |
| `SELECT`, `SHOW`, `EXPLAIN` | apply takes writes; `SELECT ... INTO OUTFILE` writes a file | reads go through `ls`, `src`, `cols`, `grep` |
| `USE` | changes the schema for what follows | `--conn` for a connection to that schema |
| `START TRANSACTION`, `COMMIT`, `ROLLBACK`, `LOCK TABLES`, `SET autocommit` | pythia-mysql owns the transaction | drop the transaction control |
| `LOAD DATA`, `IMPORT TABLE` | read files no preview can show | INSERT statements, or a DBA loads it by hand |
| `CREATE TEMPORARY TABLE` | dies with the connection, nothing left to verify | not needed through apply |
| accounts, roles, databases, `SET GLOBAL`, `FLUSH`, `GRANT ... ON *.*`, plugins | act on the server, outside one schema | a DBA runs it by hand |
| `OPTIMIZE`, `REPAIR`, `ANALYZE`, `CHECK TABLE` | table maintenance | the developer or a DBA picks the time and runs it |
| `IF NOT EXISTS` on a stored program | leaves an existing one as it is | write `CREATE`: pythia-mysql previews replacing it |
| `ALTER EVENT ... RENAME TO` | leaves the old name's restore behind | `DROP EVENT`, then `CREATE EVENT` |
| an executable comment `/*! ... */` | runs as code whenever the server's version allows | write the statement plainly |
| a routine or view whose definition this account cannot read | nothing to snapshot, no way back | grant `SHOW_ROUTINE` (or `SHOW VIEW`), or the developer decides by hand |
| a file that ends inside a quote, a `name` or a comment | cannot be read safely | close it |
| a schema other than the connection's | writing across schemas is refused | `--conn` for the connection that owns it |
| a group set to `deny` | the policy | relay it; loosening is the developer's `policy set`, at a console |
| a DDL statement in `deploy` | MySQL commits it as it runs, so a release cannot land it all or nothing | apply it on its own, before or after the release |
| `CREATE OR REPLACE PROCEDURE` (or `FUNCTION`, `TRIGGER`, `EVENT`) on MySQL | MySQL has none | write `CREATE`: pythia-mysql replaces the one that exists |
| `CREATE`, `ALTER`, `DROP SEQUENCE` on MySQL | MySQL has no sequences | — |
| a MariaDB package (`CREATE PACKAGE`, `PACKAGE BODY`, `DROP PACKAGE`) | read only in pythia-mysql | the developer writes it by hand, or the logic moves into procedures and functions |
| `RETURNING` (MariaDB) on an INSERT, REPLACE or DELETE | the write hands rows back, and its rows cannot be read beforehand | the statement without it |
| `DELETE HISTORY` (MariaDB) | removes a system-versioned table's history for good, unrehearsable | a DBA runs it by hand |

When the gate refuses, the developer may still decide to run the statement
by hand. Hand them the file and, for a definition, the restore from
`pythia-mysql history <name>` — never run it for them through the mysql
client.
