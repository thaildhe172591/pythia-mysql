"""The write tier for MySQL: reading MySQL's SQL, rehearsing data and
predicting DDL.

MySQL runs no DDL inside a transaction: every CREATE, ALTER, DROP, RENAME,
TRUNCATE, GRANT and REVOKE commits implicitly, and commits whatever was
pending with it. So the write path splits in two (pythia-core DESIGN.md §8,
question 6):

- Data (INSERT, REPLACE, UPDATE, DELETE) is REHEARSED in the transaction
  pythia-core owns, and rolled back, or committed whole. A trigger or a
  function that writes to a table MySQL cannot roll back (MyISAM, MEMORY)
  would turn a preview into a write: the statement runs first inside a
  savepoint, and MySQL's warning 1196 on rolling that back reports the
  write as escaped. A statement whose own table cannot roll back is
  refused before it runs.
- DDL is PREDICTED: nothing runs before the approval. A view's SELECT runs
  with LIMIT 0; the views MySQL would mark invalid are read from
  information_schema (it marks every view that reads a dropped table,
  view, function or column, and every view on top of those); a routine is
  named NOT VERIFIED — MySQL checks its names only when it runs. After the
  approval the statement runs once, and the views MySQL marked invalid are
  read back and compared with the prediction.

MySQL has no CREATE OR REPLACE for a procedure, function, trigger or event,
so apply of a CREATE for one that exists replaces it: a procedure or
function is first created under a scratch name, so that MySQL's verdict on
the new text costs nothing; then the old one is dropped and the new one
created, and if MySQL refuses it the old one is put back from the snapshot.

A statement is read with MySQL's own quoting: '...' and "..." strings
(doubled quotes and backslash escapes inside), `backticked` names, #, --
and /* */ comments. An executable comment /*! ... */ is code to MySQL, and
is refused. DELIMITER lines are read as the mysql client reads them.
"""
import re
import sys

from pythia_core.output import cell

from .catalog import fold, ident, like_contains, literal, q, sql_of
from .read import HIDDEN, error_text, refers_to, statements

SAMPLE_ROWS = 10
SCRATCH = "__pythia_check"          # a routine checked under this suffix first
NOT_ROLLED_BACK = 1196              # "Some non-transactional changed tables couldn't be rolled back"
LOST = (2006, 2013)                 # the server went away; the connection was lost


class Lexed:
    def __init__(self, masked, uncommented, cuts, unterminated, executable):
        self.masked = masked                # same length; literal, name and comment contents blanked
        self.uncommented = uncommented      # same length; only comments blanked
        self.cuts = cuts                    # positions of the ';' that end statements
        self.unterminated = unterminated    # ends inside a quote or a comment
        self.executable = executable        # holds a /*! ... */ comment MySQL runs


def lex(text):
    """Blank out string contents, `names` and comments (every position and
    newline kept, the quote characters too), and find the semicolons."""
    out, bare = list(text), list(text)
    cuts, unterminated, executable = [], False, False
    n, i = len(text), 0

    def blank(a, b, comment=False):
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "
                if comment:
                    bare[k] = " "

    while i < n:
        c = text[i]
        # "--" starts a comment only when a space or a line end follows it
        if c == "#" or (text.startswith("--", i) and (i + 2 >= n or text[i + 2] in " \t\r\n")):
            j = text.find("\n", i)
            j = n if j < 0 else j
            blank(i, j, comment=True)
            i = j
        elif text.startswith("/*", i):
            executable |= text.startswith("/*!", i)
            j = text.find("*/", i + 2)
            unterminated |= j < 0
            j = n if j < 0 else j + 2
            blank(i, j, comment=True)
            i = j
        elif c in "'\"`":
            j, closed = i + 1, False
            while j < n:
                if text[j] == "\\" and c != "`":
                    j += 2
                    continue
                if text[j] == c:
                    if text.startswith(c * 2, j):
                        j += 2
                        continue
                    closed, j = True, j + 1
                    break
                j += 1
            unterminated |= not closed
            blank(i + 1, j - 1 if closed else n)    # the quotes stay
            i = min(j, n)
        else:
            if c == ";":
                cuts.append(i)
            i += 1
    return Lexed("".join(out), "".join(bare), cuts, unterminated, executable)


def _code(stmt):
    """The statement's code: literals, names and comments blanked, lower
    case, one space between words."""
    return " ".join(lex(stmt).masked.lower().split())


# --- statements, cut as the mysql client cuts them --------------------------------------

_DELIMITER = re.compile(r"(?im)^[ \t]*delimiter[ \t]+(\S+)[ \t]*$")
_Q = r"(?:`[^`]*`|'[^']*'|\"[^\"]*\"|[\w.$%-]+)"   # a name or a quoted value, as masked
_PROGRAM = re.compile(r"create(?: or replace)?(?: algorithm ?= ?\w+)?"
                      r"(?: definer ?= ?(?:current_user(?: ?\( ?\))?|" + _Q + r"(?: ?@ ?" + _Q + r")?))?"
                      r"(?: sql security \w+)? (?:aggregate )?(procedure|function|trigger|event)\b")


def _stored_program(code):
    m = _PROGRAM.match(code)
    return m.group(1) if m else None


def _pieces(text):
    """(offset, statement) in order. Under a DELIMITER other than ';' a
    statement ends at the delimiter; under ';' a stored program's body —
    whose statements end in ';' themselves — runs to the end of its text,
    and anything else ends at its ';'."""
    masked = lex(text).masked
    segments, delim, start = [], ";", 0
    for m in _DELIMITER.finditer(masked):
        segments.append((start, m.start(), delim))
        delim, start = m.group(1), m.end()
    segments.append((start, len(text), delim))
    out = []
    for a, b, d in segments:
        seg, mseg = text[a:b], masked[a:b]
        if d == ";":
            cuts = [k for k in lex(seg).cuts]
        else:
            cuts, k = [], mseg.find(d)
            while k >= 0:
                cuts.append(k)
                k = mseg.find(d, k + len(d))
        size = 1 if d == ";" else len(d)
        s = 0
        for cut in cuts + [len(seg)]:
            piece = mseg[s:cut]
            if d == ";" and _stored_program(" ".join(piece.lower().split())):
                end = len(mseg.rstrip().rstrip(";").rstrip())
                out.append((a + s, seg[s:end]))
                break
            if piece.strip():
                out.append((a + s, seg[s:cut]))
            s = cut + size
    return out


