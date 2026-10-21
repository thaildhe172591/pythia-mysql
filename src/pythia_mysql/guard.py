"""The harness tier: what pythia-core's guard and install need to know
about MySQL. The guard denies the mysql client (and MySQL Shell,
mysqlimport, mysqladmin, MariaDB's client) when it would write around the
gate; reads through the client are left to the client's own prompt.

The patterns read a shell command for what it names, never for what it
means, so a write spelled in a way they do not list gets through, and a
read that merely mentions DROP TABLE is denied. The gate behind them holds
either way (pythia-core's SECURITY.md).
"""
import pathlib

CLIENTS = r"mysql|mysqlsh|mysqlimport|mysqladmin|mariadb|mariadb-import|mariadb-admin"

# matched against the whole command, quoted SQL included. A word a read
# also uses (REPLACE(), DO in a shell loop, a shell's `source`) counts only
# in the form a statement takes.
WRITE_SQL = "|".join((
    r"(?<!show )\b(create|alter|drop|truncate|grant|revoke|flush|shutdown|restart)\b",
    r"\brename\s+(table|user)\b",
    r"\binsert\s+(low_priority\s+|delayed\s+|high_priority\s+|ignore\s+)*(into\b|[\w`.]+)",
    r"\breplace\s+(low_priority\s+|delayed\s+)*(into\b|[\w`.]+\s+(values?|set|select)\b)",
    r"\bdelete\s+(low_priority\s+|quick\s+|ignore\s+)*(from\b|[\w`.]+)",
    r"\bupdate\s+(low_priority\s+|ignore\s+)*[\w`.]+(\s*,\s*[\w`.]+)*(\s+(as\s+)?\w+)?\s+set\b",
    r"\bload\s+(data|xml)\b",
    r"\b(un)?install\s+(plugin|component)\b",
    r"\bkill\s+(query\s+|connection\s+)?\d",
    r"\b(purge|reset)\s+(binary|master|replica|slave|persist)\b",
    r"\b(optimize|repair|analyze)\s+(no_write_to_binlog\s+|local\s+)?tables?\b",
    r"\bhandler\s+\S+\s+(open|read|close)\b",
    r"\bcall\s+[\w`.]+",
    r"\bdo\s+[\w`.]+\s*\(",
    r"\bprepare\s+\w+\s+from\b|\bexecute\s+\w+",
    r"\bset\s+(global|persist|persist_only|password)\b|\bset\s+@@(global|persist)",
    r"\bselect\b[^;]*\binto\s+(outfile|dumpfile)\b",   # a SELECT that writes a file
    r"\block\s+tables?\b",
    r"\bsource\s+\S+\.sql\b|\\\.\s+\S",            # the client reading a script
    r"\butil\s*\.\s*(load|import)\w*",                # MySQL Shell's loaders
))

# matched with quoted text emptied: what the shell hands the client
SCRIPT = "|".join((
    r"(^|[^<])<(?![<(&])\s*\S",                      # stdin from a file, not <<, <(
    r"\|\s*(\S*[/\\])?(mysql|mysqlsh|mariadb)\b",    # a pipe into the client
    r"(^|\s)(-f|--file)(=|\s)\s*\S",                 # mysqlsh reading a script
    r"\b(mysqlimport|mariadb-import)\b",             # a file into a table, always
    r"\b(mysqladmin|mariadb-admin)\b.*\b(create|drop|flush\w*|kill|password|"
    r"reload|refresh|shutdown|start-replica|stop-replica|debug)\b",
))

TEMPLATE = {
    "default": "dev",
    "dev": {
        "host": "",
        "port": 3306,
        "database": "app_owner",
        "user": "",
        "password": "",
        "tls": "request",
    },
}

SKILLS_DIR = pathlib.Path(__file__).resolve().parent / "skills"
