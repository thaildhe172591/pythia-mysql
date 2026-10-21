"""The read tier for MySQL: pythia's Learn movement, asked of the live
catalog.

MySQL records less than the other engines. information_schema keeps which
tables, views and functions a view reads (VIEW_TABLE_USAGE and
VIEW_ROUTINE_USAGE), the triggers on a table and the foreign keys between
tables — and nothing at all about what a procedure, function, trigger or
event body uses. The walks therefore ask the catalog, then search bodies by
name, and mark what only the search vouches for (how = "text"), naming that
blind spot every time.

MySQL also hides from an account what it holds no privilege to see: a
routine without SHOW_ROUTINE (or a global SELECT, or being its definer), a
trigger without TRIGGER, an event without EVENT. SHOW GRANTS, with the
active roles' privileges merged in, says which; every answer that could be
short because of it says so.

MySQL keeps no line numbers, and information_schema no CREATE statement:
`src` and `ddl` rebuild the statement — its header on line 1, then the body
as it was written. A view's SELECT is kept only as MySQL rewrote it.

`errors` reads the views MySQL has marked invalid: dropping or altering
what a view reads marks it, and information_schema then shows the error the
view would raise. Nothing checks a routine, trigger or event before it
runs, so `errors` names those as unchecked.

MariaDB records no dependencies at all and marks no view invalid. It does
store each view's SELECT with every name written `schema`.`name`, so a
view's dependencies are read there (how = "definition"), and `errors` asks
CHECK TABLE of every view, which opens it and names what it cannot find.
It hides routines behind its own privileges (SHOW CREATE ROUTINE from 11.3,
SELECT on mysql.proc before), and keeps sequences and, in sql_mode=ORACLE,
packages, which are read too.
"""
import datetime
import re

from pythia_core.output import TEXT_HOW

from .catalog import MARIADB, MYSQL, fold, ident, like_contains, literal, q, run_template, server

CATALOG_HOW = "catalog"
# MariaDB's stored view definition names it `schema`.`name`: not a record of
# the dependency, but not a guess from a body either
DEFINITION_HOW = "definition"
ROUTINE_TYPES = ("PROCEDURE", "FUNCTION", "PACKAGE", "PACKAGE BODY")
CODE_TYPES = ROUTINE_TYPES + ("TRIGGER", "EVENT")

DDL_NOTE = ("-- rebuilt from information_schema by pythia-mysql; MySQL's own "
            "SHOW CREATE is the reference")

BLIND_TEXT_IN = {
    MYSQL: ("MySQL records no dependencies for procedures, functions, triggers "
            "or events, so their bodies are matched by name ([text]): a "
            "variable, column or comment with the same name gives a false match, "
            "and a name built at run time (PREPARE of a string) is not seen at all"),
    MARIADB: ("MariaDB records no dependencies at all: views are read in their "
              "stored definitions, where every name is written `schema`.`name` "
              "(definition), and procedure, function, trigger, event and package "
              "bodies are matched by name ([text]): a variable, column or comment "
              "with the same name gives a false match, and a name built at run "
              "time (PREPARE of a string) is not seen at all"),
}
BLIND_TEXT_OUT = {
    MYSQL: ("a procedure, function, trigger or event body is read against the "
            "names of existing tables, views and routines ([text]): MySQL "
            "records none of it, and a name built at run time is not seen"),
    MARIADB: ("a view is read in its stored definition (definition), and a "
              "procedure, function, trigger, event or package body against the "
              "names of existing tables, views and routines ([text]): MariaDB "
              "records none of it, and a name built at run time is not seen"),
}
BLIND_ELSEWHERE = (
    "other schemas are seen only as far as this account's privileges reach "
    "there")
