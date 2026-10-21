# pythia-mysql

**English** · [Tiếng Việt](https://github.com/thaildhe172591/pythia-mysql/blob/main/README.vi.md)

pythia for MySQL: stored-program development for AI agents, built on
[pythia-core](https://github.com/thaildhe172591/pythia-core). It aims to do
what [pythia](https://github.com/thaildhe172591/pythia) does on Oracle and
its siblings do on PostgreSQL, SQL Server and MongoDB: the agent learns
from the live catalog, asks a person before any write, and writes only
through a gate that snapshots, verifies and reports honestly.

**Pre-alpha (Phase 9a).** It reads everything pythia's Learn movement
needs, and writes nothing yet.

| Works today | Next |
|---|---|
| `check`, `ls`, `src`, `cols`, `ddl`, `grep`, `deps`, `impact`, `errors`, `connections` | the write gate (9b); the harness, deploy, autopilot and lint (9c) |

MySQL 8.4 LTS is the floor: CI runs the whole live check on 8.4, 9.4 and
9.5, and below 8.4 — or on MariaDB — `check` says so (nothing is refused).

## Install (from git while pre-alpha)

```bash
pip install "git+https://github.com/thaildhe172591/pythia-core" \
            "git+https://github.com/thaildhe172591/pythia-mysql"
```

That brings [PyMySQL](https://pypi.org/project/PyMySQL/), pure Python: no
client library needs installing, on Windows, macOS or Linux.

## Connections

`.pythia/mysql/connections.json` in the project root, owner-readable only
(`chmod 600`), and out of git. Template:
[examples/connections.example.json](https://github.com/thaildhe172591/pythia-mysql/blob/main/examples/connections.example.json).

```json
{
  "default": "dev",
  "dev": { "host": "db-dev", "port": 3306, "database": "app_owner",
           "user": "app_agent", "password": "...", "tls": "request" }
}
```

- `host`, `database`, `user` are required. In MySQL a schema is a
  database: `database` is where an unqualified name lands, and what pythia
  reads unless `schema` names another (then `check` warns).
- `tls` is `off`, `request` (the default: TLS whenever the server offers
  it), `require` (encrypted or refused, the certificate not checked) or
  `verify` (the certificate and the host name checked, against `tls_ca`
  when it is set, else this machine's CAs).
- An account on `caching_sha2_password` — MySQL's default — needs TLS, or
  the `cryptography` package, to send its password; when neither is there,
  pythia-mysql says so instead of failing obscurely.
- The entry is picked by `--conn NAME`, then `PYTHIA_MYSQL_CONNECTION`, then
  the only entry, the folder directly under the project root, then
  `"default"`. `PYTHIA_MYSQL_CONFIG` points at another file.

pythia for Oracle keeps `.pythia/connections.json`, and the other engines
`.pythia/postgres/`, `.pythia/mssql/` and `.pythia/mongo/`; pythia-mysql
reads none of them.

## Commands

```bash
pythia-mysql check                 # server, database, where unqualified names land
pythia-mysql ls "t_order%"         # tables, views, routines, triggers, events by LIKE
pythia-mysql src f_order_total     # a routine, view, trigger or event, rebuilt
pythia-mysql cols t_order          # columns, types, defaults, generated columns
pythia-mysql ddl t_order           # CREATE TABLE and its triggers, rebuilt
pythia-mysql grep "t_order where"  # every line of code holding a text
pythia-mysql deps p_order_paid     # what it uses
pythia-mysql impact t_order        # what uses it: run before changing it
pythia-mysql errors [NAME]         # views MySQL has marked broken; what it cannot check
```

`--json` gives one envelope per command; `--limit`, `--max-lines` and
`--offset` window long output, and any truncation says how to fetch the
rest.

### What the catalog cannot see, and how pythia-mysql says so

- **`impact` asks the catalog, then searches bodies.** information_schema
  records which tables, views and functions a view reads, the triggers on a
  table and the foreign keys that point at it — and nothing about what a
  procedure, function, trigger or event body uses. Those bodies, in every
  schema, are searched for the name as a whole word (a qualifier names the
  schema, none means the body's own), and those rows are marked `[text]`.
  Each blind spot is printed every time.
- **MySQL hides what an account may not see.** A routine needs
  `SHOW_ROUTINE` (or a global `SELECT`) to be seen with its body, a trigger
  the `TRIGGER` privilege, an event `EVENT`. pythia-mysql reads `SHOW
  GRANTS` and says which of them this account cannot see, every time it
  could matter.
- **`errors` reads what MySQL has marked broken.** Dropping or altering
  what a view reads marks the view invalid, and pythia-mysql lists the
  error it would raise. MySQL resolves the names inside a procedure,
  function, trigger or event only when it runs: `errors` names them as not
  checked, and never calls that clean.
- **`src` and `ddl` are rebuilt, not dumped.** MySQL keeps no CREATE
  statement in information_schema and no line numbers: the header is
  rebuilt on line 1, and the body follows as it was written (a view's
  SELECT only as MySQL rewrote it). `ddl` wraps code in `DELIMITER //`, as
  the mysql client and Flyway read it, and notes the `sql_mode` it was
  created under. The live check runs every `ddl` into a copy and compares
  it with the original.
- **Reads cannot write.** Every read command's session is `READ ONLY`, and
  MySQL refuses DML and DDL alike there (error 1792). A read-only account is
  the first line.

### Least privilege

The read commands need `SELECT` and `SHOW VIEW` on the schemas, and
`SHOW_ROUTINE` to read routine bodies:

```sql
CREATE USER 'app_agent'@'%' IDENTIFIED BY '...';
GRANT SELECT, SHOW VIEW ON app_owner.* TO 'app_agent'@'%';
GRANT SHOW_ROUTINE ON *.* TO 'app_agent'@'%';
```

MySQL shows triggers only to an account holding `TRIGGER`, and events only
with `EVENT` — both also let it change them. Without them, pythia-mysql
says that triggers and events are hidden; the live check runs every read
command both ways.

## Tests

```bash
python tests/test_mysql.py    # no database, no PyMySQL
python tests/live_check.py    # a disposable server only (see its docstring)
```

CI runs the suite on Ubuntu, Windows and macOS, Python 3.9 and 3.13, and
the live check against MySQL 8.4, 9.4 and 9.5 in service containers. It
tests against the pythia-core branch of the same name when one exists.

## License

MIT
