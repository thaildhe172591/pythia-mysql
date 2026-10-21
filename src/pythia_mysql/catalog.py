"""Where pythia-mysql's SQL lives and how it is run.

Every statement is a file in queries/, under pythia-core's contract:
pyformat binds, a header, and its binds declared here; a literal % is
written %%. PyMySQL builds each statement with Python's own % operator and
the binds dict — core always passes one, even empty — so %% arrives as %
and the files need no adapter.

The queries read the same under any sql_mode a server or a session sets:
strings in single quotes only (ANSI_QUOTES), CONCAT never || (PIPES_AS_
CONCAT), no backslash in a literal (NO_BACKSLASH_ESCAPES) — which is why a
LIKE escapes with '!' (tests/test_mysql.py holds every file to it).

MariaDB speaks MySQL's protocol and most of its catalog, but not all of it:
it has no view usage tables, marks no view invalid, and keeps no SRS id or
functional index, while it keeps ignored indexes and column-level checks.
A file in queries/mariadb/ of the same name as one in queries/ answers in
its place on MariaDB, with the same binds and columns; a file only there is
asked of MariaDB only. Which server a connection reached is read from the
version it sent on connecting, so knowing costs no query.
"""
import pathlib
import sys

from pythia_core.queries import load_query, run_query

QUERY_DIR = pathlib.Path(__file__).resolve().parent / "queries"
MARIADB_DIR = QUERY_DIR / "mariadb"
MYSQL, MARIADB = "MySQL", "MariaDB"

QUERY_BINDS = {
    "server-version.sql": set(),
    "current-schema.sql": set(),
    "session-read-only.sql": set(),
    "grants.sql": set(),
    "object-names.sql": {"s", "p", "n"},
    "resolve.sql": {"s", "n"},
    "routine.sql": {"s", "n"},
    "routine-params.sql": {"s", "n"},
    "view.sql": {"s", "n"},
    "triggers.sql": {"s", "n", "t"},
    "event.sql": {"s", "n"},
    "columns.sql": {"s", "n"},
    "table-head.sql": {"s", "n"},
    "table-columns.sql": {"s", "n"},
    "table-indexes.sql": {"s", "n"},
    "table-foreign-keys.sql": {"s", "n"},
    "table-checks.sql": {"s", "n"},
    "grep.sql": {"s", "p"},
    "dependents-catalog.sql": {"s", "n", "t"},
    "dependents-text.sql": {"p"},
    "dependencies-catalog.sql": {"s", "n", "t"},
    "dependencies-text.sql": {"b"},
    "view-errors.sql": {"s", "n"},
    "unchecked.sql": {"s"},
    "rehearsal-settings.sql": set(),
    "savepoint.sql": set(),
    "rollback-to-savepoint.sql": set(),
    "warnings.sql": set(),
    "table-engine.sql": {"s", "n"},
    "invalid-views.sql": set(),
    "views-reading.sql": {"s", "n"},
    "views-using.sql": {"p"},
    "views-using-function.sql": {"s", "n"},
    "table-comment.sql": {"s", "n"},
    "current-user.sql": set(),
    "row-set-count.sql": set(),
    "row-set-sample.sql": set(),
}

MARIADB_QUERY_BINDS = {
    # in MySQL's place: no view usage tables, no SRS id, ignored indexes,
    # column-level checks, system-versioned tables
    "dependents-catalog.sql": {"s", "n", "t"},
    "dependencies-catalog.sql": {"s", "n", "t"},
    "table-head.sql": {"s", "n"},
    "table-columns.sql": {"s", "n"},
    "table-indexes.sql": {"s", "n"},
    "table-checks.sql": {"s", "n"},
    # MariaDB's alone: views read in their stored definitions, checked by
    # CHECK TABLE, and sequences shown as the server prints them
    "view-dependents.sql": {"s", "n"},
    "view-dependencies.sql": {"s", "n"},
    "views.sql": {"s", "n"},
    "check-views.sql": set(),
    "show-create-sequence.sql": set(),
}

# MySQL's own schemas: never a dependent of the developer's objects
SYSTEM_SCHEMAS = ("mysql", "sys", "performance_schema", "information_schema")


def server(conn):
    """MySQL or MariaDB: MariaDB names itself in the version it sends when a
    connection opens (10.x behind a '5.5.5-' prefix), which PyMySQL keeps."""
    name = getattr(conn, "_pythia_server", None)
    if name is None:
        info = getattr(conn, "get_server_info", None)
        name = MARIADB if callable(info) and "mariadb" in str(info()).lower() else MYSQL
        try:
            conn._pythia_server = name
        except AttributeError:
            pass
    return name


def sql_of(name, mariadb=False):
    if mariadb and name in MARIADB_QUERY_BINDS:
        return load_query(MARIADB_DIR, name)
    if name not in QUERY_BINDS and name in MARIADB_QUERY_BINDS:
        sys.exit(f"{name} is asked of MariaDB only, and this server is MySQL.")
    return load_query(QUERY_DIR, name)


def q(conn, name, **binds):
    """(COLUMNS, rows) for one query file — MariaDB's own where it has one.
    Column names are upper case, as every pythia engine reports them."""
    cols, rows = run_query(conn, sql_of(name, server(conn) == MARIADB), binds)
    return [str(c).upper() for c in cols], rows


def run_template(conn, name, **parts):
    """(columns, rows) for a query file whose /*PART*/ markers take text
    pythia quoted itself (an identifier list a bind cannot carry). It runs
    with no binds, so PyMySQL formats nothing in it."""
    sql = sql_of(name, server(conn) == MARIADB)
    for key, text in parts.items():
        sql = sql.replace(f"/*{key.upper()}*/", text)
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, cur.fetchall() if cur.description else []


def fold(name):
    """A name as the catalog holds it: `backticked` or "quoted" (ANSI_QUOTES)
    taken exactly, the quoting removed. Case is left as typed: MySQL compares
    table names as lower_case_table_names says, routine names without regard
    to case, and information_schema's collations already do the same."""
    name = str(name).strip()
    if len(name) >= 2 and name[0] == name[-1] == "`":
        return name[1:-1].replace("``", "`")
    if len(name) >= 2 and name[0] == name[-1] == '"':
        return name[1:-1].replace('""', '"')
    return name


def ident(name):
    """A name quoted as MySQL reads it whatever the sql_mode: in backticks."""
    return "`" + str(name).replace("`", "``") + "`"


def literal(text):
    """A string literal as mysqldump writes one: '' for a quote, \\\\ for a
    backslash (MySQL reads a backslash as an escape unless
    NO_BACKSLASH_ESCAPES is set)."""
    return "'" + str(text).replace("\\", "\\\\").replace("'", "''") + "'"


def like_contains(text):
    """A LIKE pattern matching text anywhere. The queries declare ESCAPE '!':
    a backslash escape would mean something else under NO_BACKSLASH_ESCAPES."""
    esc = "".join("!" + ch if ch in "!%_" else ch for ch in str(text))
    return f"%{esc}%"