HIDDEN = {
    MYSQL: {
        "routine": ("this account holds neither SHOW_ROUTINE nor a global SELECT: "
                    "MySQL hides the procedures and functions it did not define, or "
                    "shows them without a body (GRANT SHOW_ROUTINE ON *.* lets it "
                    "read them)"),
        "trigger": ("this account holds no TRIGGER privilege on {schema}: MySQL "
                    "hides that schema's triggers from it"),
        "event": ("this account holds no EVENT privilege on {schema}: MySQL hides "
                  "that schema's events from it"),
    },
    MARIADB: {
        "routine": ("this account holds neither SHOW CREATE ROUTINE (MariaDB 11.3 and "
                    "later) nor SELECT on mysql.proc or on every database: MariaDB "
                    "hides the procedures, functions and packages it did not define "
                    "(GRANT SHOW CREATE ROUTINE ON *.* lets it read them; on 10.11, "
                    "GRANT SELECT ON mysql.proc)"),
        "trigger": ("this account holds no TRIGGER privilege on {schema}: MariaDB "
                    "hides that schema's triggers from it"),
        "event": ("this account holds no EVENT privilege on {schema}: MariaDB hides "
                  "that schema's events from it"),
    },
}


def resolve(conn, schema, name):
    """[(schema, name, type)] of every object holding a name: tables and
    views share a namespace, routines, triggers and events have their own."""
    return [tuple(r) for r in q(conn, "resolve.sql", s=schema, n=name)[1]]


def object_names(conn, schema, pattern, fetch):
    return q(conn, "object-names.sql", s=schema, p=pattern, n=int(fetch))


def split_body(text):
    return str(text).replace("\r\n", "\n").rstrip("\n").split("\n")


# --- what this account may see -------------------------------------------------------

GRANT_RE = re.compile(r"^GRANT\s+(.*?)\s+ON\s+(?:(?:TABLE|FUNCTION|PROCEDURE)\s+)?"
                      r"(\S+)\s+TO\s", re.I | re.S)
SCOPE_RE = re.compile(r"^(\*|`(?:[^`]|``)*`|[^.`]+)\.(\*|`(?:[^`]|``)*`|\S+)$")


def privileges(text):
    """The privilege names of a GRANT's list, column lists dropped."""
    depth, word, out = 0, "", []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(word)
            word = ""
        elif depth == 0:
            word += ch
    out.append(word)
    return {" ".join(w.split()).upper() for w in out if w.strip()}


def db_matches(pattern, schema):
    """A database-level grant's name as MySQL matches it: % and _ are
    wildcards unless a backslash escapes them."""
    if pattern == "*":
        return True
    rx, i = "", 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            rx += re.escape(pattern[i + 1])
            i += 2
            continue
        rx += ".*" if ch == "%" else "." if ch == "_" else re.escape(ch)
        i += 1
    return re.fullmatch(rx, schema, re.S) is not None


def hidden_kinds(conn, schema):
    """{kind: why} for what the server hides from this account in a schema —
    'routine', 'trigger', 'event' — read from SHOW GRANTS; {} when it sees
    them all. A grant on one table is not a grant on the schema. Only the
    privilege list and the scope of each line are read: MariaDB's lines also
    carry the password hash, which goes nowhere."""
    name = server(conn)
    held = {"routine": False, "trigger": False, "event": False}
    for row in q(conn, "grants.sql")[1]:
        m = GRANT_RE.match(str(row[0]).strip())
        if not m:
            continue        # a role granted: once active, its privileges are listed
        privs, where = privileges(m.group(1)), SCOPE_RE.match(m.group(2))
        if not where:
            continue
        db = where.group(1) if where.group(1) == "*" else fold(where.group(1))
        obj = where.group(2) if where.group(2) == "*" else fold(where.group(2))
        everything = bool(privs & {"ALL", "ALL PRIVILEGES"})
        reads = everything or "SELECT" in privs
        if name == MARIADB:
            # another definer's routine: SHOW CREATE ROUTINE (11.3 and later),
            # or whoever may read mysql.proc, where MariaDB keeps routines
            if (db == "*" and (reads or "SHOW CREATE ROUTINE" in privs)) \
                    or (db.lower() == "mysql" and obj in ("*", "proc") and reads) \
                    or (obj == "*" and db_matches(db, schema)
                        and "SHOW CREATE ROUTINE" in privs):
                held["routine"] = True
        elif db == "*" and (everything or privs & {"SHOW_ROUTINE", "SELECT"}):
            held["routine"] = True
        if obj != "*":
            continue
        if db_matches(db, schema):
            held["trigger"] = held["trigger"] or everything or "TRIGGER" in privs
            held["event"] = held["event"] or everything or "EVENT" in privs
    return {kind: HIDDEN[name][kind].format(schema=schema)
            for kind, seen in held.items() if not seen}


