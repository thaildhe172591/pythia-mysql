# Changelog

## 0.1.0.dev0 — unreleased

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
