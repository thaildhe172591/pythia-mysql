---
name: pythia-mysql-verify
description: Use before claiming any MySQL or MariaDB change is done, fixed, working or safe - after an apply, a deploy, a restore, or a fix to a broken view or procedure. Evidence first - exit codes, errors, the dependents - and "broken", "not verified" or "WRITTEN?" said plainly.
---

# Evidence before "done"

**Announce at start:** "Using pythia-mysql-verify — evidence before done."

**Phase:** Do — the last step of every change

MySQL accepts a procedure that names a table that does not exist; it fails
when it runs. "It applied" is not "it works", and a claim of done without
evidence costs the developer the debugging later.

## The Iron Law

```
NO COMPLETION CLAIM WITHOUT THE EVIDENCE PRINTED IN THIS SESSION
```

## The Checklist

1. **Every write's exit code, unpiped.** 0 clean; 3 written-but-broken,
   written unlike the prediction, or `WRITTEN?`. A 3 means the report starts
   with "broken" or "may be written".
2. **`pythia-mysql errors <name>`** for each view you touched, and the
   schema's `errors` against the baseline taken before the change: only new
   findings are yours.
3. **`NOT VERIFIED` is reported as such.** A procedure, function, trigger or
   event is checked by MySQL only when it runs, and a grant's effect is
   never checked: say "applied, not verified" for them, never "clean".
4. **The dependents.** If the change altered a column, a parameter or a
   result, read the `[text]` rows from `impact` again — they are where a
   run-time failure hides.
5. **`pythia-mysql lint`** on the change's files is clean of errors.
6. **The journal.** `pythia-mysql history <name>` shows the entry; quote its
   restore command in the report for a change the developer may want back.

## How to report

```
Applied p_order_paid (PROCEDURE) — exit 0, read back as written.
NOT VERIFIED: MySQL checks a procedure's names only when it runs.
Dependents: trg_order_audit [catalog], p_close_day [text] — not checked.
errors (app_owner): no new invalid view.
Restore if needed: pythia-mysql journal restore <entry>
```

Say "broken" first when it is; say "not verified" plainly when it is.

## Red Flags — STOP if you catch yourself thinking

| Thought | Reality |
|---------|---------|
| "apply printed Applied" | Read the exit code and the prediction lines, not the word. |
| "errors printed nothing" | With no NOT VERIFIED line, that is evidence. With one, it is not. |
| "The procedure was created, so it works" | MySQL checks its names when it runs. Say not verified. |
| "I'll verify after reporting" | Then the report is a guess. |
