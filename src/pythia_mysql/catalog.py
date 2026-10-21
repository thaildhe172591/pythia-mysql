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
"""
import pathlib

from pythia_core.queries import load_query, run_query

QUERY_DIR = pathlib.Path(__file__).resolve().parent / "queries"

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
}

# MySQL's own schemas: never a dependent of the developer's objects
SYSTEM_SCHEMAS = ("mysql", "sys", "performance_schema", "information_schema")


def sql_of(name):
    return load_query(QUERY_DIR, name)


def q(conn, name, **binds):
    """(COLUMNS, rows) for one query file. Column names are upper case, as
    every pythia engine reports them."""
    cols, rows = run_query(conn, sql_of(name), binds)
    return [str(c).upper() for c in cols], rows


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
