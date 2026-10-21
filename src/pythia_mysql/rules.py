"""MySQL's lint rules: what MySQL accepts and a reviewer would not.

Each rule reads the statement as the lexer does — strings, `names` and
comments blanked — so a keyword inside a literal or a name never fires one.
What MySQL rejects itself is left to the rehearsal or the prediction.
"""
import re

from .write import _NAME, _qualified, lex, parse_object


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def _hits(stmt, pattern, message, skip=None):
    """(line, message) for every match in the statement's code; the line is
    where the named group `at` starts when the pattern has one."""
    code = lex(stmt).masked.lower()
    out = []
    for m in re.finditer(pattern, code):
        if skip and skip(code, m):
            continue
        at = m.start("at") if "at" in m.re.groupindex and m.group("at") else m.start()
        out.append((_line(stmt, at), message))
    return out


_CREATE_TABLE = re.compile(r"\s*create\s+table\s+(?:if\s+not\s+exists\s+)?" + _NAME, re.I)


def _create_table(stmt, group):
    """(table, the offset just past its column list, masked lower code) of a
    CREATE TABLE with a column list; None for anything else."""
    if group != "structural":
        return None
    m = _CREATE_TABLE.match(lex(stmt).uncommented)
    if not m:
        return None
    code = lex(stmt).masked.lower()
    open_ = re.match(r"\s*\(", code[m.end():])
    if not open_:
        return None                         # CREATE TABLE ... LIKE / AS SELECT
    depth, i = 0, m.end() + open_.end() - 1
    while i < len(code):
        depth += {"(": 1, ")": -1}.get(code[i], 0)
        i += 1
        if depth == 0:
            break
    return _qualified(m)[1], i, code, m


def non_transactional(stmt, group, run):
    if group != "structural":
        return []
    return _hits(stmt, r"\bengine\s*=?\s*(?P<at>myisam|memory|heap|archive|csv|merge|"
                 r"mrg_myisam|blackhole)\b",
                 "a table without transactions: pythia-mysql cannot rehearse a write "
                 "to it, a crash can lose rows, and it ignores foreign keys — use "
                 "InnoDB")


def utf8mb3(stmt, group, run):
    if group not in ("source", "structural"):
        return []
    return _hits(stmt, r"\b(?:charset|character\s+set|collate)\s*=?\s*(?P<at>utf8(?:mb3)?)"
                 r"(?:_\w+)?\b(?!mb4)",
                 "utf8 is utf8mb3: three bytes a character, so no emoji and no rarer "
                 "CJK — utf8mb4 holds every character")


def _after_exists(code, m):
    return re.search(r"\bexists\s*\(\s*$", code[:m.start()]) is not None


def select_star(stmt, group, run):
    if group != "source":
        return []
    return _hits(stmt, r"\bselect\s+(?:distinct\s+|all\s+)?(?:[\w`]+\s*\.\s*)?\*",
                 "SELECT * in stored code: MySQL expands * when a view is created "
                 "and keeps that column list, and a procedure's result changes "
                 "shape when a column is added — name the columns",
                 skip=_after_exists)


def not_in_subquery(stmt, group, run):
    return _hits(stmt, r"\bnot\s+in\s*\(\s*select\b", "NOT IN (SELECT ...) is "
                 "never true when the subquery returns a NULL — use NOT EXISTS")


def no_primary_key(stmt, group, run):
    found = _create_table(stmt, group)
    if not found:
        return []
    table, end, code, m = found
    if re.search(r"\bprimary\s+key\b", code[:end]):
        return []
    return [(_line(stmt, m.start("name")), f"table {table} has no primary key: InnoDB "
             "invents a hidden one that replication and row-based tools cannot use "
             "— give it one")]