def split_script(text):
    """(line, statement) for each statement of a script, the line where its
    code starts."""
    out = []
    for start, piece in _pieces(text):
        code = lex(piece).masked
        first = start + len(code) - len(code.lstrip())
        out.append((text.count("\n", 0, first) + 1, piece.strip()))
    return out


def split_statements(text):
    return [s for _, s in split_script(text)]


# --- classification --------------------------------------------------------------------

TXN = ("pythia-mysql owns the transaction: it rolls a preview back and commits "
       "only an approved write. Leave transaction control out of the file.")
FLOW = ("Compound statements (DECLARE, IF, WHILE, LOOP, BEGIN ... END) run only "
        "inside a stored program. Put the logic in a procedure and apply that.")
READS = ("apply takes writes; reads go through ls, src, cols and grep — and a "
         "SELECT can call a function that writes, or write a file with INTO "
         "OUTFILE, so it is refused, not run.")
RUNS = ("CALL, DO, PREPARE and EXECUTE run code that can do anything — no policy "
        "group honestly fits. Run it by hand, or apply the statements it would run.")
SERVER = ("This acts on the server, not inside one schema, and pythia-mysql writes "
          "inside one schema. A DBA runs it by hand.")
CANNOT = ("Cannot classify this statement, so it is refused rather than guessed "
          "at. apply takes one CREATE VIEW / PROCEDURE / FUNCTION / TRIGGER / EVENT, "
          "ALTER TABLE ... COMMENT, INSERT / REPLACE / UPDATE / DELETE, DDL, GRANT / "
          "REVOKE on a schema or SET statement per file.")
MANY = ("{n} statements in one file — apply takes one statement per file, so "
        "each is previewed, approved and journaled on its own (deploy takes a "
        "script). End every statement with ';'.")

RULES = (
    (r"(start transaction|begin|commit|rollback|savepoint|release savepoint|xa|"
     r"(lock|unlock) (table|tables|instance)|set (session |local |global )?"
     r"(transaction|autocommit)|set @@(session\.|local\.)?autocommit)\b", None, TXN),
    (r"(declare|if|while|loop|repeat|leave|iterate|return|signal|resignal|"
     r"get (current |stacked )?diagnostics)\b", None, FLOW),
    (r"use\b", None, "USE changes the schema for every later statement. Connect to "
     "the right schema instead (a connection, --conn)."),
    (r"with\b", None, "A WITH statement is refused: a CTE in front of an UPDATE or "
     "DELETE hides which rows it touches. Write it as a plain statement."),
    (r"(select|table|values|show|describe|desc|explain|help|\()", None, READS),
    (r"(call|do|prepare|execute|deallocate|handler)\b", None, RUNS),
    (r"(load (data|xml|index)|import table)\b", None, "LOAD and IMPORT read files "
     "on a server or a client: no preview can show their rows. Load the data with "
     "INSERT statements, or a DBA loads it by hand."),
    (r"create (temporary table|table .*\btemporary\b)", None, "A temporary table dies "
     "with this connection, which ends after the command: nothing would be left to "
     "verify or undo."),
    (r"create (aggregate )?function \S+ returns \w+ soname\b", None, SERVER),
    (r"((create|alter|drop) (database|schema|tablespace|logfile group|server|"
     r"spatial reference system|resource group|undo tablespace)|"
     r"(create|alter|drop|rename) (user|role)|(install|uninstall) (plugin|component)|"
     r"flush|kill|reset|purge|change (master|replication)|"
     r"(start|stop) (slave|replica|group_replication)|shutdown|restart|clone|"
     r"set (global|persist|persist_only|password|default role|role|resource group)\b|"
     r"set @@(global|persist|persist_only)\.|cache index|binlog)\b", None, SERVER),
    (r"(optimize|repair|analyze|check|checksum) (no_write_to_binlog |local )?"
     r"(table|tables)\b", None, "OPTIMIZE, REPAIR, ANALYZE and CHECK maintain a table: "
     "they run by hand, when a DBA picks the time."),
    (r"(create|alter)(?: or replace)?(?: algorithm ?= ?\w+)?"
     r"(?: definer ?= ?(?:current_user(?: ?\( ?\))?|" + _Q + r"(?: ?@ ?" + _Q + r")?))?"
     r"(?: sql security \w+)? (view|procedure|function|trigger|event)\b", "source", None),
    (r"alter table " + _Q + r"(?: ?\. ?" + _Q + r")? comment ?=? ?'[^']*'$", "comments",
     None),
    (r"(insert|replace|update|delete)\b", "data_dml", None),
    (r"(grant|revoke)\b", "grants", None),
    (r"set\b", "session", None),
    (r"(create|alter|drop|rename|truncate)\b", "structural", None),
)

_GRANT_ON = re.compile(r"(?:grant|revoke)\b(?:(?!\bon\b).)*\bon\s+(?:(?:table|procedure|"
                       r"function)\s+)?(\S+)\s+(?:to|from)\b", re.I | re.S)


def _grant_scope(stmt):
    """None when a GRANT or REVOKE acts inside a schema, else why it is refused."""
    m = _GRANT_ON.match(" ".join(lex(stmt).uncommented.split()))
    if not m:
        return ("GRANT and REVOKE of a role act on the server: MySQL's roles and "
                "accounts live outside every schema. A DBA runs it by hand.")
    if m.group(1).startswith("*.*"):
        return ("ON *.* grants across the whole server. pythia-mysql writes inside "
                "one schema: grant on `schema`.* or on an object, or a DBA runs it.")
    if re.match(r"(?i)proxy\b", m.group(0).split()[1]):
        return SERVER
    return None