# --- the statements MySQL does not keep, rebuilt -----------------------------------------

def definer(text):
    user, _, host = str(text).rpartition("@")
    return f"DEFINER={ident(user)}@{ident(host)}"


def timestamp(value):
    if isinstance(value, datetime.datetime):
        value = value.strftime("%Y-%m-%d %H:%M:%S")
    return literal(value)


def routine_header(schema, row, params):
    (rtype, name, returns, rcharset, determ, access, security, comment, who,
     _mode, language, _body, schema_charset) = row
    if rtype in ("PACKAGE", "PACKAGE BODY"):
        # MariaDB's, in sql_mode=ORACLE: its body is the text from AS on
        head = f"CREATE {definer(who)} {rtype} {ident(schema)}.{ident(name)}"
        if security == "INVOKER":
            head += " SQL SECURITY INVOKER"
        return head + (f" COMMENT {literal(comment)}" if comment else "")
    args = []
    for _rt, _pos, mode, pname, dtype, charset in params:
        arg = f"{ident(pname)} {dtype}"
        if charset and charset != schema_charset:
            arg += f" CHARSET {charset}"
        args.append(arg if rtype == "FUNCTION" else f"{mode} {arg}")
    head = (f"CREATE {definer(who)} {rtype} {ident(schema)}.{ident(name)}"
            f"({', '.join(args)})")
    if rtype == "FUNCTION":
        head += f" RETURNS {returns}"
        if rcharset and rcharset != schema_charset:
            head += f" CHARSET {rcharset}"
    if access and access != "CONTAINS SQL":
        head += f" {access}"
    if determ == "YES":
        head += " DETERMINISTIC"
    if security == "INVOKER":
        head += " SQL SECURITY INVOKER"
    if comment:
        head += f" COMMENT {literal(comment)}"
    if language and str(language).upper() != "SQL":
        head += f" LANGUAGE {language} AS $$"
    return head


def view_statement(schema, row):
    name, definition, check, security, who = row
    head = (f"CREATE {definer(who)}"
            + (" SQL SECURITY INVOKER" if security == "INVOKER" else "")
            + f" VIEW {ident(schema)}.{ident(name)} AS")
    if not definition:
        return head, None                       # SHOW VIEW not held
    if check and check != "NONE":
        definition += f" WITH {check} CHECK OPTION"
    return head, definition


def trigger_header(schema, row, siblings):
    name, timing, event, table, order, _body, who, _mode = row
    head = (f"CREATE {definer(who)} TRIGGER {ident(schema)}.{ident(name)} {timing} "
            f"{event} ON {ident(schema)}.{ident(table)} FOR EACH ROW")
    if order and order > 1:
        before = [s[0] for s in siblings if s[3] == table and s[1] == timing
                  and s[2] == event and s[4] == order - 1]
        if before:
            head += f" FOLLOWS {ident(before[0])}"
    return head


EVENT_STATUS = {"ENABLED": "ENABLE", "DISABLED": "DISABLE",
                "SLAVESIDE_DISABLED": "DISABLE ON REPLICA",
                "REPLICA_SIDE_DISABLED": "DISABLE ON REPLICA"}


def event_header(schema, row):
    (name, etype, at, ivalue, ifield, starts, ends, completion, status, comment,
     who, _body, _mode, _tz) = row
    if etype == "ONE TIME":
        when = f"AT {timestamp(at)}"
    else:
        value = ivalue if re.fullmatch(r"\d+", str(ivalue)) else literal(ivalue)
        when = f"EVERY {value} {ifield}"
        if starts:
            when += f" STARTS {timestamp(starts)}"
        if ends:
            when += f" ENDS {timestamp(ends)}"
    head = (f"CREATE {definer(who)} EVENT {ident(schema)}.{ident(name)} ON SCHEDULE "
            f"{when} ON COMPLETION {completion} {EVENT_STATUS.get(status, 'ENABLE')}")
    if comment:
        head += f" COMMENT {literal(comment)}"
    return head + " DO"


