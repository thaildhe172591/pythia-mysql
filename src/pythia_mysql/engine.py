"""MySQL, through PyMySQL, as a pythia-core engine.

It answers the connect tier (here), the read tier (read.py), the write,
predict and release tiers (write.py), the lint tier (rules.py) and the
harness tier (guard.py). In MySQL a schema is a database: a
connection's "database" is where unqualified names land, and "schema",
when it is set, is what pythia reads (check says when the two differ).
MySQL commits DDL as it runs it, so data is rehearsed in a transaction and
DDL is predicted, written once after the approval, and read back.
"""
import copy
import os
import re
import ssl
import sys

from . import __version__, guard, read, write
from .catalog import QUERY_BINDS, QUERY_DIR, fold, ident, q  # noqa: F401 — QUERY_* re-exported

FLOOR = (8, 4)          # MySQL 8.4 LTS: the oldest CI tests
CONFIG_REL = ".pythia/mysql/connections.json"
REQUIRED = ("host", "database", "user")
TLS = ("off", "request", "require", "verify")
# CLIENT_FOUND_ROWS: an UPDATE reports the rows its WHERE matched, as the
# row-set check counts them, not only the rows whose value changed
FOUND_ROWS = 2


class MySqlEngine:
    name = "mysql"
    label = "MySQL"
    command = "pythia-mysql"
    env_prefix = "PYTHIA_MYSQL"
    version = __version__
    bind_style = "pyformat"
    default_port = 3306
    rollback_notes = {
        "source": "Yes — the definition is snapshotted before every write; a new "
                  "object's undo is a DROP. A routine whose body this account "
                  "cannot read (no SHOW_ROUTINE) is refused.",
        "comments": "Yes — the previous table comment is snapshotted.",
        "data_dml": "No. After commit only a backup, or the binary log replayed "
                    "to a point in time, brings rows back. Revalidation checks "
                    "the rows; it is not an undo.",
        "structural": "No. MySQL commits DDL as it runs it: a dropped column or "
                      "table is gone. The prediction shows what would break "
                      "before anything runs.",
        "grants": "By hand — write the opposite GRANT or REVOKE.",
        "session": "Not needed — it ends with the connection.",
    }

    # --- the connection's life ------------------------------------------------

    def driver_errors(self):
        try:
            import pymysql
        except ModuleNotFoundError:
            sys.exit("The 'PyMySQL' package is required to connect: "
                     "pip install PyMySQL")
        return (pymysql.Error,)

    def connect(self, entry):
        import pymysql
        gaps = [k for k in REQUIRED if not entry.get(k)]
        if gaps:
            sys.exit(f"Connection is missing {', '.join(map(repr, gaps))} — "
                     f"fill in {CONFIG_REL}.")
        tls = str(entry.get("tls") or "request").lower()
        if tls not in TLS:
            sys.exit(f'"tls" must be one of {", ".join(TLS)} — got '
                     f"{entry.get('tls')!r} in {CONFIG_REL}.")
        ca = entry.get("tls_ca")
        if ca and tls != "verify":
            sys.exit(f'"tls_ca" is read only with "tls": "verify" — with '
                     f'"tls": "{tls}" no certificate is checked. Fix {CONFIG_REL}.')
        if ca and not os.path.isfile(ca):
            sys.exit(f'"tls_ca" {ca!r} is not a file — fix {CONFIG_REL}.')
        # autocommit off: every command runs in a transaction that only an
        # approved write ever commits — closing rolls the rest back
        kw = dict(host=entry["host"], port=int(entry.get("port") or self.default_port),
                  database=entry["database"], user=entry["user"],
                  password=entry.get("password") or "", charset="utf8mb4",
                  autocommit=False, client_flag=FOUND_ROWS,
                  connect_timeout=int(entry.get("connect_timeout") or 10),
                  program_name=self.command)
        if tls == "off":
            kw["ssl_disabled"] = True
        elif tls == "require":
            # encrypted or refused; the certificate is not checked
            ctx = ssl.create_default_context()
            ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
            kw["ssl"] = ctx
        elif tls == "verify":
            kw["ssl"] = ssl.create_default_context(cafile=ca or None)
        # "request": PyMySQL's own default — TLS whenever the server offers it
        try:
            return pymysql.connect(**kw)
        except RuntimeError as exc:
            if "cryptography" not in str(exc):
                raise
            sys.exit(f"Could not connect: the account authenticates with "
                     "caching_sha2_password (or sha256_password), and without TLS "
                     "PyMySQL needs the 'cryptography' package to send its "
                     f"password. Let the server offer TLS and set \"tls\": "
                     f"\"request\" or stronger in {CONFIG_REL}, or pip install "
                     "cryptography.")

    def session(self, conn, readonly):
        # a read command's session refuses every write, DDL included: a READ
        # ONLY session characteristic covers the implicit transaction MySQL
        # starts after each DDL commit (pythia-core DESIGN.md §8). A read-only account is
        # the first line; this is the second.
        if readonly:
            q(conn, "session-read-only.sql")
        return conn

    def close(self, conn):
        conn.close()

    def connect_failure(self, exc, conn_name, entry):
        """Name the next step for the failures MySQL has already diagnosed:
        its error number when it sent one, else the text."""
        number, message = read.error_text(exc)
        low = message.lower()
        who = entry.get("user") or "<the user>"
        db = entry.get("database") or "<the database>"
        head = f"Could not connect using connection {conn_name!r}: {message}"
        if isinstance(exc, ssl.SSLError) or "ssl" in low or "certificate" in low:
            return (f"{head}\nThe TLS handshake failed. \"tls\": \"require\" "
                    "encrypts without checking the certificate; \"verify\" checks "
                    f"it against \"tls_ca\" (or this machine's CAs). See {CONFIG_REL}.")
        if number == 1045:
            return (f"{head}\nAccess denied for {who}: a wrong password, or no "
                    f"account {who!r} for this host (MySQL matches 'user'@'host'). "
                    f"Check the entry in {CONFIG_REL}.")
        if number == 1130:
            return (f"{head}\nThe server has no account {who!r} that may connect "
                    "from this host. A DBA creates one for it, or for '%'.")
        if number == 1049:
            return (f"{head}\nMySQL has no database {db!r} — check \"database\" in "
                    f"{CONFIG_REL} (a schema, in MySQL, is a database).")
        if number == 1044:
            return (f"{head}\nThe account works, but holds nothing on database "
                    f"{db!r}. A DBA grants the reads:\n  GRANT SELECT, SHOW VIEW ON "
                    f"{ident(db)}.* TO {ident(who)}@'%';")
        if number == 3159:
            return (f"{head}\nThe server accepts only encrypted connections: set "
                    f"\"tls\": \"require\" (or \"verify\") in {CONFIG_REL}.")
        if number in (2002, 2003, 2005, 2013) or "can't connect" in low \
                or "timed out" in low or "refused" in low:
            return (f"{head}\nNothing answered at {self.target_of(entry)}. Check "
                    "host and port, that MySQL listens on TCP (bind_address), and "
                    "that a firewall lets this machine through.")
        return (f"{head}\nCheck host/port/database, the credentials, and that "
                "the server is reachable from here. Use --conn NAME to try a "
                "different entry.")

    def schema_of(self, entry):
        return fold(entry.get("schema") or entry.get("database") or "")

    def target_of(self, entry):
        host = entry.get("host")
        if not host:
            return ""
        target = f"{host}:{entry.get('port') or self.default_port}"
        return f"{target}/{entry['database']}" if entry.get("database") else target

    # --- what check asks --------------------------------------------------------

    def server_version(self, conn):
        version, edition, database = q(conn, "server-version.sql")[1][0]
        return f"MySQL {version} ({edition}) — database {database}"

    def floor_warning(self, conn):
        """Below MySQL 8.4 LTS, the oldest version CI tests, or not MySQL at
        all: said by `check`, never refused (pythia-core DESIGN.md §8)."""
        version, edition, _db = q(conn, "server-version.sql")[1][0]
        if "mariadb" in f"{version} {edition}".lower():
            return ("This server is MariaDB, not MySQL: pythia-mysql is tested on "
                    "MySQL 8.4 to 9.5 only, and reads MySQL's catalog, which "
                    "MariaDB's differs from. Expect some commands to fail.")
        m = re.match(r"(\d+)\.(\d+)", str(version))
        if not m or (int(m.group(1)), int(m.group(2))) >= FLOOR:
            return None
        return (f"MySQL {m.group(1)}.{m.group(2)} is below pythia-mysql's floor, "
                "8.4: it is not tested there (CI runs 8.4 to 9.5), and Oracle no "
                "longer supports it. Most commands may still work.")

    def current_schema(self, conn):
        rows = q(conn, "current-schema.sql")[1]
        return rows[0][0] if rows and rows[0] and rows[0][0] else None

    # --- the read tier (read.py) -------------------------------------------------

    def object_names(self, conn, schema, pattern, fetch):
        return read.object_names(conn, schema, pattern, fetch)

    def source(self, conn, schema, name):
        return read.source(conn, schema, name)

    def columns(self, conn, schema, name):
        return read.columns(conn, schema, name)

    def ddl(self, conn, schema, name):
        return read.ddl(conn, schema, name)

    def grep(self, conn, schema, text, fetch):
        return read.grep(conn, schema, text, fetch)

    def dependencies(self, conn, schema, name, depth):
        return read.dependencies(conn, schema, name, depth)

    def dependents(self, conn, schema, name, depth):
        return read.dependents(conn, schema, name, depth)

    def compile_errors(self, conn, schema, name):
        return read.compile_errors(conn, schema, name)

    # --- the write tier (write.py) -----------------------------------------------

    def classify(self, text):
        return write.classify(text)

    def prepare_statement(self, text, group):
        return write.prepare_statement(text, group)

    def parse_object(self, stmt, group):
        return write.parse_object(stmt, group)

    def destructive_reason(self, stmt, group):
        return write.destructive_reason(stmt, group)

    def dml_probe(self, stmt):
        return write.dml_probe(stmt)

    def measure_row_set(self, conn, target, pred):
        return write.measure_row_set(conn, target, pred)

    def snapshot(self, conn, schema, group, ident):
        return write.snapshot(conn, schema, group, ident)

    def rehearse(self, conn, schema, group, stmt, ident, snapshot):
        return write.rehearse(conn, schema, group, stmt, ident, snapshot,
                              self.driver_errors())

    def restore_statement(self, group, ident, before, outcome):
        return write.restore_statement(group, ident, before, outcome)

    def privilege_warning(self, conn, schema):
        return write.privilege_warning(conn, schema)

    # --- the predict tier (write.py): DDL runs once, after the approval -----------

    def execute(self, conn, schema, group, stmt, ident):
        return write.execute(conn, schema, group, stmt, ident,
                             self.driver_errors() + (OSError,))

    def verify_written(self, conn, schema, group, stmt, ident, outcome):
        return write.verify_written(conn, schema, group, stmt, ident, outcome,
                                    self.driver_errors())

    # --- the release tier (write.py): a release is data, in one transaction ------

    def split_script(self, text):
        return write.split_script(text)

    # --- the lint tier (rules.py) ------------------------------------------------

    def lint_rules(self):
        from . import rules
        return list(rules.RULES)

    # --- the harness tier (guard.py) ---------------------------------------------

    def raw_client_pattern(self):
        return guard.CLIENTS

    def write_sql_pattern(self):
        return guard.WRITE_SQL

    def script_pattern(self):
        return guard.SCRIPT

    def connections_template(self):
        return copy.deepcopy(guard.TEMPLATE)

    def skills_dir(self):
        return guard.SKILLS_DIR
