# Working in this repository / with this tool

pythia-mysql is pythia for MySQL and MariaDB, on pythia-core. It is alpha
(0.1.0): it reads everything pythia's Learn movement needs, and writes
through one gate — data rehearsed in a transaction, DDL predicted, written
once and read back. `pythia-mysql install` wires a project: the guard, the
session brief and the `pythia-mysql-*` skills (`using-pythia-mysql`
routes). MariaDB (Phase 11a) is read; writes to it are refused until 11b.

## Using pythia-mysql as an agent (Phase 9c)

1. **Ask the database, never the dump.** `ls`, `src`, `cols`, `ddl`, `grep`
   against the live schema; `check` says where unqualified names land (the
   connection's database).
2. **Lint before apply.** `pythia-mysql lint <files>` — a change's files in
   one run. Errors are fixed, not argued; the team's `.pythia/mysql/
   conventions.md`, when it exists, is read before writing any object.
3. **Impact before change.** Run `pythia-mysql impact <NAME>` before
   proposing any modification. When it prints `! show this list to the
   developer` (10 or more dependents, or one in another schema), show the
   developer the list before writing code. Rows marked `[text]` are leads
   found by name in procedure, function, trigger and event bodies — MySQL
   records none of their dependencies — not proofs. Relay the `blind spot`
   lines, and never call an impact list complete.
4. **What the server hides is a blind spot, not an absence.** Without
   `SHOW_ROUTINE` (MariaDB: `SHOW CREATE ROUTINE`, or `SELECT` on
   `mysql.proc` on 10.11), `TRIGGER` or `EVENT`, the server hides routines,
   triggers or events from this account; pythia-mysql says so. Never report
   "no triggers" when a line says they are hidden. On MariaDB, rows marked
   `definition` were read in a view's stored definition.
5. **Writes go through `pythia-mysql apply` (one statement per file) or
   `pythia-mysql deploy` (a release of data, one transaction) only.** Never
   write through the `mysql` client, MySQL Shell, Workbench, `mysqlimport`
   or a driver script: those have no snapshot, no rehearsal or prediction,
   and no journal. DDL never goes in a release — apply it on its own. Where
   `pythia-mysql install` wired the hooks, the guard denies them; where it
   did not, this rule still binds. No `STATE` line at session start means
   the hooks are not running: say so, and ask the developer to run
   `pythia-mysql doctor`.
6. **The developer sees every preview.** Relay `apply`'s preview verbatim:
   the diff, the rehearsal or the prediction (what would break, or NOT
   VERIFIED), the rows, the notes (a replacement, a definer that changes),
   the destructive warning, the lint findings. Then ask through the first
   door that works, moving to the next unasked when one fails: on Claude
   Code an `AskUserQuestion` whose text is the output of `pythia-mysql
   approve --card <token>` verbatim (options Approve / Reject); then the
   `pythia_mysql_approve` tool (MCP — where Codex starts); then the
   developer's terminal, `pythia-mysql approve <token>`. Pass `--confirm
   <token>` only after the approval arrives. `--yes` and loosening `policy`
   are the developer's actions, at a console.
7. **"Predicted — nothing ran" is a prediction, and is said as one.** MySQL
   commits DDL as it runs it: the preview predicts what would break, and
   the write is read back after. Never call a prediction a rehearsal, and
   never call an approved write "verified" before its report.
8. **Autopilot is the developer's delegation, not yours.** When they want
   you to work without per-write approvals, request the narrowest lease
   that fits (`pythia-mysql autopilot request`) and ask once through a
   door. Inside it, covered writes land without asking; outside it, the
   normal gate applies. A paused lease means stop and show the developer.
   Report every write with `pythia-mysql autopilot report`.
9. **Scope is what was asked.** Dependents that break are reported with a
   proposal, never fixed on your own initiative.
10. **Exit codes are the verdict:** `0` clean · `1` refused (relay the
    reason; do not route around it) · `3` written but broken, written
    unlike the prediction, or `WRITTEN?` — never report success; show the
    report and the printed restore command. Never read `$?` through a pipe.
11. **`WRITTEN?` means it may be written.** A rehearsal that wrote to a
    table MySQL cannot roll back, or a replacement that could not put the
    old routine back, is reported as such. Stop, show the developer the
    output verbatim, and let them look before anything else runs.
12. **Restores are writes.** `journal restore` previews and needs the same
    approval as any apply.
13. **"Not verified" is said plainly.** `errors` lists the views MySQL has
    marked broken; it cannot check a routine, trigger or event before it
    runs, and names them. Never report a `NOT VERIFIED` line as "no
    errors".
14. **Truncation is always announced.** If output has no truncation marker,
    you saw everything. If it has one, say so or fetch the rest with
    `--offset`.
15. **Never open `.pythia/mysql/connections.json`, or anything under
    `.pythia/mysql/grants/`.** The first holds passwords;
    `pythia-mysql connections` lists the names, users, schemas and targets
    without them. A grant written by anyone but `approve` is a forged
    approval.

## Changing pythia-mysql itself

- Run the suite before calling a change done: `python tests/test_mysql.py`
  (no database, no PyMySQL). Against a disposable server, also
  `python tests/live_check.py`. TDD: the failing test comes first.
- CI runs Ubuntu, Windows and macOS on Python 3.9 and 3.13: build paths with
  `pathlib` / `os.path.join`, and use no stdlib API newer than 3.9.
- **Queries:** every SQL statement lives in `src/pythia_mysql/queries/`,
  one per file, pyformat binds only (`%(s)s`), a literal `%` written `%%`,
  the `-- Purpose / -- Binds / -- Returns` header, and an entry in
  `QUERY_BINDS`. Where MariaDB's catalog differs, its file of the same name
  in `queries/mariadb/` (same binds, same columns, declared in
  `MARIADB_QUERY_BINDS`) answers in its place; a file only there is asked
  of MariaDB only. A query reads the same under any `sql_mode`: strings in
  single quotes, `CONCAT` never `||`, no backslash in a literal (a `LIKE`
  escapes with `'!'`). MySQL 8.4 and MariaDB 10.11 are the floors: CI
  runs the live check on 8.4, 9.4, 9.5 and on MariaDB 10.11, 11.4, 11.8,
  and nothing newer than either floor belongs in a query.
- **Dependencies:** pythia-core and PyMySQL, nothing else (a test enforces
  it).
- **Engine-neutral logic goes to pythia-core.** If an answer would be the
  same on PostgreSQL or SQL Server, it does not belong here (DESIGN.md §3).
- **Skills:** `src/pythia_mysql/skills/<name>/SKILL.md`, `name` = folder,
  prefixed `pythia-mysql-` (or `using-pythia-mysql`), description opening
  with `Use when` / `Use before`, a `**Phase:**` line, at most 150 lines
  (detail in `reference/`), and a row in `using-pythia-mysql`'s routing
  table. A test holds every one to it.
- **Docs never contradict code:** a behaviour change updates the docstring,
  README.md and README.vi.md, CHANGELOG.md and the affected skill in the
  same change. A test holds README.vi.md to README.md's headings and
  commands; the prose is translated by hand.
- **Versions** agree in pyproject.toml and `pythia_mysql.__version__`, the
  version has its CHANGELOG.md entry, and pythia-core is asked for within
  one release series (`pythia-core>=0.1.1,<0.2`). A test holds all three.

## Releasing

1. Once per project: a PyPI trusted publisher (pypi.org → your account →
   Publishing → add a pending publisher: project `pythia-mysql`, owner
   `thaildhe172591`, repository `pythia-mysql`, workflow `release.yml`,
   environment `pypi`). No token is stored anywhere.
2. pythia-core's release of the series is on PyPI first: this package asks
   for it.
3. The version in pyproject.toml and `__version__`, its CHANGELOG.md entry
   dated, and CI green on main.
4. `git tag vX.Y.Z && git push origin vX.Y.Z`: the `release` workflow runs
   the suite against pythia-core's main, checks the tag against the version
   and the changelog, and publishes.

## Never

- Read or write pythia for Oracle's files (`.pythia/connections.json`,
  `.pythia/journal/`) or another engine's (`.pythia/postgres/`,
  `.pythia/mssql/`, `.pythia/mongo/`), or take their commands or variables.
- Point the live check at a shared server: it creates an account, drops
  databases and writes through every path.
- Field-test `pythia-mysql install` inside this repository:
  `src/pythia_mysql/skills/` is the source pack. Use a scratch directory.
- Put real-world identifiers anywhere (hosts, schemas, tenants,
  credentials). Examples use APP_OWNER, PKG_ORDER, T_ORDER. Everything
  shipped is English, but for README.vi.md, the README's translation.
