---
name: using-pythia-mysql
description: Use when starting any conversation that touches MySQL or MariaDB, a schema, a stored procedure, a function, a trigger, an event or a view - it picks the right pythia-mysql skill BEFORE any response or action, including clarifying questions. Fires on plain requests in any language - "build/add/fix/explain/review X", "lam/them/sua/tao/giai thich/kiem tra X" (Vietnamese, with or without diacritics). Also use whenever unsure which pythia-mysql skill applies.
---

# Using pythia-mysql — the pocket handbook

**Phase:** Learn → Ask → Do — this page opens the right one

pythia-mysql is pythia for MySQL and MariaDB. Its one job here is
consistency: whether
a session measures the blast radius and asks before it writes should not
depend on the agent's mood that day.

## The Rule

If there is even a small chance a pythia-mysql skill applies, open it
**before acting** — before answering, before exploring, before clarifying
questions. Opened the wrong one? Close it, no harm done.

## Route by what the developer said

| The request sounds like | Open first | Then |
|---|---|---|
| "explain X / why / how does it work" ("giải thích") | `pythia-mysql-explore` | |
| "is it safe to touch X" | `pythia-mysql-impact` | |
| "change / fix / add X" ("sửa", "thêm") | `pythia-mysql-impact` | write, then `pythia-mysql-apply` |
| "land / apply this" — one statement | `pythia-mysql-apply` | `pythia-mysql-verify` |
| "run this data fix / backfill / batch" ("chạy script") | `pythia-mysql-deploy` | `pythia-mysql-verify` |
| "do it all without asking me" ("tự động hoàn toàn") | `pythia-mysql-autopilot` — one lease, never a blank cheque | the task's own skills |
| "undo / restore X" | `pythia-mysql-apply` (a restore is a write) | `pythia-mysql-verify` |
| an error from MySQL, a broken view or procedure | `pythia-mysql-explore` (`errors`, `src`) | |
| about to say done / fixed / works | `pythia-mysql-verify` — evidence first | |
| setup, connection failures, the hooks not running | `pythia-mysql doctor`, then `pythia-mysql check` | |

Priority when several apply: **process before construction** — impact
before writing, apply's preview before any write, verify before "done".
Announce the skill you opened ("Using pythia-mysql-impact — ...") so the
developer sees which page you are on.

## A request with open decisions

A change that leaves real decisions open — data kept or deleted, a column's
type, who may run a procedure (its DEFINER, SQL SECURITY), a security or
audit trade-off — becomes questions with options and a recommendation,
asked **before** any code is written. A new decision found mid-build stops
the build.

## Red flags

| Thought | Reality |
|---------|---------|
| "This task is simple" | Simple tasks hide decisions; ask the open ones first. |
| "I'll just run it in the mysql client / Workbench" | Those have no snapshot, no rehearsal or prediction, no journal. The guard denies the client. |
| "I remember the schema" | The live catalog is the truth; a dump drifts. `pythia-mysql ls`. |
| "No triggers on that table" | Unless a blind spot says MySQL hides them from this account. Read it. |
| "I remember what that skill says" | Open the current page. |

## Session state

The session-start brief ends with `STATE` lines: the connections (the
default is starred) and the write policy per group. Read them before
deciding whether a write is even allowed — `data_dml`, `structural` and
`grants` are `deny` until the developer says otherwise.

No STATE line this session means the hooks are not running and the guard
is off: say so to the developer before any write and ask them to run
`pythia-mysql doctor`. Every rule still binds.