def classify(text):
    """(group, None) or (None, why it is refused)."""
    lexed = lex(text)
    if lexed.unterminated:
        return None, ("The file ends inside a quote, a `name` or a comment, so it "
                      "cannot be read safely — refused.")
    if lexed.executable:
        return None, ("An executable comment /*! ... */ is code to MySQL, run "
                      "whenever the server's version allows: write the statement "
                      "plainly, so the preview shows what runs.")
    stmts = split_statements(text)
    if not stmts:
        return None, "The file holds no statement."
    first = _code(stmts[0])
    for pattern, _group, why in RULES[:2]:     # BEGIN ...; ... reads as several
        if re.match(pattern, first):
            return None, why
    if len(stmts) > 1:
        return None, MANY.format(n=len(stmts))
    if _stored_program(first) and _code_after_program(stmts[0]):
        return None, MANY.format(n="Several") + (
            " Under ';' a stored program takes the whole file, so nothing may follow "
            "its body — if what follows is the program's own, a name in it reads as "
            "END: quote it.")
    for pattern, group, why in RULES:
        if re.match(pattern, first):
            head = _SOURCE_HEAD.match(lex(stmts[0]).uncommented)
            if group == "source" and head and head.group("ine"):
                return None, ("IF NOT EXISTS leaves an existing object as it is. Write "
                              "CREATE: pythia-mysql previews replacing it, or creating "
                              "it new.")
            if group == "source" and re.match(r"alter event\b.*\brename to\b", first):
                return None, ("ALTER EVENT ... RENAME TO leaves the old name's restore "
                              "behind: write DROP EVENT and CREATE EVENT instead.")
            if group == "grants":
                why = _grant_scope(stmts[0])
                if why:
                    return None, why
            return group, why
    return None, CANNOT


_BLOCKS = re.compile(r";|\bend\b(?: (?:if|loop|while|repeat|case)\b)?|\b(?:begin|case)\b")


def _code_after_program(stmt):
    """Whether a stored program's text runs on past its body: under ';' a
    program takes its whole text, so a statement after its last END — or
    after the ';' of a body with no BEGIN — would read as part of it."""
    code = " ".join(lex(stmt).masked.lower().split())
    depth = 0
    for m in _BLOCKS.finditer(code):
        token = m.group(0)
        if token == ";":
            if depth == 0 and code[m.end():].strip(" ;"):
                return True
        elif token in ("begin", "case"):
            depth += 1
        elif token in ("end", "end case"):
            depth = max(depth - 1, 0)
    return False


def prepare_statement(text, group):
    return split_statements(text)[0]


# --- what a statement names ------------------------------------------------------------

_ID = r"(?:`(?:[^`]|``)*`|\"(?:[^\"]|\"\")*\"|[\w$]+)"
_NAME = r"(?P<schema>" + _ID + r"\s*\.\s*)?(?P<name>" + _ID + r")"
_VAL = r"(?:`(?:[^`]|``)*`|'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|[\w.$%-]+)"
_DEFINER = (r"definer\s*=\s*(?P<definer>current_user(?:\s*\(\s*\))?|" + _VAL
            + r"(?:\s*@\s*" + _VAL + r")?)\s+")
_SOURCE_HEAD = re.compile(
    r"\s*(?P<verb>create|alter)\s+(?P<replace>or\s+replace\s+)?(?:algorithm\s*=\s*\w+\s+)?"
    r"(?:" + _DEFINER + r")?(?:sql\s+security\s+\w+\s+)?(?:aggregate\s+)?"
    r"(?P<kind>view|procedure|function|trigger|event)\s+(?P<ine>if\s+not\s+exists\s+)?"
    + _NAME, re.I)
_TRIGGER_ON = re.compile(r"\s+(?:before|after)\s+(?:insert|update|delete)\s+on\s+"
                         r"(?P<tschema>" + _ID + r"\s*\.\s*)?(?P<table>" + _ID + r")", re.I)
_COMMENT_HEAD = re.compile(r"\s*alter\s+table\s+" + _NAME + r"\s+comment\s*=?\s*"
                           r"(?P<value>'(?:[^'\\]|''|\\.)*'|\"(?:[^\"\\]|\"\"|\\.)*\")", re.I | re.S)


def _qualified(m, schema_group="schema", name_group="name"):
    part = m.group(schema_group)
    return (fold(part.strip().rstrip(".").strip()) if part else None,
            fold(m.group(name_group)))


def _string_value(token):
    """A MySQL string literal's value: '' and \\x unescaped."""
    body, quote = token[1:-1], token[0]
    out, i = [], 0
    escapes = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "b": "\b", "Z": "\x1a"}
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            out.append(escapes.get(body[i + 1], body[i + 1]))
            i += 2
        elif ch == quote and body[i + 1:i + 2] == quote:
            out.append(quote)
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_object(stmt, group):
    """{type, name, schema or None, ...} as MySQL reads the name."""
    text = lex(stmt).uncommented
    if group == "source":
        m = _SOURCE_HEAD.match(text)
        if not m:
            return None
        schema, name = _qualified(m)
        out = {"type": m.group("kind").upper(), "name": name, "schema": schema,
               "verb": m.group("verb").lower(), "replace": bool(m.group("replace")),
               "definer": m.group("definer"), "span": (m.start("name"), m.end("name"))}
        if out["type"] == "TRIGGER":
            t = _TRIGGER_ON.match(text, m.end())
            if t:
                out["table"] = _qualified(t, "tschema", "table")[1]
        return out
    if group == "comments":
        m = _COMMENT_HEAD.match(text)
        if not m:
            return None
        schema, name = _qualified(m)
        return {"type": "COMMENT", "name": name, "schema": schema, "table": name,
                "value": _string_value(m.group("value"))}
    return None


