# Working in this repository / with this tool

pythia-mysql is pythia for MySQL, on pythia-core. It is pre-alpha (Phase
9b): it reads everything pythia's Learn movement needs, and writes through
one gate — data rehearsed in a transaction, DDL predicted, written once and
read back.

## Using pythia-mysql as an agent (Phase 9b)

1. **Ask the database, never the dump.** `ls`, `src`, `cols`, `ddl`, `grep`
   against the live schema; `check` says where unqualified names land (the
   connection's database).
2. **Impact before change.** Run `pythia-mysql impact <NAME>` before
   proposing any modification. When it prints `! show this list to the
   developer` (10 or more dependents, or one in another schema), show the
   developer the list before writing code. Rows marked `[text]` are leads
   found by name in procedure, function, trigger and event bodies — MySQL
   records none of their dependencies — not proofs. Relay the `blind spot`
   lines, and never call an impact list complete.
3. **What MySQL hides is a blind spot, not an absence.** Without
   `SHOW_ROUTINE`, `TRIGGER` or `EVENT`, MySQL hides routines, triggers or
   events from this account; pythia-mysql says so. Never report "no
   triggers" when a line says they are hidden.
4. **Writes go through `pythia-mysql apply` (one statement per file)
   only.** Never write through the `mysql` client, MySQL Shell, Workbench
   or a driver script: those have no snapshot, no rehearsal or prediction,
   and no journal.
5. **The developer sees every preview.** Relay `apply`'s preview verbatim:
   the diff, the rehearsal or the prediction (what would break, or NOT
   VERIFIED), the rows, the notes (a replacement, a definer that changes),
   the destructive warning. Until the harness exists (Phase 9c) the only
   door is the developer's terminal: `pythia-mysql approve <token>`. Pass
   `--confirm <token>` only after the approval arrives. `--yes` and
   loosening `policy` are the developer's actions, at a console.
6. **"Predicted — nothing ran" is a prediction, and is said as one.** MySQL
   commits DDL as it runs it: the preview predicts what would break, and
   the write is read back after. Never call a prediction a rehearsal, and
   never call an approved write "verified" before its report.
7. **Scope is what was asked.** Dependents that break are reported with a
   proposal, never fixed on your own initiative.
8. **Exit codes are the verdict:** `0` clean · `1` refused (relay the
   reason; do not route around it) · `3` written but broken, written unlike
   the prediction, or `WRITTEN?` — never report success; show the report
   and the printed restore command. Never read `$?` through a pipe.
9. **`WRITTEN?` means it may be written.** A rehearsal that wrote to a
   table MySQL cannot roll back, or a replacement that could not put the
   old routine back, is reported as such. Stop, show the developer the
   output verbatim, and let them look before anything else runs.
10. **Restores are writes.** `journal restore` previews and needs the same
    approval as any apply.
11. **"Not verified" is said plainly.** `errors` lists the views MySQL has
    marked broken; it cannot check a routine, trigger or event before it
    runs, and names them. Never report a `NOT VERIFIED` line as "no
    errors".
12. **Truncation is always announced.** If output has no truncation marker,
    you saw everything. If it has one, say so or fetch the rest with
    `--offset`.
13. **Never open `.pythia/mysql/connections.json`, or anything under
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
  `QUERY_BINDS`. A query reads the same under any `sql_mode`: strings in
  single quotes, `CONCAT` never `||`, no backslash in a literal (a `LIKE`
  escapes with `'!'`). MySQL 8.4 is the floor: CI runs the live check on
  8.4, 9.4 and 9.5, and nothing newer than 8.4 belongs in a query.
- **Dependencies:** pythia-core and PyMySQL, nothing else (a test enforces
  it).
- **Engine-neutral logic goes to pythia-core.** If an answer would be the
  same on PostgreSQL or SQL Server, it does not belong here (DESIGN.md §3).
- **Docs never contradict code:** a behaviour change updates the docstring,
  README.md and README.vi.md and CHANGELOG.md in the same change. A test
  holds README.vi.md to README.md's headings and commands; the prose is
  translated by hand.
- **Versions** agree in pyproject.toml and `pythia_mysql.__version__`, the
  version has its CHANGELOG.md entry, and pythia-core is asked for within
  one release series (`pythia-core>=0.1.1,<0.2`). A test holds all three.

## Never

- Read or write pythia for Oracle's files (`.pythia/connections.json`,
  `.pythia/journal/`) or another engine's (`.pythia/postgres/`,
  `.pythia/mssql/`, `.pythia/mongo/`), or take their commands or variables.
- Point the live check at a shared server: it creates an account, drops
  databases and writes through every path.
- Put real-world identifiers anywhere (hosts, schemas, tenants,
  credentials). Examples use APP_OWNER, PKG_ORDER, T_ORDER. Everything
  shipped is English, but for README.vi.md, the README's translation.
