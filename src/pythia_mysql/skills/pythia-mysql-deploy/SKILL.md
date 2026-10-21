---
name: pythia-mysql-deploy
description: Use when landing several MySQL data changes together - a backfill, a data fix across tables, inserts, updates and deletes that must land all or none, or more than one file of them. pythia-mysql deploy rehearses the whole release in one transaction and lands all of it or none of it, under one approval.
---

# Deploy data changes as one transaction

**Announce at start:** "Using pythia-mysql-deploy — the release is rehearsed as one, then approved as one."

**Phase:** Ask → Do — one card for the whole release is the Ask; the confirm is the Do

On InnoDB, inserts, updates and deletes can run in one transaction: if the
fifth fails, the first four are not left half-landed. Running them through
`mysql < fix.sql` gives that up, and the snapshot, the rehearsal and the
journal with it.

## The Iron Law

```
A RELEASE LANDS WHOLE, AS APPROVED, OR NOT AT ALL
```

## The Workflow

1. **Impact first** (`pythia-mysql-impact`) for every table the release
   changes.
2. **The scripts:** data statements in the order they must run — one file
   or several, named in that order on the command line, each statement
   ended by `;`. Only data belongs here: `INSERT`, `REPLACE`, `UPDATE`,
   `DELETE` (`pythia-mysql-apply`'s refusals hold for each).
3. **Preview:** `pythia-mysql deploy 01_fix.sql 02_backfill.sql`. Every
   statement runs in order inside one transaction, each against what the
   ones before it left, and then everything rolls back. One card shows
   every statement, the rows each touches, and one 10-digit token. Rows the
   release itself inserts get a new AUTO_INCREMENT value, `CURRENT_TIMESTAMP`
   or `UUID()` on every run, so an UPDATE or DELETE of them can never match
   its approval: give those rows their final values in the INSERT.
4. **Relay the card verbatim**, then ask through the doors exactly as
   `pythia-mysql-apply` does — AskUserQuestion with the output of
   `pythia-mysql approve --card <token>`, then the `pythia_mysql_approve`
   tool, then `pythia-mysql approve <token>` in the developer's terminal. A
   statement's own token is refused: a release is approved as a whole.
5. **Confirm:** the same command with `--confirm <token>` and the same files
   in the same order. It checks every statement is byte-identical to what
   was approved, runs the release again in one transaction, and commits
   only if every statement still matches — its rows, its count. Otherwise
   the whole release rolls back, says which statement moved, and the
   approval stays unspent.
6. **Verify** (`pythia-mysql-verify`).

## What a release cannot hold

DDL — a table, a column, an index, a view, a routine, a trigger, an event, a
grant: MySQL commits each as it runs it, so it is predicted, not rehearsed,
and a release that lands all or nothing cannot hold it. `deploy` refuses
the release and rolls everything back — apply each DDL statement on its own,
in order, before or after the data. A trigger that writes to a MyISAM table
during the rehearsal, or a commit that does not answer, is reported
`WRITTEN?`: stop, and show the developer.

## Red Flags — STOP if you catch yourself thinking

| Thought | Reality |
|---------|---------|
| "`mysql < backfill.sql` is how fixes run" | Not here: no rehearsal, no snapshot, no all-or-nothing. The guard denies it. |
| "I'll add the new column to the release" | Refused: DDL is predicted, not rehearsed. Apply it on its own first. |
| "Just one more statement after approval" | The scripts changed: nothing runs. Preview again. |
| "It rolled back, so I'll retry with --yes" | `--yes` is the developer's flag. Find what moved, preview again. |

## When NOT to use this skill

- One statement → `pythia-mysql-apply`.
- Any DDL → `pythia-mysql-apply`, one statement at a time.