def destructive_reason(stmt, group):
    """Why no journal brings this statement's work back, or None."""
    code = _code(stmt)
    if group == "structural":
        if code.startswith("drop "):
            return "DROP removes the object and everything in it"
        if code.startswith("truncate "):
            return "TRUNCATE empties the table — no journal brings the rows back"
        if code.startswith("rename "):
            return "RENAME breaks every view and routine that still uses the old name"
        if re.match(r"alter table\b.*\bdrop\b", code):
            return ("ALTER TABLE ... DROP removes a column, key or constraint, and a "
                    "column's data")
        if re.match(r"alter table\b.*\b(modify|change)\b", code):
            return "redefining a column rewrites it, and can lose data"
        if re.match(r"alter table\b.*\brename\b", code):
            return "a rename breaks every view and routine that still uses the old name"
    if group == "data_dml":
        if code.startswith("replace "):
            return ("REPLACE deletes a row whose key it meets before inserting: the "
                    "deleted row's other columns are gone")
        if re.match(r"(update|delete)\b", code):
            if not re.search(r"\bwhere\b", code):
                return "no WHERE clause — it touches every row in the table"
            if re.search(r"\bwhere\s*\(?\s*(1\s*=\s*1|0\s*=\s*0|true|1)\s*\)?\s*$", code):
                return "a WHERE clause that is always true touches every row"
    if group == "grants":
        if code.startswith("revoke "):
            return "REVOKE takes a privilege away from whoever relied on it"
        if re.search(r"\bwith grant option\b", code):
            return "WITH GRANT OPTION lets the grantee pass the privilege on"
    return None


# --- the rows a data change touches ----------------------------------------------------

_DML_TARGET = (
    re.compile(r"\s*(?:insert|replace)\s+(?:(?:low_priority|delayed|high_priority|ignore)\s+)*"
               r"(?:into\s+)?" + _NAME, re.I),
    re.compile(r"\s*update\s+(?:low_priority\s+)?(?:ignore\s+)?" + _NAME, re.I),
    re.compile(r"\s*delete\s+(?:low_priority\s+)?(?:quick\s+)?(?:ignore\s+)?from\s+"
               + _NAME, re.I),
)


def dml_target(stmt):
    """(schema or None, table) a data change writes to, or None."""
    text = lex(stmt).uncommented
    for pattern in _DML_TARGET:
        m = pattern.match(text)
        if m:
            return _qualified(m)
    return None


def _refuse_probe(why):
    sys.exit(f"Refused: {why} The rows an UPDATE or DELETE touches are shown and "
             "revalidated before it is approved, so a statement whose rows cannot "
             "be read beforehand is refused.")


def dml_probe(stmt):
    """(target, predicate or None) of an UPDATE or DELETE; None for INSERT and
    REPLACE. Read with the comments blanked, so a trailing comment never
    swallows what the probe appends."""
    code = _code(stmt)
    text = " ".join(lex(stmt).uncommented.split()).rstrip(";").rstrip()
    if not re.match(r"(update|delete)\b", code):
        return None
    if re.match(r"(update|delete)( low_priority)?( quick)? ignore\b", code):
        _refuse_probe("IGNORE turns errors into warnings and skips those rows: the rows "
                      "it writes are not the rows the preview showed.")
    if code.startswith("update "):
        m = re.match(r"update\s+(?:low_priority\s+)?" + _NAME + r"\s+set\b", text, re.I)
    else:
        m = re.match(r"delete\s+(?:low_priority\s+)?(?:quick\s+)?from\s+" + _NAME
                     + r"(?=\s+where\b|$)", text, re.I)
    if not m:
        _refuse_probe("the target table could not be read: several tables, an alias, "
                      "a JOIN or USING bring in rows the statement's own WHERE does "
                      "not show.")
    rest = _code(text[m.end():])
    if re.search(r"\b(order by|limit)\b", rest):
        _refuse_probe("ORDER BY ... LIMIT: which rows is decided as it runs.")
    if re.search(r"\bpartition\b", rest):
        _refuse_probe("a PARTITION clause narrows the rows outside the WHERE.")
    depth = 0
    for ch in rest:
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth < 0:
            break
    if depth:
        _refuse_probe("the WHERE clause's parentheses do not balance.")
    if re.search(r"\(\s*select\b", rest):
        _refuse_probe("a subquery in WHERE reads other tables as it runs.")
    if re.search(r"\b(from|join)\b", rest):
        _refuse_probe("FROM or a JOIN brings in another table; the rows it touches "
                      "cannot be read from its own WHERE.")
    target = text[m.start("schema") if m.group("schema") else m.start("name"):
                  m.end("name")].strip()
    w = re.search(r"\bwhere\b", text[m.end():], re.I)
    pred = text[m.end():][w.end():].strip() if w else None
    return target, pred or None


def _run_text(conn, sql):
    """Statement text, run exactly as written: no binds, so PyMySQL formats
    nothing in it (a % stays a %)."""
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall() if cur.description else []
        return cols, rows, cur.rowcount


def _schema_name(target, schema):
    m = re.match(_NAME + r"\s*$", target.strip())
    if not m:
        return schema, target
    s, n = _qualified(m)
    return s or schema, n


def measure_row_set(conn, target, pred):
    """How many rows the predicate selects, a fingerprint that moves when any
    of them changes, and the first few."""
    s, n = _schema_name(target, None)
    s = s or _current(conn)
    names = [r[1] for r in q(conn, "columns.sql", s=s, n=n)[1]]
    if not names:
        sys.exit(f"Refused: no table {target} that this account can read — the rows "
                 "an UPDATE or DELETE touches must be measured before it is approved.")
    row = "json_array(" + ", ".join(ident(c) for c in names) + ")"

    def fill(name):
        return (sql_of(name).replace("/*TARGET*/", target).replace("/*ROW*/", row)
                .replace("/*WHERE*/", f"({pred})" if pred else "1 = 1"))
    try:
        _, agg, _ = _run_text(conn, fill("row-set-count.sql"))
        cols, rows, _ = _run_text(conn, fill("row-set-sample.sql"))
    except Exception as e:                  # noqa: BLE001 — refused, not guessed
        sys.exit("Refused: pythia-mysql could not measure the rows this statement "
                 f"would touch.\n  {target} — {error_text(e)[1]}\nRevalidation is "
                 "mandatory for UPDATE and DELETE, so a set that cannot be measured "
                 "cannot be approved.")
    count, fingerprint = agg[0]
    return {"target": target, "predicate": pred or "", "count": int(count or 0),
            "hash": str(fingerprint), "columns": [str(c).upper() for c in cols],
            "sample": [[cell(v) for v in r] for r in rows[:SAMPLE_ROWS]],
            "truncated": len(rows) > SAMPLE_ROWS}


