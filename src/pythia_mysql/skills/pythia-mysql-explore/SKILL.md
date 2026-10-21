---
name: pythia-mysql-explore
description: Use when explaining, investigating or reading MySQL objects - what a procedure does, where a table is used, why something fails, what a schema holds. Asks the live database through pythia-mysql read commands, never a dump, Workbench scripts or memory.
---

# Explore the live database

**Announce at start:** "Using pythia-mysql-explore to read the live database."

**Phase:** Learn — facts from the catalog, before any opinion

A repository's SQL files drift from the database: a procedure changed in
Workbench, an index added by hand, a trigger nobody scripted out. An
explanation built on the dump is an explanation of a database that does
not exist.

## The Iron Law

```
EVERY FACT COMES FROM THE LIVE CATALOG, WITH THE COMMAND THAT SHOWED IT
```

## The commands

| Question | Command |
|---|---|
| Where am I, and where do unqualified names land? | `pythia-mysql check` |
| Which objects match a name? | `pythia-mysql ls "t_order%"` |
| What does this procedure / function / view / trigger / event say? | `pythia-mysql src <name>` |
| What columns does this table or view have? | `pythia-mysql cols <name>` |
| What statements would create it? | `pythia-mysql ddl <name>` |
| Where is this text used in stored code? | `pythia-mysql grep <text>` |
| What does it use? | `pythia-mysql deps <name>` |
| What uses it? | `pythia-mysql impact <name>` (see `pythia-mysql-impact`) |
| What is broken now? | `pythia-mysql errors [<name>]` |

`--json` gives structured output on every command. MySQL keeps no line
numbers and no CREATE statement: `src` rebuilds the header on line 1 and
shows the body as it was written below it; a view's SELECT only as MySQL
rewrote it.

## Reading the output honestly

- **Truncation is announced.** No `-- truncated` line means you saw
  everything. With one, say so, or fetch the rest with `--offset` /
  `--limit 0`.
- **`[text]` rows are leads, not proofs.** MySQL records nothing about what
  a procedure, function, trigger or event body uses; pythia-mysql finds
  names in those bodies and marks them. Say which rows are which.
- **`-- blind spot:` lines are part of the answer.** MySQL hides routines
  from an account without `SHOW_ROUTINE`, triggers without `TRIGGER` and
  events without `EVENT`, and other schemas as far as privileges stop.
  Relay them; "no triggers" is not an answer while one says they are
  hidden.
- **`errors` lists the views MySQL has marked invalid.** It cannot check a
  routine, trigger or event before it runs — MySQL resolves their names
  only then — so it names them as unchecked: a `NOT VERIFIED` line is never
  "no errors".

## Red flags

| Thought | Reality |
|---------|---------|
| "The migration file shows the table" | The database may not. `pythia-mysql cols`. |
| "`errors` printed nothing, so it is clean" | Only if no NOT VERIFIED line was printed. |
| "I'll open connections.json to see the host" | Never: `pythia-mysql connections` lists it without passwords. |
| "I'll check it in the mysql client quickly" | Read commands answer it, with truncation and blind spots said. |

## Hand-off

Explaining only → done, with the commands quoted. A change follows →
`pythia-mysql-impact` before any code is written.