def created_under(sql_mode, time_zone=None):
    """The settings a stored program keeps from its creation, as comments: a
    replay under others behaves differently."""
    notes = [f"created under sql_mode={sql_mode or literal('')}"]
    if time_zone:
        notes.append(f"created under time_zone={time_zone}: AT, STARTS and ENDS "
                     "are times there")
    return notes


def statements(conn, schema, name):
    """[(type, name, header, body or None, notes)] for every object of that
    name that holds code; body None when MySQL will not show it to this
    account, notes what the ddl says above the statement."""
    out, routines = [], None
    for _s, obj, otype in resolve(conn, schema, fold(name)):
        if otype == "VIEW":
            for row in q(conn, "view.sql", s=schema, n=obj)[1]:
                head, body = view_statement(schema, row)
                out.append((otype, obj, head, body, []))
        elif otype in ROUTINE_TYPES:
            if routines is None:
                params = q(conn, "routine-params.sql", s=schema, n=obj)[1]
                routines = [(r, [p for p in params if p[0] == r[0]])
                            for r in q(conn, "routine.sql", s=schema, n=obj)[1]]
            for row, mine in routines:
                if row[0] == otype:
                    body = row[11]
                    if body is not None and row[10] and str(row[10]).upper() != "SQL":
                        body = str(body).rstrip("\n") + "\n$$"
                    out.append((otype, obj, routine_header(schema, row, mine), body,
                                created_under(row[9])))
        elif otype == "TRIGGER":
            for row in q(conn, "triggers.sql", s=schema, n=obj, t=None)[1]:
                siblings = (q(conn, "triggers.sql", s=schema, n=None, t=row[3])[1]
                            if row[4] and row[4] > 1 else [])
                out.append((otype, obj, trigger_header(schema, row, siblings), row[5],
                            created_under(row[7])))
        elif otype == "EVENT":
            for row in q(conn, "event.sql", s=schema, n=obj)[1]:
                out.append((otype, obj, event_header(schema, row), row[11],
                            created_under(row[12], row[13])))
    return out


def source(conn, schema, name):
    units = [u for u in statements(conn, schema, name) if u[3] is not None]
    rows = []
    for otype, obj, head, body, _mode in units:
        unit = obj if len(units) == 1 else f"{obj} ({otype})"
        lines = [head] + split_body(body)
        rows.extend((unit, i, line) for i, line in enumerate(lines, 1))
    return rows


def columns(conn, schema, name):
    cols, rows = q(conn, "columns.sql", s=schema, n=fold(name))
    return (cols, rows) if rows else None


# --- ddl ----------------------------------------------------------------------------------

def unescaped(expr):
    """An expression as SHOW CREATE TABLE prints it: information_schema
    keeps check clauses, generated columns, expression defaults and
    functional index parts with one more level of backslash escaping."""
    return re.sub(r"\\(.)", r"\1", str(expr), flags=re.S)


def default_sql(default, extra, ctype):
    if "DEFAULT_GENERATED" in extra.upper():
        if re.match(r"(current_timestamp|now|localtime|localtimestamp)\b", default, re.I):
            return default
        return f"({unescaped(default)})"        # an expression default
    if ctype.lower().startswith("bit") and default.lower().startswith("b'"):
        return default
    return literal(default)


def column_line(row, table_charset, table_collation, mariadb=False, check=None):
    """A column as SHOW CREATE TABLE prints it. MariaDB keeps the default as
    SQL already and its expressions unescaped; check is a column-level CHECK
    clause, which MariaDB prints on the column."""
    name, ctype, nullable, default, extra, gen, charset, collation, comment, srs = row
    extra = extra or ""
    parts = [ident(name), ctype]
    if charset and charset != table_charset:
        parts.append(f"CHARACTER SET {charset} COLLATE {collation}")
    elif collation and collation != table_collation:
        parts.append(f"COLLATE {collation}")
    if gen:
        kind = "STORED" if "STORED" in extra.upper() else "VIRTUAL"
        parts.append(f"GENERATED ALWAYS AS ({gen if mariadb else unescaped(gen)}) {kind}")
    if nullable == "NO":
        parts.append("NOT NULL")
    if srs is not None:
        parts.append(f"SRID {srs}")
    if not gen:
        if default is not None and not (mariadb and default == "NULL"):
            parts.append("DEFAULT " + (default if mariadb else default_sql(default, extra, ctype)))
        elif nullable == "YES":
            parts.append("DEFAULT NULL")
    if "INVISIBLE" in extra.upper():
        parts.append("INVISIBLE")
    if "auto_increment" in extra.lower():
        parts.append("AUTO_INCREMENT")
    on_update = re.search(r"on update (\S+)", extra, re.I)
    if on_update:
        parts.append(f"ON UPDATE {on_update.group(1)}")
    if comment:
        parts.append(f"COMMENT {literal(comment)}")
    if check:
        parts.append(f"CHECK ({check})")
    return " ".join(parts)