def _current(conn):
    rows = q(conn, "current-schema.sql")[1]
    return rows[0][0] if rows else None


# --- snapshot and restore -------------------------------------------------------------------

def _definition(conn, schema, ident_):
    """The CREATE statement that rebuilds an object as it stands, None when
    there is none; refused when MySQL will not show this account its body."""
    for otype, _obj, head, body, _notes in statements(conn, schema, ident_["name"]):
        if otype != ident_["type"]:
            continue
        if body is None:
            why = (HIDDEN["routine"] if otype in ("PROCEDURE", "FUNCTION") else
                   f"SHOW VIEW, TRIGGER or EVENT is needed to read a {otype.lower()}")
            sys.exit(f"Refused: {ident_['name']} exists but this account cannot read "
                     f"its definition ({why}), so there is nothing to snapshot and no "
                     "way back.")
        if otype == "VIEW":
            head = re.sub(r"^CREATE ", "CREATE OR REPLACE ", head)
        return f"{head}\n{body}"
    return None


def snapshot(conn, schema, group, ident_):
    """What the statement could replace, as it stands: a view's, routine's,
    trigger's or event's definition, or a table's comment."""
    target_schema = ident_.get("schema") or schema
    if group == "source":
        text = _definition(conn, target_schema, ident_)
        return {ident_["name"]: text} if text is not None else {}
    if group == "comments":
        rows = q(conn, "table-comment.sql", s=target_schema, n=ident_["table"])[1]
        return {ident_["name"]: rows[0][0] or ""} if rows else {}
    return {}


def restore_statement(group, ident_, before, outcome):
    """The statement that puts back what this one replaced."""
    schema = ident_.get("schema") or outcome.get("schema")
    if group == "comments":
        return (f"ALTER TABLE {ident(schema)}.{ident(ident_['table'])} COMMENT = "
                f"{literal(before or '')}")
    if before:
        return before
    return f"DROP {ident_['type']} {ident(schema)}.{ident(ident_['name'])}"


# --- rehearsing data ---------------------------------------------------------------------

def _settings(conn):
    q(conn, "rehearsal-settings.sql")


def rehearse(conn, schema, group, stmt, ident_, snap, errors=Exception):
    """Data runs in the open transaction (core rolls a preview back and
    commits an approved write); everything else is predicted."""
    _settings(conn)
    if group == "session":
        try:
            _run_text(conn, stmt)
        except errors as e:
            return {"error": _said(e)}
        return {"error": None}
    if group == "data_dml":
        return _rehearse_data(conn, schema, stmt, errors)
    try:
        out = _predict(conn, schema, group, stmt, ident_, snap, errors)
    except errors as e:
        out = {"error": f"the prediction could not finish: {_said(e)}"}
    out["predicted"] = True
    return out


def _said(e):
    number, message = error_text(e)
    return f"{number}: {message}" if number else message


def _rehearse_data(conn, schema, stmt, errors):
    target = dml_target(stmt)
    if target is None:
        return {"error": "the table this statement writes could not be read from it"}
    s, n = target[0] or schema, target[1]
    rows = q(conn, "table-engine.sql", s=s, n=n)[1]
    if rows and rows[0][1] != "YES":
        return {"error": (f"{n} is a {rows[0][0]} table: MySQL cannot roll a write to it "
                          "back, so pythia-mysql cannot rehearse it — and writes nothing "
                          "it has not rehearsed. Convert it to InnoDB, or a DBA writes "
                          "it by hand.")}
    q(conn, "savepoint.sql")
    try:
        _run_text(conn, stmt)
    except errors as e:
        q(conn, "rollback-to-savepoint.sql")
        return {"error": _said(e)}
    q(conn, "rollback-to-savepoint.sql")
    if any(int(w[1]) == NOT_ROLLED_BACK for w in q(conn, "warnings.sql")[1]):
        return {"schema": schema, "error": f"{NOT_ROLLED_BACK}: some changed tables "
                "could not be rolled back",
                "escape_head": "MySQL could not roll the rehearsal back",
                "escaped": ("a trigger or function wrote to a table MySQL cannot roll "
                            "back (MyISAM, MEMORY): those rows are written, though the "
                            "statement itself was rolled back")}
    try:
        _, _, count = _run_text(conn, stmt)
    except errors as e:
        return {"error": _said(e)}
    return {"error": None, "object": None, "type": None, "after": stmt, "rows": count,
            "broken": [], "own_errors": [], "verified": True, "blind": None,
            "notes": ["a rehearsal fires the statement's triggers and draws "
                      "AUTO_INCREMENT values: rolling back undoes the rows, not "
                      "those; it runs twice, the first time in a savepoint, to find "
                      "a write MySQL cannot roll back"]}


# --- predicting DDL ----------------------------------------------------------------------------

def _qname(schema, name, home):
    return name if schema == home else f"{schema}.{name}"


def invalid_views(conn):
    """{qualified name: MySQL's message} for every view it marks invalid now,
    in every schema but its own."""
    return {(s, n): m for s, n, m in q(conn, "invalid-views.sql")[1]}


def _closure(conn, seeds):
    """The views on top of seeds, transitively: MySQL marks each of them
    invalid when one below it is."""
    found, todo = {}, list(seeds)
    while todo:
        s, n, why = todo.pop()
        for vs, vn in q(conn, "views-reading.sql", s=s, n=n)[1]:
            if (vs, vn) not in found:
                found[(vs, vn)] = f"it reads {s}.{n}, which {why}"
                todo.append((vs, vn, "would be invalid"))
    return found


