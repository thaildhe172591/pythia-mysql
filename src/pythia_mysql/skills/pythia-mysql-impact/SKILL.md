---
name: pythia-mysql-impact
description: Use before proposing or writing any change to a MySQL object - a procedure, function, trigger, event, view, table or column. Impact analysis comes first, because what depends on an object decides how careful the change must be.
---

# Impact Before Change

**Announce at start:** "Using pythia-mysql-impact to measure the blast radius first."

**Phase:** Learn — and the first Ask gate: a large blast radius reaches the developer before any code is written

A dropped column breaks every view that reads it — MySQL marks them invalid
— and every procedure that names it, when it next runs: MySQL keeps a
routine whose names no longer resolve. The cost of knowing first is one
command.

## The Iron Law

```
NO CHANGE PROPOSED WITHOUT ITS IMPACT MEASURED FIRST
```

## The Workflow

1. `pythia-mysql impact <name> --depth 2` — everything that depends on it,
   as a tree, ending with the summary:
   `-- impact: N dependent objects (... matched by name as text ...)`.
2. `pythia-mysql deps <name> --depth 2` — the other direction, what it uses;
   read it when the change touches calls or table access.
3. `pythia-mysql errors` — the baseline. Anything broken before the change
   must not be blamed on it later.

## Reading the numbers

| Result | What to do |
|---|---|
| 0 dependents | Say so, with the output and its blind spots as evidence, and proceed. |
| 1–9 dependents | List them to the developer alongside the proposal. |
| `! show this list to the developer` (10+, or one in another schema) | Show the tree and get an explicit go-ahead **before writing any code**. |
| `[text]` rows | Leads found by name in routine, trigger and event bodies: name them as such. |
| `-- blind spot:` lines | Relay them. Never call the list complete. |

What counts: views that read a table or view or call a function (the
catalog), the triggers on a table, tables whose foreign keys point at it —
and every procedure, function, trigger and event whose body names it, in
any schema this account can see (`[text]`). MySQL hides routines, triggers
and events from an account without `SHOW_ROUTINE`, `TRIGGER` or `EVENT`;
the blind spots say when.

## Red Flags — STOP if you catch yourself thinking

| Thought | Reality |
|---------|---------|
| "It's just a small helper" | Helpers are the most-depended-on objects there are. |
| "I'll check impact after writing the code" | Then the number cannot change the design. Too late. |
| "The catalog shows no dependents, so nothing calls it" | MySQL records nothing for routine bodies — read the `[text]` rows and blind spots. |
| "apply's preview shows what breaks anyway" | That confirms a number you should already know; it is not discovery. |

## Hand-off

Impact known and acceptable → write the change (one statement per file) →
`pythia-mysql-apply` to land it through the gate.
