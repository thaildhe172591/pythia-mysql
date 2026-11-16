"""What `check` adds about the session (pythia-core's optional `status`),
and the `query` tier: the developer's own SELECT, read-only.

status: who the session is and what it may do, whether it is encrypted and
whether the server insists, and the connection headroom — the things an
audit of a connection otherwise needs raw SQL for (a shared server that had
refused 27k connections at its max_connections cap was found this way).
"""
import re

from .catalog import q
from .write import lex

READS = ("select", "show", "describe", "desc", "explain", "with", "table", "values")
# a word a read also uses as a function (REPLACE(), INSERT(), TRUNCATE(),
# CHARACTER SET) counts only in the form a statement takes
WRITES = re.compile(
    r"\b(insert\s+(?:ignore\s+)?into|replace\s+into|update|delete|merge|create|"
    r"alter|drop|truncate\s+table|rename\s+table|grant|revoke|call|handler|"
    r"load\s+data|unlock|prepare|execute|flush|kill|install|uninstall|optimize|"
    r"repair|purge|reset)\b")


def query_refusal(sql):
    """None when the text is one statement that only reads; else why not.
    Read on the masked text, so a literal or a comment saying DELETE is not
    a DELETE. The read-only session behind it is the second line."""
    lexed = lex(sql or "")
    code = " ".join(lexed.masked.lower().split())
    code = re.sub(r"(\s*;)+\s*$", "", code)
    if not code:
        return "the statement is empty"
    if lexed.unterminated:
        return "the statement ends inside a quote or a comment"
    if ";" in code:
        return "query takes one statement; this text holds more than one"
    if lexed.executable:
        return "a /*! ... */ comment is code MySQL runs, and is not read here"
    first = code.split()[0].strip("(")
    if first not in READS:
        return f"{first.upper()} is not a statement that only reads"
    body = code if first not in ("show", "describe", "desc") else ""
    # SHOW ... is a read by its first word; its arguments may name anything
    if re.search(r"\bfor\s+(update|share)\b|\block\s+in\s+share\s+mode\b", body):
        return "it takes a lock (FOR UPDATE / FOR SHARE): query only reads"
    found = WRITES.search(body) if body else None
    if found:
        word = " ".join(found.group(1).split()).upper()
        return f"it holds {word}, and query only reads"
    if re.search(r"\binto\s+(outfile|dumpfile|@|`?\w)", body) and first != "explain":
        return "SELECT ... INTO writes a file or a variable: query only reads"
    if re.search(r"\bload_file\s*\(", body):
        return "LOAD_FILE reads the server's own files: not through query"
    return None


def run_query(conn, schema, sql, fetch):
    """(cols, rows) for the developer's statement, at most `fetch` rows. It
    runs with no binds, so PyMySQL formats nothing in it, in the read-only
    session core opened; core closes it, which rolls back."""
    text = re.sub(r"(\s*;)+\s*$", "", sql.strip())
    with conn.cursor() as cur:
        cur.execute(text)
        cols = [d[0] for d in cur.description] if cur.description else []
        fetchmany = getattr(cur, "fetchmany", None)
        rows = list(fetchmany(fetch)) if callable(fetchmany) else list(cur.fetchall())[:fetch]
    return cols, rows


def _values(conn, name):
    try:
        return {str(k).lower(): str(v if v is not None else "")
                for k, v in q(conn, name)[1]}
    except Exception:  # noqa: BLE001 — a status line is never worth a failed check
        return {}


def _grants(conn):
    lines, roles = [], []
    for (g,) in q(conn, "grants.sql")[1]:
        m = re.match(r"GRANT\s+(.*?)\s+ON\s+(\S+)\s+TO\s", str(g), re.I | re.S)
        if not m:
            r = re.match(r"GRANT\s+(.*?)\s+TO\s", str(g), re.I | re.S)
            if r:
                roles.append(r.group(1).replace("`", ""))
            continue
        privs, scope = " ".join(m.group(1).split()), m.group(2).replace("`", "")
        if privs.upper() == "USAGE":
            continue
        lines.append(f"{privs} on {scope}")
    if roles:
        lines.append("roles " + ", ".join(roles))
    text = "; ".join(lines) or "USAGE only (no privileges)"
    return text if len(text) <= 240 else text[:237] + "..."


def status(conn, accepted_floor=None):
    """[(item, value, warning or None)] for check."""
    out = []
    who = q(conn, "current-user.sql")[1]
    out.append(("user", who[0][0] if who else "", None))
    try:
        out.append(("grants", _grants(conn), None))
    except Exception:  # noqa: BLE001
        out.append(("grants", "could not be read", None))
    var = _values(conn, "session-variables.sql")
    ro = var.get("transaction_read_only", "").upper() in ("ON", "1")
    out.append(("read_only", "yes (this command's session)" if ro else "no", None))
    ses = _values(conn, "session-status.sql")
    cipher = ses.get("ssl_cipher", "")
    forced = var.get("require_secure_transport", "")
    tls = (f"{cipher} ({ses.get('ssl_version') or 'TLS'})" if cipher else "none") + \
        (f"; require_secure_transport {forced}" if forced else "") + \
        (f"; server speaks {var['tls_version']}" if var.get("tls_version") else "")
    out.append(("tls", tls, None if cipher else
                "this session is not encrypted — set \"tls\": \"require\" (or "
                "\"verify\") for the connection"))
    st = _values(conn, "server-status.sql")
    cap = var.get("max_connections", "")
    now, used = st.get("threads_connected", ""), st.get("max_used_connections", "")
    refused = st.get("connection_errors_max_connections", "")
    head = f"{now or '?'} / {cap or '?'} connected"
    if used:
        head += f"; max used {used}" + (f" at {st['max_used_connections_time']}"
                                         if st.get("max_used_connections_time") else "")
    if refused:
        head += f"; {refused} refused at the cap since the server started"
    warn = None
    try:
        if refused and int(refused) > 0:
            warn = (f"the server refused {refused} connections at its max_connections "
                    f"cap ({cap}) — clients see random connection errors")
        elif now and cap and int(now) >= 0.8 * int(cap):
            warn = f"{now} of {cap} connections in use: close to the max_connections cap"
    except ValueError:
        pass
    out.append(("connections", head, warn))
    if accepted_floor:
        out.append(("floor", accepted_floor, None))
    return out