def _views_using_column(conn, s, t, column):
    pattern = like_contains(f"{ident(s)}.{ident(t)}.{ident(column)}")
    return [(vs, vn) for vs, vn in q(conn, "views-using.sql", p=pattern)[1]]


def _base(name, otype, after, schema, **more):
    return {"error": None, "object": name, "type": otype, "after": after, "rows": None,
            "broken": [], "own_errors": [], "verified": True, "blind": None,
            "notes": [], "schema": schema, **more}


def _broken(found, home):
    return sorted((_qname(s, n, home), "VIEW", f"would be marked invalid: {why}")
                  for (s, n), why in found.items())


def _leads(conn, s, n):
    """Routines, triggers and events that name s.n in their body: MySQL
    records none of them, and checks them only when they run."""
    return sorted(f"{rs}.{rn}" if rs != s else rn
                  for rs, rn, _t, body in q(conn, "dependents-text.sql",
                                            p=like_contains(n))[1]
                  if refers_to(body, n, rs, s))


def _predict(conn, schema, group, stmt, ident_, snap, errors):
    before = {f"{s}.{n}": m for (s, n), m in invalid_views(conn).items()}
    if group == "source":
        out = _predict_source(conn, schema, stmt, ident_, snap, errors)
    elif group == "comments":
        out = _base(ident_["name"], "COMMENT", ident_["value"], schema)
        if not q(conn, "table-comment.sql", s=ident_.get("schema") or schema,
                 n=ident_["table"])[1]:
            out = {"error": f"no table {ident_['table']} in {schema}"}
    elif group == "grants":
        out = _base(None, None, stmt, schema, verified=False,
                    blind="who can do what after a GRANT or REVOKE is not something "
                          "a prediction can check")
    else:
        out = _predict_structural(conn, schema, stmt)
    if not out.get("error"):
        out["prediction"] = {"invalid_before": before,
                             "broken": sorted(b[0] for b in out["broken"])}
        out["notes"].append("MySQL commits DDL as it runs it, so nothing ran: after "
                            "the approval it runs once and the views MySQL marks "
                            "invalid are read back")
    return out


_AS = re.compile(r"\s+as\s+", re.I)


def view_select(stmt, ident_):
    """The SELECT of a CREATE or ALTER VIEW, its CHECK OPTION cut off."""
    lexed = lex(stmt)
    masked = lexed.masked
    i = ident_["span"][1]
    m = re.match(r"\s*\(", masked[i:])
    if m:                                       # a column list
        depth, j = 0, i + m.end() - 1
        while j < len(masked):
            depth += {"(": 1, ")": -1}.get(masked[j], 0)
            j += 1
            if depth == 0:
                break
        i = j
    m = _AS.match(masked, i)
    if not m:
        return None
    tail = re.search(r"\s+with\s+(?:cascaded\s+|local\s+)?check\s+option\s*;?\s*$",
                     masked[m.end():], re.I)
    end = m.end() + tail.start() if tail else len(stmt.rstrip().rstrip(";"))
    return stmt[m.end():end].strip()


def _predict_source(conn, schema, stmt, ident_, snap, errors):
    s, name, otype = ident_.get("schema") or schema, ident_["name"], ident_["type"]
    exists = name in snap
    after = stmt
    if otype == "VIEW":
        if exists and ident_["verb"] == "create" and not ident_["replace"]:
            return {"error": f"{name} exists: CREATE OR REPLACE VIEW, or ALTER VIEW, "
                             "replaces it"}
        if not exists and ident_["verb"] == "alter":
            return {"error": f"no view {name} to alter"}
        select = view_select(stmt, ident_)
        if select is None:
            return {"error": "the view's SELECT could not be read from the statement"}
        try:
            cols, _, _ = _run_text(conn, f"select * from ({select}) as pythia_view_probe "
                                         "limit 0")
        except errors as e:
            return {"error": _said(e)}
        out = _base(name, otype, after, schema)
        new = {str(c).lower() for c in cols}
        old = [r[1] for r in q(conn, "columns.sql", s=s, n=name)[1]] if exists else []
        gone = [c for c in old if c.lower() not in new]
        seeds = {}
        for c in gone:
            for vs, vn in _views_using_column(conn, s, name, c):
                seeds[(vs, vn)] = f"it reads {s}.{name}.{c}, which this drops"
        found = dict(seeds)
        found.update(_closure(conn, [(vs, vn, "would be invalid") for vs, vn in seeds]))
        out["broken"] = _broken(found, schema)
        out["notes"].append("the view's SELECT ran with LIMIT 0: its names resolve")
        if exists:
            out["notes"].extend(_definer_notes(conn, otype, ident_, snap[name]))
        return out
    out = _base(name, otype, after, schema, verified=False,
                blind=(f"MySQL checks a {otype.lower()}'s syntax when it is created, and "
                       "the names inside it only when it runs: nothing in it was "
                       "checked before the write"))
    if otype == "TRIGGER" and ident_.get("table") and not \
            q(conn, "table-engine.sql", s=s, n=ident_["table"])[1]:
        return {"error": f"no table {ident_['table']} for the trigger to be on"}
    if exists:
        how = ("checks the new one under a scratch name, drops the old one, creates "
               "the new one" if otype in ("PROCEDURE", "FUNCTION") else
               "drops the old one and creates the new one")
        out["notes"].append(f"MySQL has no CREATE OR REPLACE {otype}: pythia-mysql {how}, "
                            "and puts the old one back if MySQL refuses the new one")
        if otype == "TRIGGER":
            out["notes"].append("rows written between the DROP and the CREATE fire "
                                "neither trigger")
        out["notes"].extend(_definer_notes(conn, otype, ident_, snap[name]))
    if otype == "FUNCTION":
        users = [f"{vs}.{vn}" if vs != s else vn
                 for vs, vn in q(conn, "views-using-function.sql", s=s, n=name)[1]]
        if users:
            out["notes"].append(f"{', '.join(users)} call {name}: MySQL checks them again "
                                "after the write, and they are read back")
    return out


