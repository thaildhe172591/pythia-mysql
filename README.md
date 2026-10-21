# pythia-mysql

**English** · [Tiếng Việt](https://github.com/thaildhe172591/pythia-mysql/blob/main/README.vi.md)

pythia for MySQL: stored-program development for AI agents, built on
[pythia-core](https://github.com/thaildhe172591/pythia-core). It aims to do
what [pythia](https://github.com/thaildhe172591/pythia) does on Oracle and
its siblings do on PostgreSQL, SQL Server and MongoDB: the agent learns
from the live catalog, asks a person before any write, and writes only
through a gate that snapshots, verifies and reports honestly.

**Alpha (0.1.0).** It reads everything pythia's Learn movement needs,
writes through one gate — data rehearsed in a transaction, DDL predicted,
written once and read back — and wires a project for an agent: the guard,
the session brief, the approval doors and the `pythia-mysql-*` skills.

| Works today |
|---|
| reads: `check`, `ls`, `src`, `cols`, `ddl`, `grep`, `deps`, `impact`, `errors`, `connections` |
| writes: `apply`, `deploy`, `approve`, `journal`, `history`, `policy`, `autopilot`, `lint` |
| the harness: `install`, `doctor`, `hook`, `mcp`, `skill lint` |

MySQL 8.4 LTS is the floor: CI runs the whole live check on 8.4, 9.4 and
9.5, and below 8.4 — or on MariaDB — `check` says so (nothing is refused).

## Install

```bash
pip install pythia-mysql
```

That brings pythia-core, and [PyMySQL](https://pypi.org/project/PyMySQL/),
pure Python: no client library needs installing, on Windows, macOS or
Linux. The development version is the main branch of both:

```bash
pip install "git+https://github.com/thaildhe172591/pythia-core" \
            "git+https://github.com/thaildhe172591/pythia-mysql"
```

## Set up a project for an agent

```bash
cd your-project
pythia-mysql install     # once; a second run changes nothing
pythia-mysql doctor      # is everything wired? exit 1 names what is not
```

`install` writes, and leaves everything else as it was:

- `.pythia/mysql/connections.json`, mode 600, created once from the
  template — the developer fills in the passwords; an agent never opens it;
- `.gitignore` lines for that file, this machine's approvals
  (`.pythia/mysql/grants/`) and `.claude/settings.local.json`;
- `.claude/settings.local.json`: the hooks (the guard, the session brief,
  the AskUserQuestion answer), spelled with this interpreter's absolute path
  so they start whether or not a virtual environment is active, and deny
  rules for the engine's files;
- the MCP approver `pythia_mysql` (tool `pythia_mysql_approve`), in this
  machine's files only: Claude Code's local scope for the project
  (`~/.claude.json`) and Codex's `~/.codex/config.toml`, each when that
  client has run here;
- a `pythia-mysql` block in CLAUDE.md and AGENTS.md (other tools' blocks,
  and the developer's own text, are left alone);
- the skills, in `.claude/skills` and `.agents/skills`:
  `using-pythia-mysql` (the router), `pythia-mysql-explore`,
  `pythia-mysql-impact`, `pythia-mysql-apply`, `pythia-mysql-deploy`,
  `pythia-mysql-autopilot`, `pythia-mysql-verify`.

Restart the agent's session after installing, so the hooks load. Each
session then starts with the rules and a `STATE` line (connections, the
write policy). Before every tool call the guard decides:

| The agent runs | The guard |
|---|---|
| `mysql`, `mysqlsh` or `mariadb` given write SQL (DDL, DML, `CALL`, `DO`, `PREPARE`/`EXECUTE`, `LOAD DATA`, `SET GLOBAL`, `SELECT ... INTO OUTFILE`, `LOCK TABLES`, `source file.sql`), a script (`< file`, a pipe into the client, `mysqlsh -f`), MySQL Shell's `util.load*`; `mysqlimport`; `mysqladmin` create, drop, flush, kill, password or shutdown — also behind `docker exec`, `ssh`, `sudo` or `bash -c` | denies: writes go through `pythia-mysql apply` |
| an MCP SQL tool given write SQL | denies |
| reading `connections.json`; editing `policy.json`, the journal or a grant; setting `PYTHIA_MYSQL_CI`; calling `grants.mint` from a one-liner | denies |
| a `pythia-mysql` read, a preview, `approve --card` | allows without a prompt |
| `apply --confirm <token>` the developer already approved on this connection | allows; apply re-verifies it |
| `mysql` reads, `mysqldump`, `approve`, `--yes`, `policy set`, anything compound | stays out: the client asks |

The guard reads a command for what it names, not what it means: it can
deny a harmless command (a `SELECT` whose text mentions `drop`) and miss a
write spelled in a way it does not list. It sees the commands Claude Code
hands its tools, not Workbench or a driver inside the application. The gate
behind it holds either way (pythia-core's SECURITY.md).

pythia-postgres, pythia-mssql and pythia-mongo install beside it in one
project, and pythia for Oracle too: each keeps the others' hooks and
instruction blocks, and each guard and approval hook acts for its own tool
only (pythia-core's CI checks it with all five installed).

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

### Writing: the gate

```bash
pythia-mysql apply change.sql                   # preview: nothing written
pythia-mysql approve 3fa9c1                     # the developer approves (or from chat, below)
pythia-mysql apply change.sql --confirm 3fa9c1  # writes it — only as approved
pythia-mysql journal restore <entry>            # undo is a write too: preview, approve, confirm
pythia-mysql policy                             # which groups may be written, and is rollback real?
```

The developer approves through the first door that works:

1. **In Claude Code's chat.** The agent asks with AskUserQuestion, its text
   exactly the output of `pythia-mysql approve --card <token>`, options
   Approve / Reject. The answer hook records the approval only when the
   question carried that card and the developer chose Approve themselves —
   not an answer the agent wrote, not a dialog that closed unattended.
2. **Through the MCP approver** (`pythia_mysql_approve`; Codex starts
   here): the client shows the card, and only an explicit Approve counts.
3. **At the developer's console:** `pythia-mysql approve <token>`.

`pythia-mysql doctor` warns about settings that would answer the chat door
for the developer (`dontAsk` mode, an allow rule for AskUserQuestion, a hook
matching every tool).

### A release: `deploy`, one transaction

```bash
pythia-mysql deploy 01_fix.sql 02_backfill.sql                     # preview the release as one transaction
pythia-mysql deploy 01_fix.sql 02_backfill.sql --confirm 9c41e0b2aa  # all of it, as approved, or none
```

A release is data: one or more scripts of `INSERT`, `REPLACE`, `UPDATE` and
`DELETE`, cut at each `;` (and at `DELIMITER` lines, as the mysql client
cuts them). It is rehearsed in one transaction: each statement in order,
its rows taken at its own point, then everything rolls back. One card shows
every statement, and one approval (a 10-digit token, through the same
doors) covers the release; a single statement's token cannot be approved
alone. The confirm checks that every statement is byte-identical to what
was approved before anything runs, re-runs the release in one transaction,
and commits only if every statement still matches. A statement that fails,
or rows that moved, roll back the whole release.

MySQL commits DDL as it runs it, so a release cannot hold it: a table, a
column, an index, a view, a routine, a trigger, an event, a comment or a
grant is refused, with nothing written — apply each on its own, before or
after the data. A `SET` inside a release is refused too, and anything
`apply` refuses. Rows the release itself inserts get a new `AUTO_INCREMENT`
value, `CURRENT_TIMESTAMP` or `UUID()` every time it runs, so an UPDATE or
DELETE of them later in the same release never matches its approval: give
them their final values in the INSERT.

### Lint: before any apply

```bash
pythia-mysql lint 01_table.sql 02_view.sql   # a change's files in one run
pythia-mysql lint --rules                    # every rule and its effective severity
```

The rules read what MySQL accepts and a reviewer would not:

| Rule | Default | Why |
|---|---|---|
| `mysql-non-transactional` | error | a MyISAM, MEMORY or other table without transactions cannot be rehearsed, can lose rows in a crash, and ignores foreign keys |
| `mysql-utf8mb3` | warn | `utf8` is `utf8mb3`: no emoji and no rarer CJK — `utf8mb4` |
| `mysql-select-star` | warn | MySQL expands `*` when a view is created and keeps that list; a procedure's result changes shape; `EXISTS (SELECT * ...)` is fine |
| `mysql-not-in-subquery` | warn | `NOT IN (SELECT ...)` is never true when the subquery returns a NULL |
| `mysql-primary-key` | warn | without one, InnoDB invents a hidden key that replication and row-based tools cannot use |
| `mysql-table-comment` | warn | a new table gets its `COMMENT` in the same change (an `ALTER TABLE ... COMMENT` in the same run counts) |
| `mysql-function-characteristic` | warn | a function declaring none of `DETERMINISTIC`, `NO SQL`, `READS SQL DATA` is refused while binary logging is on (1418) |
| `mysql-definer` | warn | a `DEFINER` naming an account needs `SET_ANY_DEFINER`, and breaks where that account does not exist |
| `mysql-zero-date` | warn | `'0000-00-00'` is refused under MySQL's default `NO_ZERO_DATE` |
| `mysql-limit-order` | info | `LIMIT` without `ORDER BY` in stored code takes whichever rows come first |

What MySQL rejects itself is left to the rehearsal or the prediction. The
team sets severities and naming patterns in `.pythia/mysql/lint.json`:

```json
{"severity": {"mysql-select-star": "error", "naming": "error"},
 "naming": {"PROCEDURE": "^p_[a-z0-9_]+$", "VIEW": "^v_[a-z0-9_]+$"}}
```

Every preview shows the findings, a statement's errors are on its card, and
autopilot never lands a lint error.

### Autopilot: one lease instead of every approval

```bash
pythia-mysql autopilot request --groups source,comments --hours 2 --max-writes 30
pythia-mysql autopilot report      # every write under the lease, with its restore
pythia-mysql autopilot off         # anyone may revoke
```

When the developer wants the agent to work without approving each write,
the agent requests a lease. Its card names the connection, the groups, the
time, the number of writes and whether destructive statements are included,
and nothing is delegated until the developer approves it through a door (or
runs `pythia-mysql autopilot on` at a console). While it lasts, `apply` and
`deploy` land what it covers without `--confirm` — still snapshotted,
rehearsed or predicted, read back and journaled. It never covers another
connection, one marked `"protected": true` (or an `"env"` of prod /
production / prd / live), a group or destructive statement the card did not
name, or more than 1000 rows; a write that breaks something, lands unlike
its prediction or is `WRITTEN?`, or five failures in a row pause it.

### One statement: `apply`

One statement per file. A stored program (`CREATE PROCEDURE`, `FUNCTION`,
`TRIGGER`, `EVENT`) takes its whole file, its body's `;` included, and
nothing may follow its body; `DELIMITER` lines are read as the mysql client
reads them, so `ddl`'s output applies as it is. Anything else ends at its
`;`. `apply` sorts the statement into a group, and the policy decides:
`source` (views, procedures, functions, triggers, events) and `comments`
(`ALTER TABLE ... COMMENT = '...'`, alone) need the developer's approval;
`data_dml`, `structural` (DDL) and `grants` (`GRANT` and `REVOKE` on a
schema or an object in it) are denied until the developer runs
`pythia-mysql policy set <group> confirm` at a console. `session` (`SET`)
is allowed.

MySQL commits DDL as it runs it, so the write path is split in two:

- **Data is rehearsed.** An INSERT, REPLACE, UPDATE or DELETE runs inside
  the transaction and is rolled back; the confirm runs it again and commits
  only if it still matches. An UPDATE or DELETE is approved on its rows:
  the count, a sample and a fingerprint over every column (an order-free
  sum of `md5(json_array(...))`); if any row joins, leaves or changes before
  the confirm, the confirm is refused. An UPDATE counts the rows it
  matched, as the check does, not only those whose value changed.
- **A rehearsal cannot write where MySQL cannot roll back.** A statement
  whose own table is MyISAM, MEMORY or another engine without transactions
  is refused before it runs. A trigger or function that writes to such a
  table would turn a preview into a write, so every data change runs first
  inside a savepoint: when rolling that back draws MySQL's warning 1196,
  the preview is reported **`WRITTEN?`** with exit 3 — those rows are
  written — and never as nothing written. The statement therefore runs
  twice in a rehearsal; the preview says so. A server that enforces GTID
  consistency refuses such a statement itself (error 1785), before
  anything is written.
- **DDL is predicted — nothing runs before the approval.** A view's SELECT
  runs with `LIMIT 0`, so its names must resolve. The views MySQL would
  mark invalid are read from information_schema: every view that reads a
  table, view, function or column the statement drops or renames, and
  every view on top of those, in any schema. A routine, trigger or event is
  `NOT VERIFIED` — MySQL checks its names only when it runs — and the
  routines that name what a statement drops are listed as `[text]` leads.
  After the approval the statement runs once; the views MySQL marked
  invalid are read back, and anything unlike the prediction exits 3, as a
  breakage does. A prediction that moved since the approval refuses the
  write.
- **A CREATE for a routine that exists replaces it.** MySQL has no `CREATE
  OR REPLACE` for a procedure, function, trigger or event. A procedure or
  function is first created under a scratch name, so that MySQL's verdict
  on the new text costs nothing; then the old one is dropped and the new
  one created, and if MySQL refuses it the old one is put back from the
  snapshot (if that fails too, it is **`WRITTEN?`**, exit 3, with the
  restore). A trigger or an event is dropped and created; rows written in
  between fire neither trigger. A view is replaced with `CREATE OR REPLACE
  VIEW`, which MySQL does in one step.
- **The definer is said.** A replacement without a `DEFINER` clause is
  defined by this account; the preview says so when that changes it.
  Putting back another account's routine or view needs `SET_ANY_DEFINER`
  (and `SYSTEM_USER` when that account is a system one): when this account
  lacks it, the preview says the old one could not be put back by it, and a
  restore it tries is refused with nothing written.
- **Refused, with the reason:** `CALL`, `DO`, `PREPARE` and `EXECUTE`;
  compound statements outside a stored program; `SELECT`, `SHOW`, `WITH`;
  `USE`; transaction control and `LOCK TABLES`; `LOAD DATA`; temporary
  tables; accounts, roles, databases and other server-level statements
  (`SET GLOBAL`, `FLUSH`, `GRANT ... ON *.*`); table maintenance
  (`OPTIMIZE`, `ANALYZE`); `IF NOT EXISTS` on a stored program;
  executable comments (`/*! ... */`); several statements in one file; an
  UPDATE or DELETE whose rows cannot be read beforehand (`IGNORE`, `ORDER
  BY ... LIMIT`, several tables, a join, a subquery, a `PARTITION` clause,
  parentheses that do not balance); and a routine whose body this account
  cannot read (nothing to snapshot).

pythia-mysql never turns on `MULTI_STATEMENTS` or `LOCAL INFILE`: MySQL
itself refuses any text after the one statement sent. A write waits at most
5 s for a lock (`innodb_lock_wait_timeout`, `lock_wait_timeout`). A
rehearsal still fires triggers and draws `AUTO_INCREMENT` values, and the
preview of a data change says so. Exit codes follow pythia: `0` clean, `1`
refused, `3` written but broken, or written unlike the prediction (with the
restore command).

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

A write needs what the change needs, on its schema only — for example
`INSERT, UPDATE, DELETE` for data, `CREATE, ALTER, DROP, INDEX, CREATE
VIEW, CREATE ROUTINE, ALTER ROUTINE, TRIGGER, EVENT` for DDL. An account
holding every privilege on the server, `SUPER`, `SYSTEM_USER`,
`SET_ANY_DEFINER` or `SET_USER_ID` is named in the preview: far more than a
change needs. The live check runs every write path as an account whose
write privileges stop at its schema.

## Tests

```bash
python tests/test_mysql.py    # no database, no PyMySQL
python tests/live_check.py    # a disposable server only (see its docstring)
```

CI runs the suite on Ubuntu, Windows and macOS, Python 3.9 and 3.13, and
the live check — every read, every write path, a release, a lint finding in
a real preview and a write under a lease — against MySQL 8.4, 9.4 and 9.5
in service containers. It tests against the pythia-core branch of the same
name when one exists.

## License

MIT