def index_lines(rows, mariadb=False):
    indexes = {}
    for name, non_unique, _seq, col, sub, direction, itype, expr, visible, comment in rows:
        ix = indexes.setdefault(name, {"unique": not non_unique, "type": itype,
                                       "parts": [], "visible": visible,
                                       "comment": comment})
        part = f"({unescaped(expr)})" if expr else ident(col) + (f"({sub})" if sub else "")
        ix["parts"].append(part + (" DESC" if direction == "D" else ""))

    def rank(item):
        name, ix = item
        if name == "PRIMARY":
            return 0, name
        if ix["type"] in ("FULLTEXT", "SPATIAL"):
            return 3, name
        return (1 if ix["unique"] else 2), name

    lines = []
    for name, ix in sorted(indexes.items(), key=rank):
        cols = ",".join(ix["parts"])
        if name == "PRIMARY":
            text = f"PRIMARY KEY ({cols})"
        elif ix["type"] in ("FULLTEXT", "SPATIAL"):
            text = f"{ix['type']} KEY {ident(name)} ({cols})"
        else:
            text = f"{'UNIQUE ' if ix['unique'] else ''}KEY {ident(name)} ({cols})"
        if ix["type"] == "HASH":
            text += " USING HASH"
        if ix["comment"]:
            text += f" COMMENT {literal(ix['comment'])}"
        if ix["visible"] == "NO":
            text += " IGNORED" if mariadb else " INVISIBLE"
        lines.append(text)
    return lines


def foreign_key_lines(rows):
    fks = {}
    for name, col, ref_schema, ref_table, ref_col, on_update, on_delete in rows:
        fk = fks.setdefault(name, {"cols": [], "ref_cols": [], "upd": on_update,
                                   "del": on_delete,
                                   "ref": f"{ident(ref_schema)}.{ident(ref_table)}"})
        fk["cols"].append(ident(col))
        fk["ref_cols"].append(ident(ref_col))
    lines = []
    for name in sorted(fks):
        fk = fks[name]
        text = (f"CONSTRAINT {ident(name)} FOREIGN KEY ({', '.join(fk['cols'])}) "
                f"REFERENCES {fk['ref']} ({', '.join(fk['ref_cols'])})")
        for verb, rule in (("DELETE", fk["del"]), ("UPDATE", fk["upd"])):
            if rule and rule != "NO ACTION":
                text += f" ON {verb} {rule}"
        lines.append(text)
    return lines


def table_options(engine, charset, collation, options, comment):
    parts = [f"ENGINE={engine}"] if engine else []
    if charset:
        parts.append(f"DEFAULT CHARSET={charset}")
    if collation:
        parts.append(f"COLLATE={collation}")
    for option in str(options or "").split():
        if option.lower() == "partitioned":
            continue
        key, eq, value = option.partition("=")
        parts.append(key.upper() + eq + value)
    if comment:
        parts.append(f"COMMENT={literal(comment)}")
    return " ".join(parts)


def delimited(items):
    """Statements whose bodies may hold ';', as the mysql client and Flyway
    read them: between DELIMITER lines, each ended by //."""
    out = ["DELIMITER //"]
    for notes, head, body in items:
        out.extend(f"-- {note}" for note in notes)
        out.append(head + "\n" + str(body).rstrip("\n") + "\n//")
    out.append("DELIMITER ;")
    return "\n".join(out)