def _definer_notes(conn, otype, ident_, before):
    """What a replacement does to the definer, and whether this account could
    put the old definer back."""
    old = re.search(r"DEFINER=(\S+)", before or "")
    me = q(conn, "current-user.sql")[1][0][0]
    if not old or _who(old.group(1)) == me:
        return []
    notes, was = [], _who(old.group(1))
    if not ident_.get("definer"):
        notes.append(f"the definer changes from {was} to {me}: a SQL SECURITY DEFINER "
                     f"{otype.lower()} then runs with {me}'s privileges")
    if not _may_set_definer(conn):
        when = ("if MySQL refuses the new one, or later, " if otype != "VIEW" else "later ")
        notes.append(f"the old one's definer is {was}: {when}this account cannot put the "
                     "old one back (that needs SET_ANY_DEFINER, and SYSTEM_USER when the "
                     "definer is a system account); the journal keeps it for a DBA")
    return notes


def _may_set_definer(conn):
    """Whether this account may create objects for another definer."""
    for row in q(conn, "grants.sql")[1]:
        m = re.match(r"GRANT\s+(.*?)\s+ON\s+\*\.\*\s+TO\s", str(row[0]), re.I | re.S)
        held = {" ".join(p.split()).upper() for p in m.group(1).split(",")} if m else set()
        if held & {"ALL", "ALL PRIVILEGES", "SUPER", "SET_USER_ID", "SET_ANY_DEFINER"}:
            return True
    return False


def _who(definer):
    """`user`@`host` as CURRENT_USER() spells it: user@host."""
    return re.sub(r"[`'\"]", "", definer)


_DROP = re.compile(r"\s*drop\s+(?P<kind>table|view|procedure|function|trigger|event|index)"
                   r"\s+(?:if\s+exists\s+)?(?P<names>.*)", re.I | re.S)
_ALTER_TABLE = re.compile(r"\s*alter\s+table\s+" + _NAME + r"\s+(?P<rest>.*)", re.I | re.S)
_RENAME_TABLE = re.compile(r"\s*rename\s+tables?\s+(?P<pairs>.*)", re.I | re.S)


def _names(text):
    return [_qualified(m) for m in re.finditer(_NAME, text)]


def _top_level(text):
    """text split at its top-level commas."""
    out, depth, start = [], 0, 0
    masked = lex(text).masked
    for i, ch in enumerate(masked):
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if ch == "," and depth == 0:
            out.append(text[start:i])
            start = i + 1
    out.append(text[start:])
    return [p.strip() for p in out if p.strip()]


_COLUMN_GONE = (
    re.compile(r"drop\s+(?:column\s+)?(?!(?:index|key|primary|foreign|check|constraint|"
               r"partition|default)\b)(?P<col>" + _ID + r")\s*$", re.I),
    re.compile(r"rename\s+column\s+(?P<col>" + _ID + r")\s+to\s+(?P<new>" + _ID + r")", re.I),
    re.compile(r"change\s+(?:column\s+)?(?P<col>" + _ID + r")\s+(?P<new>" + _ID + r")\s", re.I),
)


def _predict_structural(conn, schema, stmt):
    text = " ".join(lex(stmt).uncommented.split()).rstrip(";").strip()
    seeds, gone = {}, []                 # views marked invalid directly; objects that go
    m = _DROP.match(text)
    if m and m.group("kind").lower() != "index":
        kind = m.group("kind").lower()
        names = re.sub(r"\s+(?:restrict|cascade)\s*$", "", m.group("names"), flags=re.I)
        for s, n in _names(names):
            s = s or schema
            gone.append((s, n))
            if kind in ("table", "view"):
                for vs, vn in q(conn, "views-reading.sql", s=s, n=n)[1]:
                    seeds[(vs, vn)] = f"it reads {s}.{n}, which this drops"
            elif kind == "function":
                for vs, vn in q(conn, "views-using-function.sql", s=s, n=n)[1]:
                    seeds[(vs, vn)] = f"it calls {s}.{n}, which this drops"
    m = _RENAME_TABLE.match(text)
    if m:
        for pair in _top_level(m.group("pairs")):
            old = re.match(_NAME, pair)
            if old:
                s, n = _qualified(old)
                s = s or schema
                gone.append((s, n))
                for vs, vn in q(conn, "views-reading.sql", s=s, n=n)[1]:
                    seeds[(vs, vn)] = f"it reads {s}.{n}, which this renames"
    m = _ALTER_TABLE.match(text)
    if m:
        s, t = _qualified(m)
        s = s or schema
        for clause in _top_level(m.group("rest")):
            if re.match(r"rename\s+(?:to\s+|as\s+)?(?!column\b|index\b|key\b)", clause, re.I):
                gone.append((s, t))
                for vs, vn in q(conn, "views-reading.sql", s=s, n=t)[1]:
                    seeds[(vs, vn)] = f"it reads {s}.{t}, which this renames"
                continue
            for pattern in _COLUMN_GONE:
                c = pattern.match(clause)
                if c and not ("new" in c.groupdict() and
                              fold(c.group("new")).lower() == fold(c.group("col")).lower()):
                    col = fold(c.group("col"))
                    for vs, vn in _views_using_column(conn, s, t, col):
                        seeds[(vs, vn)] = f"it reads {s}.{t}.{col}, which this drops"
                    break
    found = dict(seeds)
    found.update(_closure(conn, [(vs, vn, "would be invalid") for vs, vn in seeds]))
    out = _base(None, None, stmt, schema)
    out["broken"] = _broken(found, schema)
    leads = sorted({lead for s, n in gone for lead in _leads(conn, s, n)})
    if leads:
        out.update(verified=False, blind=(
            f"{', '.join(leads)} name what this drops or renames in their body: MySQL "
            "checks those names only when they run, so whether they break was not "
            "checked ([text] leads)"))
    return out


# --- after the approval: the write, and what it left ---------------------------------------

def _run_or_none(conn, sql, errors):
    try:
        _run_text(conn, sql)
        return None
    except errors as e:
        return e


