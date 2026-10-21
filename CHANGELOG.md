# Changelog

## 0.1.0.dev0 — unreleased

### Phase 9b: the write and predict tiers

MySQL commits DDL as it runs it, so the write path is split in two.

- **`apply`, `approve`, `journal`, `policy`**, over pythia-core's gate.
- **Data is rehearsed** in the transaction and rolled back; the confirm
  commits only if it still matches. An UPDATE or DELETE is approved on its
  rows: count, sample and an order-free fingerprint over every column (a
  sum of `md5(json_array(...))`). The connection asks MySQL for the rows an
  UPDATE matched (`CLIENT_FOUND_ROWS`), as the check counts them.
- **No rehearsal writes where MySQL cannot roll back.** A statement on a
  MyISAM or MEMORY table is refused before it runs; every data change runs
  first in a savepoint, and MySQL's warning 1196 on rolling it back — a
  trigger or function that wrote to such a table — is reported `WRITTEN?`,
  exit 3.
- **DDL is predicted** (the predict tier): a view's SELECT runs with
  `LIMIT 0`; the views MySQL would mark invalid — those reading a table,
  view, function or column the statement drops or renames, and every view
  on top of them, in any schema — are predicted from information_schema;
  routines are `NOT VERIFIED`, and those naming what a statement drops are
  `[text]` leads. After the approval it runs once, and the views MySQL
  marked invalid are read back and compared with the prediction (exit 3
  when they differ).
- **A CREATE replaces a routine, trigger or event that exists**, as MySQL
  has no CREATE OR REPLACE for them: a procedure or function is checked
  under a scratch name first, the old one dropped, the new one created, and
  the old one put back from the snapshot if MySQL refuses it. The preview
  says when the definer changes, and when this account could not put the
  old definer back (`SET_ANY_DEFINER`, and `SYSTEM_USER` for a system
  account).
- **Comments** are `ALTER TABLE ... COMMENT = '...'`, snapshotted, read back
  and restorable; `grants` are GRANT and REVOKE inside a schema, `NOT
  VERIFIED`.
- **Refused before anything runs:** CALL, DO, PREPARE, compound statements,
  reads, USE, WITH, transaction control, LOAD DATA, temporary tables,
  server-level statements and `ON *.*` grants, table maintenance, `IF NOT
  EXISTS` on a stored program, executable comments, text after a stored
  program's body, several statements, and an UPDATE or DELETE whose rows
  cannot be read beforehand. The connection never turns on
  `MULTI_STATEMENTS` or `LOCAL INFILE`, so MySQL refuses any text after the
  one statement sent.
- **The live check writes through every path** on a disposable server, as
  an account whose write privileges stop at its schema: a procedure
  created, replaced, refused and restored; a view replaced that breaks the
  view on top as predicted; rows that moved and rows written; a MyISAM leak
  reported `WRITTEN?`; a dropped column and a rename that break views as
  predicted, and a prediction that moved after approval; a comment; a
  restore refused for want of `SET_ANY_DEFINER`, then run again.

### Phase 9a: the connect and read tiers

Phase 9a of the plan in pythia-core's DESIGN.md: MySQL's connect and read
tiers, on pythia-core 0.1.1.

- **The driver is PyMySQL** (settled by a spike against MySQL 8.4): pure
  Python, so nothing else needs installing, and it still runs on Python
  3.9 — mysql-connector-python and mysqlclient need 3.10. From 1.2 it
  negotiates TLS whenever the server offers it, the `"tls": "request"`
  default; `"require"` and `"verify"` (with `"tls_ca"`) are stricter.
- **MySQL 8.4 LTS is the floor**; `check` warns below it, and on MariaDB,
  and refuses nothing.
- **`pythia-mysql check`, `ls`, `src`, `cols`, `ddl`, `grep`, `deps`,
  `impact`, `errors`**, over pythia-core's command line.
- **Read sessions are `READ ONLY`.** MySQL refuses DML and DDL alike in
  them (error 1792), the implicit transaction after a DDL commit included.
- **`impact` asks the catalog, then searches bodies:** VIEW_TABLE_USAGE,
  VIEW_ROUTINE_USAGE, triggers and foreign keys — then every procedure,
  function, trigger and event body, in every schema, for the name as a
  whole word, the qualifier read as the schema; those rows are `[text]`.
- **What MySQL hides is said.** `SHOW GRANTS` (active roles merged in) tells
  whether this account can see routine bodies (`SHOW_ROUTINE`), triggers
  (`TRIGGER`) and events (`EVENT`); `impact`, `deps` and `errors` name each
  that is hidden.
- **`errors` lists the views MySQL has marked invalid** with the error each
  would raise, and names every routine, trigger and event as unchecked:
  MySQL resolves their names only when they run.
- **`src` and `ddl` rebuild what information_schema does not keep:** the
  CREATE header on line 1 and the body as written; tables with columns,
  defaults, generated columns, keys, functional and invisible indexes,
  foreign keys, checks, options and their triggers; code in `DELIMITER //`
  with the `sql_mode` (and an event's time zone) it was created under.
  information_schema's extra level of escaping in expressions is undone.
- **`tests/live_check.py`** runs every read command against a disposable
  MySQL, as an account without and then with TRIGGER and EVENT, proves a
  read session refuses writes, and runs every `ddl` into a copy that must
  match the original in SHOW CREATE TABLE and information_schema.