def table_ddl(conn, schema, name):
    head = q(conn, "table-head.sql", s=schema, n=name)[1]
    if not head:
        return ""
    engine, charset, collation, options, comment, partitioned, versioned = head[0]
    mariadb = server(conn) == MARIADB
    checks = sorted(q(conn, "table-checks.sql", s=schema, n=name)[1])
    # MariaDB keeps a column's own CHECK under the column's name, and prints
    # it on the column; its clauses carry no extra escaping
    on_column = {c[0]: c[1] for c in checks if c[3] == "Column"}
    body = [column_line(r, charset, collation, mariadb, on_column.get(r[0]))
            for r in q(conn, "table-columns.sql", s=schema, n=name)[1]]
    body += index_lines(q(conn, "table-indexes.sql", s=schema, n=name)[1], mariadb)
    body += foreign_key_lines(q(conn, "table-foreign-keys.sql", s=schema, n=name)[1])
    body += [f"CONSTRAINT {ident(cname)} CHECK ({clause if mariadb else unescaped(clause)})"
             + (" NOT ENFORCED" if enforced == "NO" else "")
             for cname, clause, enforced, level in checks if level != "Column"]
    notes = []
    if partitioned:
        notes.append("-- partitioned: the PARTITION BY clause is not rebuilt")
    if versioned:
        notes.append("-- system-versioned: WITH SYSTEM VERSIONING and its period columns "
                     "are not rebuilt")
    hidden = hidden_kinds(conn, schema)
    if "trigger" in hidden:
        notes.append(f"-- triggers: {hidden['trigger']}, so none are listed here")
    text = "\n".join(notes + [
        f"CREATE TABLE {ident(schema)}.{ident(name)} (\n"
        + ",\n".join("  " + line for line in body) + "\n) "
        + table_options(engine, charset, collation, options, comment) + ";"])
    triggers = q(conn, "triggers.sql", s=schema, n=None, t=name)[1]
    if triggers:
        text += "\n" + delimited([(created_under(row[7]), trigger_header(schema, row, triggers),
                                   row[5])
                                  for row in triggers if row[5] is not None])
    return text


SEQUENCE_NOTE = ("-- printed by MariaDB's SHOW CREATE SEQUENCE: a copy starts again at "
                 "its START WITH, not where this sequence has reached")


def sequence_ddl(conn, schema, name):
    """A MariaDB sequence as the server prints it, its name qualified: 10.11
    keeps no catalog table for sequences."""
    rows = run_template(conn, "show-create-sequence.sql",
                        sequence=f"{ident(schema)}.{ident(name)}")[1]
    if not rows:
        return ""
    text = re.sub(r"^CREATE SEQUENCE\s+`(?:[^`]|``)+`",
                  lambda m: f"CREATE SEQUENCE {ident(schema)}.{ident(name)}",
                  str(rows[0][1]), count=1)
    return f"{SEQUENCE_NOTE}\n{text};"


def ddl(conn, schema, name):
    objs = resolve(conn, schema, fold(name))
    if not objs:
        return ""
    if objs[0][2] == "TABLE":
        return DDL_NOTE + "\n" + table_ddl(conn, schema, objs[0][1])
    if objs[0][2] == "SEQUENCE":
        return sequence_ddl(conn, schema, objs[0][1])
    parts = [DDL_NOTE]
    routine_privilege = ("SHOW CREATE ROUTINE (or SELECT on mysql.proc)"
                         if server(conn) == MARIADB else "SHOW_ROUTINE (or a global SELECT)")
    for otype, obj, head, body, notes in statements(conn, schema, name):
        if body is None:
            parts.append(f"-- {otype} {obj}: no definition is readable — this account "
                         "neither defined it nor holds "
                         + ("SHOW VIEW on it" if otype == "VIEW" else
                            routine_privilege if otype in ROUTINE_TYPES
                            else f"the {otype} privilege"))
        elif otype == "VIEW":
            parts.append(f"{head}\n{body};")
        elif otype in ("PACKAGE", "PACKAGE BODY"):
            # Oracle syntax: it parses only in the mode it was created in
            mode = q(conn, "routine.sql", s=schema, n=obj)[1]
            mode = next((r[9] for r in mode if r[0] == otype), "")
            parts.append("SET @pythia_sql_mode = @@sql_mode;\n"
                         f"SET SESSION sql_mode = {literal(mode)};\n"
                         + delimited([(notes, head, body)])
                         + "\nSET SESSION sql_mode = @pythia_sql_mode;")
        else:
            parts.append(delimited([(notes, head, body)]))
    return "\n".join(parts)