def _lost(e):
    number, _ = error_text(e)
    return number in LOST or isinstance(e, OSError)


def _scratch(stmt, ident_):
    """The statement with its routine renamed to a scratch name."""
    a, b = ident_["span"]
    name = (ident_["name"][:64 - len(SCRATCH)] + SCRATCH)
    return stmt[:a] + ident(name) + stmt[b:], name


def execute(conn, schema, group, stmt, ident_, errors=Exception):
    """Run a predicted statement once. MySQL's DDL is atomic: a statement it
    refuses wrote nothing. A lost connection leaves it unknown."""
    _settings(conn)
    if group == "source" and ident_ and ident_["type"] != "VIEW" and ident_["verb"] == "create":
        old = snapshot(conn, schema, group, ident_).get(ident_["name"])
        if old is not None:
            return _replace(conn, schema, stmt, ident_, old, errors)
    failed = _run_or_none(conn, stmt, errors)
    if failed is None:
        return {}
    if _lost(failed):
        return {"escaped": "the statement was sent, and no answer says whether it "
                           "landed", "error": _said(failed)}
    return {"error": _said(failed)}


def _replace(conn, schema, stmt, ident_, old, errors):
    s = ident_.get("schema") or schema
    kind, name = ident_["type"], ident_["name"]
    target = f"{ident(s)}.{ident(name)}"
    if kind in ("PROCEDURE", "FUNCTION"):
        trial, scratch = _scratch(stmt, ident_)
        failed = _run_or_none(conn, trial, errors)
        if failed is not None:
            if _lost(failed):
                return {"escaped": f"a scratch {kind.lower()} {scratch} was sent, and no "
                                   "answer says whether it landed", "error": _said(failed)}
            return {"error": f"{_said(failed)} — checked under a scratch name; "
                             f"{name} was not touched"}
        left = _run_or_none(conn, f"DROP {kind} IF EXISTS {ident(s)}.{ident(scratch)}",
                            errors)
        if left is not None:
            return {"escaped": (f"the scratch {kind.lower()} {scratch}, created to check "
                                f"the new {name}, could not be dropped: it is still there "
                                f"({_said(left)}); {name} was not touched"),
                    "error": _said(left)}
    failed = _run_or_none(conn, f"DROP {kind} {target}", errors)
    if failed is not None:
        if _lost(failed):
            return {"escaped": f"DROP {kind} {name} was sent, and no answer says whether "
                               "it landed", "error": _said(failed)}
        return {"error": _said(failed)}
    failed = _run_or_none(conn, stmt, errors)
    if failed is None:
        return {}
    back = _run_or_none(conn, old, errors)
    if back is None:
        return {"error": f"{_said(failed)} — the old {kind.lower()} was put back"}
    return {"escaped": (f"the old {kind.lower()} {name} was dropped, MySQL refused the "
                        f"new one ({_said(failed)}), and putting the old one back "
                        f"failed too ({_said(back)}): {name} does not exist now"),
            "error": _said(failed)}


def verify_written(conn, schema, group, stmt, ident_, outcome, errors=Exception):
    """What the write left: views MySQL marked invalid that were not before,
    and every way that differs from the prediction."""
    prediction = outcome.get("prediction") or {}
    before = set(prediction.get("invalid_before") or {})
    now = invalid_views(conn)
    own, broken, differs = [], [], []
    for (s, n), message in sorted(now.items()):
        if f"{s}.{n}" in before:
            continue
        row = (_qname(s, n, schema), "VIEW", message)
        if group == "source" and ident_ and ident_["type"] == "VIEW" and \
                n == ident_["name"] and s == (ident_.get("schema") or schema):
            own.append(row)
        else:
            broken.append(row)
    said = set(prediction.get("broken") or [])
    seen = {b[0] for b in broken}
    differs += [f"{v} is marked invalid now; the prediction did not say so"
                for v in sorted(seen - said)]
    differs += [f"{v} was predicted invalid, and MySQL did not mark it"
                for v in sorted(said - seen)]
    if group == "source" and ident_:
        differs += _read_back_source(conn, schema, stmt, ident_)
    elif group == "comments" and ident_:
        rows = q(conn, "table-comment.sql", s=ident_.get("schema") or schema,
                 n=ident_["table"])[1]
        got = rows[0][0] if rows else None
        if got != ident_["value"]:
            differs.append(f"{ident_['table']}'s comment reads back as {got!r}, not "
                           "what was written")
    return {"broken": sorted(broken), "own_errors": own, "differs": differs}


def _squash(text):
    return " ".join(str(text or "").split())


def _read_back_source(conn, schema, stmt, ident_):
    s, name, kind = ident_.get("schema") or schema, ident_["name"], ident_["type"]
    found = [u for u in statements(conn, s, name) if u[0] == kind]
    if not found:
        return [f"no {kind.lower()} named {name} after the write"]
    body = found[0][3]
    if kind != "VIEW" and ident_["verb"] == "create" and body is not None and \
            _squash(body) not in _squash(stmt):
        return [f"{name} reads back with a body that is not the one written"]
    return []


def privilege_warning(conn, schema):
    """One line when the account can do far more than a change needs."""
    held = set()
    for row in q(conn, "grants.sql")[1]:
        m = re.match(r"GRANT\s+(.*?)\s+ON\s+\*\.\*\s+TO\s", str(row[0]), re.I | re.S)
        if m:
            held |= {" ".join(p.split()).upper() for p in m.group(1).split(",")}
    who = q(conn, "current-user.sql")[1][0][0]
    if held & {"ALL", "ALL PRIVILEGES", "SUPER"}:
        return (f"! {who} holds every privilege on the whole server: it can do far "
                "more than this change needs. An account with only the rights the "
                "change needs is safer.")
    if held & {"SYSTEM_USER", "SET_USER_ID", "SET_ANY_DEFINER"}:
        return (f"! {who} may act as any account (SYSTEM_USER, SET_USER_ID): far more "
                "than this change needs.")
    return None