def table_comment(stmt, group, run):
    found = _create_table(stmt, group)
    if not found:
        return []
    table, end, code, m = found
    if re.search(r"\bcomment\b", code[end:]):
        return []
    for other in run:
        said = parse_object(other, "comments") if re.match(
            r"\s*alter\s+table\b", lex(other).masked, re.I) else None
        if said and said["table"].lower() == table.lower():
            return []
    return [(_line(stmt, m.start("name")), f"table {table} has no COMMENT in this "
             "change — say what a row is, in the same change that creates it")]


def function_characteristic(stmt, group, run):
    ident = parse_object(stmt, group) if group == "source" else None
    if not ident or ident["type"] != "FUNCTION" or ident["verb"] != "create":
        return []
    code = " ".join(lex(stmt).masked.lower().split())
    returns = re.search(r"\breturns\b", code)
    if not returns:
        return []
    body = re.search(r"\b(begin|return)\b", code[returns.end():])
    said = code[returns.end():returns.end() + body.start()] if body else code[returns.end():]
    if re.search(r"(?<!not )\bdeterministic\b|\bno sql\b|\breads sql data\b", said):
        return []
    return [(_line(stmt, ident["span"][0]), "a function declared none of DETERMINISTIC, "
             "NO SQL or READS SQL DATA is refused while binary logging is on (1418), "
             "unless log_bin_trust_function_creators is set — declare what it does")]


def definer_clause(stmt, group, run):
    if group != "source":
        return []
    return _hits(stmt, r"\b(?P<at>definer)\s*=(?!\s*current_user\b)",
                 "a DEFINER clause names an account: writing it needs SET_ANY_DEFINER, "
                 "and the object breaks where that account does not exist — leave it "
                 "out, and the creator is the definer")


def zero_date(stmt, group, run):
    text = lex(stmt).uncommented
    return [(_line(stmt, m.start()), "a zero date: MySQL's strict default sql_mode "
             "(NO_ZERO_DATE) refuses it — use NULL for no date")
            for m in re.finditer(r"'0000-00-00", text)]


def limit_without_order(stmt, group, run):
    if group != "source":
        return []
    code = lex(stmt).masked.lower()
    out = []
    for m in re.finditer(r"\blimit\b", code):
        start = code.rfind("select", 0, m.start())
        if start >= 0 and not re.search(r"\border\s+by\b", code[start:m.start()]):
            out.append((_line(stmt, m.start()), "LIMIT without ORDER BY takes whichever "
                        "rows come first — an order the next plan may change"))
    return out


RULES = [
    {"id": "mysql-non-transactional", "severity": "error",
     "summary": "tables use InnoDB, not MyISAM, MEMORY or another engine without "
                "transactions", "check": non_transactional},
    {"id": "mysql-utf8mb3", "severity": "warn",
     "summary": "utf8mb4, not utf8 (utf8mb3)", "check": utf8mb3},
    {"id": "mysql-select-star", "severity": "warn",
     "summary": "no SELECT * in views, procedures, functions, triggers and events",
     "check": select_star},
    {"id": "mysql-not-in-subquery", "severity": "warn",
     "summary": "NOT EXISTS over NOT IN (SELECT ...)", "check": not_in_subquery},
    {"id": "mysql-primary-key", "severity": "warn",
     "summary": "every new table has a primary key", "check": no_primary_key},
    {"id": "mysql-table-comment", "severity": "warn",
     "summary": "every new table carries a COMMENT in the same change",
     "check": table_comment},
    {"id": "mysql-function-characteristic", "severity": "warn",
     "summary": "a function declares DETERMINISTIC, NO SQL or READS SQL DATA",
     "check": function_characteristic},
    {"id": "mysql-definer", "severity": "warn",
     "summary": "no DEFINER clause naming another account", "check": definer_clause},
    {"id": "mysql-zero-date", "severity": "warn",
     "summary": "no zero dates", "check": zero_date},
    {"id": "mysql-limit-order", "severity": "info",
     "summary": "LIMIT in stored code comes with ORDER BY", "check": limit_without_order},
]