GREP_COLS = ("NAME", "TYPE", "LINE", "TEXT")


def grep(conn, schema, text, fetch):
    needle = str(text).lower()
    out = []
    for unit, otype, definition in q(conn, "grep.sql", s=schema,
                                     p=like_contains(text))[1]:
        # numbered as src numbers them: line 1 is the CREATE header
        for i, line in enumerate(split_body(definition or ""), 2):
            if needle in line.lower():
                out.append((unit, otype, i, line.strip()))
                if len(out) >= fetch:
                    return GREP_COLS, out
    return GREP_COLS, out


# --- dependency walks -----------------------------------------------------------------

def name_re(name):
    """name as a whole word, backticked or not, in any case, with the schema
    it is qualified with when there is one."""
    return re.compile(r"(?:(`(?:[^`]|``)+`|[\w$]+)\s*\.\s*)?(?<![\w$])`?"
                      + re.escape(name) + r"`?(?![\w$])", re.I)


def refers_to(text, name, own_schema, target_schema):
    """Whether text, a body in own_schema, names target_schema.name: a bare
    name means the body's own schema."""
    for m in name_re(name).finditer(text or ""):
        where = fold(m.group(1)) if m.group(1) else own_schema
        if where.lower() == str(target_schema).lower():
            return True
    return False


def walk(roots, depth, children):
    """Depth-first from each root, in the order a tree is read. An object
    reached twice is listed twice (that is the graph) but walked once."""
    rows, seen = [], set(roots)

    def visit(node, level):
        if level > depth:
            return
        for schema, name, otype, how in children(node):
            rows.append((level, schema, name, otype, how))
            key = (schema, name, otype)
            if key not in seen and otype != "UNRESOLVED":
                seen.add(key)
                visit(key, level + 1)

    for root in roots:
        visit(root, 1)
    return rows


def bodies(conn, schema, name, otype):
    if otype in ROUTINE_TYPES:
        rows = [r[11] for r in q(conn, "routine.sql", s=schema, n=name)[1] if r[0] == otype]
    elif otype == "TRIGGER":
        rows = [r[5] for r in q(conn, "triggers.sql", s=schema, n=name, t=None)[1]]
    else:
        rows = [r[11] for r in q(conn, "event.sql", s=schema, n=name)[1]]
    return [b for b in rows if b]


def dependents(conn, schema, name, depth):
    roots = resolve(conn, schema, fold(name))
    if not roots:
        return None
    mariadb = server(conn) == MARIADB

    def children(node):
        node_schema, node_name, node_type = node
        found = sorted({tuple(r) for r in q(conn, "dependents-catalog.sql", s=node_schema,
                                            n=node_name, t=node_type)[1]})
        out = [r + (CATALOG_HOW,) for r in found]
        seen = set(found) | {node}
        if mariadb and node_type in ("TABLE", "VIEW", "FUNCTION", "SEQUENCE"):
            views = sorted({tuple(r) for r in q(conn, "view-dependents.sql", s=node_schema,
                                                n=node_name)[1]} - seen)
            out += [r + (DEFINITION_HOW,) for r in views]
            seen |= set(views)
        if node_type in ("TRIGGER", "EVENT"):
            return out                          # no code names one to call it
        leads = set()
        for s, n, t, body in q(conn, "dependents-text.sql", p=like_contains(node_name))[1]:
            if (s, n, t) not in seen and refers_to(body, node_name, s, node_schema):
                leads.add((s, n, t))
        return out + [r + (TEXT_HOW,) for r in sorted(leads)]

    blind = [BLIND_TEXT_IN[server(conn)], BLIND_ELSEWHERE] + list(
        hidden_kinds(conn, schema).values())
    return walk(roots, depth, children), blind


