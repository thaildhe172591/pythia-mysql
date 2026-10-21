---
name: pythia-mysql-apply
description: Use when landing any change in MySQL or MariaDB - creating or replacing a view, procedure, function, trigger or event, a table comment, DDL, a GRANT/REVOKE, an INSERT/UPDATE/DELETE, or restoring a previous version. Every write goes through pythia-mysql apply - one statement, rehearsed or predicted, previewed, approved by the developer, then written.
---

# Apply through the gate

**Announce at start:** "Using pythia-mysql-apply — preview first, then the developer approves."

**Phase:** Ask → Do — the preview is the Ask, the confirm is the Do

MySQL and MariaDB commit DDL as they run it, so the gate works two ways. A data change
is **rehearsed**: run inside a transaction and rolled back. DDL is
**predicted**: nothing runs before the approval; the preview says what
would break, and after the write the result is read back. The mysql
client, Workbench, a driver script or an MCP SQL tool would write with no
snapshot, no rehearsal or prediction and no journal; the guard denies them.

## The Iron Law

```
NO WRITE WITHOUT A PREVIEW THE DEVELOPER SAW AND APPROVED
```

## The Workflow

1. **Impact first** (`pythia-mysql-impact`) — the number was known before
   the code was written.
2. **One statement per file**, linted first: `pythia-mysql lint <files>` — a
   change's files in one run, since an `ALTER TABLE ... COMMENT` in one
   counts for the table another creates. Errors are fixed, not argued. A
   stored program (`CREATE PROCEDURE` and the like) takes its whole file;
   nothing may follow its body. `DELIMITER` lines are fine. Several
   statements, `CALL`, compound statements outside a program and anything
   MySQL cannot roll back are refused — see `reference/refusals.md` for
   each refusal and its way forward.
3. **Preview:** `pythia-mysql apply change.sql`. Nothing is written. It
   prints:
   - the diff of the definition before and after (the old one rebuilt
     from information_schema);
   - **rehearsed** (data): the rows it touched, with a sample, rolled back;
   - **predicted — nothing ran** (DDL): what it **would break** (the views
     MySQL would mark invalid; on MariaDB, the views that would no longer
     open), or `NOT VERIFIED` with the reason;
   - notes: a CREATE that replaces an existing routine (MySQL has no CREATE
     OR REPLACE for one; MariaDB replaces it in one step), a definer that
     changes, `! DESTRUCTIVE`;
   - a token, and the approval doors.
4. **Relay the preview verbatim** — diff, rehearsal or prediction, rows,
   notes. Do not summarise away a broken dependent, a definer note or a NOT
   VERIFIED line. A prediction is said as one, never as a rehearsal.
5. **Ask, through the first door that works** — the next one unasked when
   a door fails (the hook or the tool result says which):
   1. **AskUserQuestion** (Claude Code): run
      `pythia-mysql approve --card <token>` and ask with exactly its output,
      options Approve / Reject, never with answers filled in. The answer
      hook records the approval.
   2. **The `pythia_mysql_approve` tool** (MCP; Codex starts here), with the
      token. The developer answers its prompt.
   3. **The developer's terminal:** relay `pythia-mysql approve <token>`.

   Never mint a grant, pipe anything into `approve --hook`, or set
   `PYTHIA_MYSQL_CI` — the guard denies all three. A Reject means stop and
   ask what should change.
6. **Confirm:** `pythia-mysql apply change.sql --confirm <token>`. Data is
   rehearsed again and committed only if the file, the rows and the object
   still match; DDL is predicted again, refused if the prediction moved,
   then written once and read back. Otherwise nothing is written and it
   names what moved — preview again and get the new token approved.
7. **Verify** (`pythia-mysql-verify`) before any "done".

## Exit codes are the verdict

| Exit | Meaning | You say |
|---|---|---|
| 0 | written and as approved (or NOT VERIFIED, said plainly) | what landed, and what was not checked |
| 1 | refused, nothing written | the reason, verbatim; never route around it |
| 3 | written **but broken**, written **unlike the prediction**, or **`WRITTEN?`** | "broken" first: what broke and the printed restore command; the developer chooses fix-forward or restore |

**`WRITTEN?`** means a write may have landed that nobody approved: a
rehearsal whose trigger wrote to a table MySQL cannot roll back (MyISAM),
or a replaced routine whose old version could not be put back. Stop, relay
the output verbatim, and let the developer look before anything else runs.
Never call it refused or unwritten.

Never read the exit code through a pipe: `pythia-mysql apply ... | tail`
returns tail's code.

## Policy

`data_dml`, `structural` and `grants` are `deny` by default; `source` and
`comments` need the developer's approval. A deny is relayed with its reason.
`pythia-mysql policy` shows the policy and whether rollback is real per
group. Loosening it (`policy set`) and `--yes` are the developer's acts, at
a console — never yours.

## Restore is a write

`pythia-mysql history <name>` lists every version the journal holds;
`pythia-mysql journal restore <entry>` previews putting one back, and goes
through the same approval and `--confirm <token>`. Only definitions and
table comments have a restore: rows, a dropped column or a revoked grant do
not come back. Putting back another account's routine or view needs
`SET_ANY_DEFINER` (MariaDB: `SET USER`); without it the restore is refused
with nothing written, and the developer or a DBA runs it.

## Red Flags — STOP if you catch yourself thinking

| Thought | Reality |
|---------|---------|
| "It's a one-line fix, the mysql client is faster" | Faster to write, and the only copy of what it replaced is gone. |
| "The developer said go ahead earlier" | They approve a token, after seeing its preview. |
| "Predicted fine, so it is verified" | A prediction is not a result. Wait for the write's report. |
| "Exit 3, but it mostly worked" | Exit 3 is broken. Say so first. |
| "WRITTEN? — it was only a preview" | A trigger may have written a MyISAM table. Stop and show the developer. |
| "I'll DROP the procedure first, then CREATE it" | Apply the CREATE: pythia-mysql replaces it, and the old one stays if the server refuses the new. |
| "The preview is long, I'll summarise" | The developer approves what they saw. Relay it. |