def dependencies(conn, schema, name, depth):
    roots = resolve(conn, schema, fold(name))
    if not roots:
        return None

    mariadb = server(conn) == MARIADB

    def children(node):
        node_schema, node_name, node_type = node
        found = sorted({tuple(r) for r in q(conn, "dependencies-catalog.sql", s=node_schema,
                                            n=node_name, t=node_type)[1]})
        out = [r + (CATALOG_HOW,) for r in found]
        seen = set(found) | {node}
        if mariadb and node_type == "VIEW":
            named = sorted({tuple(r) for r in q(conn, "view-dependencies.sql", s=node_schema,
                                                n=node_name)[1]} - seen)
            out += [r + (DEFINITION_HOW,) for r in named]
        if node_type not in CODE_TYPES:
            return out
        leads = set()
        for body in bodies(conn, node_schema, node_name, node_type):
            for s, n, t in q(conn, "dependencies-text.sql", b=body)[1]:
                if (s, n, t) not in seen and refers_to(body, n, node_schema, s):
                    leads.add((s, n, t))
        return out + [r + (TEXT_HOW,) for r in sorted(leads)]

    blind = [BLIND_TEXT_OUT[server(conn)], BLIND_ELSEWHERE] + list(
        hidden_kinds(conn, schema).values())
    return walk(roots, depth, children), blind


# --- errors -----------------------------------------------------------------------------

def error_text(exc):
    """(number, first line of the message) of a driver or socket error."""
    args = getattr(exc, "args", ()) or ()
    number = args[0] if args and isinstance(args[0], int) else None
    raw = args[1] if number is not None and len(args) > 1 else (args[0] if args else exc)
    first = str(raw).strip().splitlines()
    return number, (first[0] if first else str(exc)).strip()


CHECKED_AT_ONCE = 100


def checked_views(conn, schema, views):
    """[(view, message)] for the views MariaDB cannot open, from CHECK TABLE:
    each one's first error, which names the cause (a table or column that is
    gone) before the view's own complaint."""
    broken = {}
    for i in range(0, len(views), CHECKED_AT_ONCE):
        chunk = views[i:i + CHECKED_AT_ONCE]
        named = {f"{schema}.{v}": v for v in chunk}
        listed = ", ".join(f"{ident(schema)}.{ident(v)}" for v in chunk)
        for table, _op, kind, text in run_template(conn, "check-views.sql", views=listed)[1]:
            view = named.get(str(table))
            if view and str(kind).lower() == "error" and str(text) != "Corrupt":
                broken.setdefault(view, str(text))
    return sorted(broken.items())


def view_findings(conn, schema, name):
    if server(conn) == MARIADB:
        views = [r[0] for r in q(conn, "views.sql", s=schema, n=name)[1]]
        found = checked_views(conn, schema, views)
    else:
        found = q(conn, "view-errors.sql", s=schema, n=name)[1]
    return [(n, "VIEW", None, None, "error", message) for n, message in found]


UNCHECKED_SHOWN = 10


def compile_errors(conn, schema, name):
    if name is not None:
        objs = resolve(conn, schema, fold(name))
        if not objs:
            return None
        types = {t for _s, _n, t in objs}
        if "VIEW" in types:
            return view_findings(conn, schema, fold(name)), None
        if types & {"TABLE", "SEQUENCE"}:
            kind = "table" if "TABLE" in types else "sequence"
            return [], f"{name} is a {kind}: {server(conn)} keeps no code in it to check"
        return [], (f"{server(conn)} resolves the names inside {name} only when it "
                    "runs: nothing in it was checked")
    rows = view_findings(conn, schema, None)
    notes = []
    code = q(conn, "unchecked.sql", s=schema)[1]
    if code:
        shown = ", ".join(n for n, _t in code[:UNCHECKED_SHOWN])
        if len(code) > UNCHECKED_SHOWN:
            shown += f" and {len(code) - UNCHECKED_SHOWN} more"
        kinds = ("procedures, functions, packages, triggers and events"
                 if server(conn) == MARIADB else "procedures, functions, triggers and events")
        notes.append(f"{server(conn)} resolves the names inside {kinds} only when they "
                     f"run: {len(code)} were not checked ({shown})")
    notes.extend(hidden_kinds(conn, schema).values())
    return rows, "; ".join(notes) if notes else None
