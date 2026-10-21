#!/usr/bin/env python3
"""Self-checks for pythia-mysql — no database, and no PyMySQL either: a
stand-in driver module records what the engine asks of it, and a stand-in
catalog answers by query file.

Needs pythia-core importable: installed, or a checkout next to this one
(../pythia-core), or PYTHIA_CORE_SRC pointing at its src/.

Run: python tests/test_mysql.py
"""
import contextlib
import datetime
import io
import json
import os
import pathlib
import re
import ssl
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
try:
    import pythia_core  # noqa: F401
except ModuleNotFoundError:
    for candidate in (os.environ.get("PYTHIA_CORE_SRC"),
                      ROOT.parent / "pythia-core" / "src"):
        if candidate and pathlib.Path(candidate).is_dir():
            sys.path.insert(1, str(candidate))
            break

from pythia_core.engine import engine_problems  # noqa: E402
from pythia_core.queries import contract_problems, query_binds  # noqa: E402

import pythia_mysql  # noqa: E402
from pythia_mysql import cli, read  # noqa: E402
from pythia_mysql.catalog import (QUERY_BINDS, QUERY_DIR, fold, ident, like_contains,  # noqa: E402
                                  literal, sql_of)
from pythia_mysql.engine import MySqlEngine  # noqa: E402


def expect_exit(fn, *needles):
    try:
        fn()
    except SystemExit as e:
        msg = str(e).lower()
        for n in needles:
            assert n.lower() in msg, f"exit message missing {n!r}: {e}"
        return str(e)
    raise AssertionError("expected SystemExit, none raised")


# --- a stand-in for PyMySQL, and a catalog answered by query file -----------------

QUERY_TEXT = {sql_of(n): n for n in QUERY_BINDS}


class DriverError(Exception):
    pass


class CatalogCursor:
    def __init__(self, conn):
        self.conn, self.description, self._rows = conn, None, []

    def execute(self, sql, params=None):
        assert params is not None, "always pass a dict"
        name = QUERY_TEXT[sql]                 # only files from queries/
        # PyMySQL formats every statement with Python's %: a lone % fails here
        sql % {k: "''" for k in params}
        self.conn.asked.append((name, dict(params)))
        answer = self.conn.answers.get(name, ((), []))
        cols, rows = answer(params) if callable(answer) else answer
        self.description = [(c,) for c in cols] if cols else None
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class CatalogConn:
    def __init__(self, answers):
        self.answers, self.asked = answers, []
        self.closed, self.commits = False, 0

    def cursor(self):
        return CatalogCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True

    def names(self):
        return [n for n, _ in self.asked]


BASIC = {
    "server-version.sql": (("version", "edition", "database_name"),
                           [("8.4.11", "MySQL Community Server - GPL", "app_owner")]),
    "current-schema.sql": (("current_schema",), [("app_owner",)]),
}


@contextlib.contextmanager
def fake_pymysql(answers=None, fail=None):
    """Install a stand-in pymysql; yields the record of what was asked."""
    record = {"connect": [], "conns": []}
    mod = types.ModuleType("pymysql")

    def connect(**kw):
        record["connect"].append(kw)
        if fail:
            raise fail
        conn = CatalogConn(dict(answers or BASIC))
        record["conns"].append(conn)
        return conn

    mod.Error, mod.connect = DriverError, connect
    saved, had = sys.modules.get("pymysql"), "pymysql" in sys.modules
    sys.modules["pymysql"] = mod
    try:
        yield record
    finally:
        if had:
            sys.modules["pymysql"] = saved
        else:
            del sys.modules["pymysql"]


@contextlib.contextmanager
def project(cfg):
    keep_env = {k: os.environ.pop(k) for k in list(os.environ)
                if k.startswith("PYTHIA_MYSQL_")}
    keep_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / ".pythia" / "mysql" / "connections.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(cfg), encoding="utf-8")
        if os.name == "posix":
            os.chmod(path, 0o600)
        os.chdir(td)
        try:
            yield pathlib.Path(td)
        finally:
            os.chdir(keep_cwd)
            os.environ.update(keep_env)


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


DEV = {"dev": {"host": "localhost", "port": 3306, "database": "app_owner",
               "user": "app_agent", "password": "s3cret"}}


# --- packaging -----------------------------------------------------------------------

def pyproject():
    return (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_version_matches_pyproject():
    declared = re.search(r'^version\s*=\s*"([^"]+)"', pyproject(), re.M).group(1)
    assert pythia_mysql.__version__ == declared == MySqlEngine.version


def test_dependencies_are_core_and_the_driver_only():
    deps = re.search(r"^dependencies\s*=\s*\[(.*?)\]", pyproject(), re.M | re.S).group(1)
    names = {re.match(r"[A-Za-z0-9_.-]+", d.strip().strip('"')).group(0)
             for d in re.findall(r'"([^"]+)"', deps)}
    assert names == {"pythia-core", "PyMySQL"}, names


def test_console_script_is_pythia_mysql():
    assert 'pythia-mysql = "pythia_mysql.cli:main"' in pyproject()
    assert not re.search(r"^pythia\s*=", pyproject(), re.M)


# --- contracts -------------------------------------------------------------------------

def test_engine_answers_the_connect_and_read_tiers():
    assert engine_problems(MySqlEngine(), tiers=("connect", "read")) == []


def test_query_contract_holds():
    assert contract_problems(QUERY_DIR, QUERY_BINDS, "pyformat") == []


def test_pymysql_formats_every_query_with_its_binds():
    """PyMySQL builds the statement with Python's % operator and the binds
    dict — always a dict, even an empty one — so %% becomes % and a lone %
    is an error."""
    for name in QUERY_BINDS:
        sql = sql_of(name)
        assert query_binds(sql, "pyformat") == QUERY_BINDS[name], name
        sql % {b: "NULL" for b in QUERY_BINDS[name]}


def test_no_query_leans_on_a_session_setting():
    """Every query reads the same under any sql_mode: no double-quoted
    string (ANSI_QUOTES), no || (PIPES_AS_CONCAT), no backslash in a literal
    (NO_BACKSLASH_ESCAPES)."""
    for name in QUERY_BINDS:
        body = "\n".join(line for line in sql_of(name).splitlines()
                         if not line.lstrip().startswith("--"))
        assert '"' not in body and "||" not in body and "\\" not in body, name


def test_example_config_resolves_and_holds_no_secret():
    cfg = json.loads((ROOT / "examples" / "connections.example.json").read_text(encoding="utf-8"))
    assert cfg["default"] in cfg
    for name, entry in cfg.items():
        if name == "default":
            continue
        assert entry["password"] == ""
        assert {"host", "port", "database", "user", "tls"} <= set(entry)


# --- the engine ------------------------------------------------------------------------

def test_names_keep_their_case_and_lose_their_quoting():
    assert fold("`t_order`") == "t_order" and fold('"T_Order"') == "T_Order"
    assert fold("`a``b`") == "a`b" and fold("t_order") == "t_order"
    e = MySqlEngine()
    assert e.schema_of({"database": "`app_owner`"}) == "app_owner"
    assert e.schema_of({"database": "app", "schema": "reporting"}) == "reporting"


def test_identifiers_and_literals_are_quoted_as_mysql_reads_them():
    assert ident("t_order") == "`t_order`" and ident("a`b") == "`a``b`"
    assert literal("it's") == "'it''s'" and literal("a\\b") == "'a\\\\b'"


def test_like_patterns_escape_like_itself():
    # '!' escapes, whatever NO_BACKSLASH_ESCAPES says
    assert like_contains("50%_off!") == "%50!%!_off!!%"


def test_target_never_shows_the_password():
    e = MySqlEngine()
    assert e.target_of(DEV["dev"]) == "localhost:3306/app_owner"
    assert "s3cret" not in e.target_of(DEV["dev"])
    assert e.target_of({"host": "db"}) == "db:3306" and e.target_of({}) == ""


def test_connect_passes_exactly_the_settings():
    e = MySqlEngine()
    with fake_pymysql() as rec:
        e.connect(DEV["dev"])
        e.connect({"host": "h", "database": "d", "user": "u", "tls": "off"})
        e.connect({"host": "h", "database": "d", "user": "u", "tls": "require"})
        e.connect({"host": "h", "database": "d", "user": "u", "tls": "verify"})
    first, off, require, verify = rec["connect"]
    assert first == {"host": "localhost", "port": 3306, "database": "app_owner",
                     "user": "app_agent", "password": "s3cret", "charset": "utf8mb4",
                     "autocommit": False, "connect_timeout": 10,
                     # CLIENT_FOUND_ROWS: an UPDATE counts the rows it matched
                     "client_flag": 2,
                     "program_name": "pythia-mysql"}      # "request": PyMySQL's own default
    assert off["ssl_disabled"] is True and "ssl" not in off
    # one statement per call, and no client file read by the server, ever:
    # MySQL refuses the text after a statement when MULTI_STATEMENTS is off
    for kw in (first, off, require, verify):
        assert not kw["client_flag"] & (1 << 16) and not kw["client_flag"] & 128, kw
        assert not kw.get("local_infile"), kw
    # require: encrypted or refused, the certificate not checked
    assert isinstance(require["ssl"], ssl.SSLContext)
    assert require["ssl"].verify_mode == ssl.CERT_NONE and not require["ssl"].check_hostname
    # verify: the certificate and the host name both checked
    assert verify["ssl"].verify_mode == ssl.CERT_REQUIRED and verify["ssl"].check_hostname


def test_connect_refuses_a_half_filled_or_unknown_setting_before_the_driver():
    e = MySqlEngine()
    with fake_pymysql() as rec:
        expect_exit(lambda: e.connect({"host": "h", "user": "u"}),
                    "'database'", ".pythia/mysql/connections.json")
        expect_exit(lambda: e.connect(dict(DEV["dev"], tls="yes")),
                    "off, request, require, verify")
        expect_exit(lambda: e.connect(dict(DEV["dev"], tls_ca="ca.pem")),
                    '"tls_ca"', '"verify"')
    assert rec["connect"] == []


def test_missing_driver_names_the_package():
    saved, had = sys.modules.get("pymysql"), "pymysql" in sys.modules
    sys.modules["pymysql"] = None
    try:
        expect_exit(MySqlEngine().driver_errors, "pip install PyMySQL")
    finally:
        if had:
            sys.modules["pymysql"] = saved
        else:
            del sys.modules["pymysql"]


def test_an_auth_plugin_that_needs_cryptography_is_explained():
    # caching_sha2_password without TLS needs RSA, which PyMySQL leaves to
    # an optional package: a RuntimeError, not a driver error
    boom = RuntimeError("'cryptography' package is required for sha256_password or "
                        "caching_sha2_password auth methods")
    with fake_pymysql(fail=boom):
        expect_exit(lambda: MySqlEngine().connect(dict(DEV["dev"], tls="off")),
                    "caching_sha2_password", '"tls"')


def failure(number, message):
    exc = DriverError(number, message)
    return MySqlEngine().connect_failure(exc, "dev", DEV["dev"])


def test_connect_failure_names_the_next_step():
    assert "Access denied for app_agent" in failure(
        1045, "Access denied for user 'app_agent'@'10.0.0.5' (using password: YES)")
    assert "no database 'app_owner'" in failure(1049, "Unknown database 'app_owner'")
    assert "GRANT SELECT, SHOW VIEW ON `app_owner`.* TO" in failure(
        1044, "Access denied for user 'app_agent'@'%' to database 'app_owner'")
    assert "Nothing answered at localhost:3306/app_owner" in failure(
        2003, "Can't connect to MySQL server on 'localhost' ([Errno 111] Connection refused)")
    assert '"tls": "require"' in failure(
        3159, "Connections using insecure transport are prohibited while "
              "--require_secure_transport=ON.")
    assert "TLS handshake" in MySqlEngine().connect_failure(
        ssl.SSLError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"),
        "dev", DEV["dev"])
    generic = failure(1105, "something else")
    assert "host/port/database" in generic and "s3cret" not in generic


def test_error_text_reads_the_number_and_the_first_line():
    assert read.error_text(DriverError(1146, "Table 'app_owner.t_gone' doesn't exist")) == \
        (1146, "Table 'app_owner.t_gone' doesn't exist")
    assert read.error_text(DriverError("no number")) == (None, "no number")
    assert read.error_text(OSError("timed out\nmore")) == (None, "timed out")


# --- end to end, through pythia-core ------------------------------------------------------

def test_check_end_to_end_and_reads_are_refused_writes():
    with fake_pymysql() as rec, project(DEV):
        code, out, err = run("check", "--json")
    doc = json.loads(out)
    assert code == 0 and doc["schema"] == "app_owner" and doc["schema_drift"] is False
    assert {"ITEM": "server", "VALUE": "MySQL 8.4.11 (MySQL Community Server - GPL) "
            "— database app_owner"} in doc["rows"]
    conn = rec["conns"][0]
    # a read session refuses every write, DDL included (MySQL refuses it in
    # a READ ONLY session), before anything else runs
    assert conn.names()[0] == "session-read-only.sql"
    assert conn.closed is True and conn.commits == 0


def test_check_warns_below_mysql_8_4_and_on_mariadb_and_refuses_nothing():
    for version, comment, said in (
            ("8.0.43", "MySQL Community Server - GPL", "MySQL 8.0 is below pythia-mysql's floor, 8.4"),
            ("5.7.44-log", "MySQL Community Server (GPL)", "MySQL 5.7 is below pythia-mysql's floor, 8.4"),
            ("11.4.5-MariaDB-ubu2404", "mariadb.org binary distribution", "This server is MariaDB, not MySQL")):
        answers = dict(BASIC)
        answers["server-version.sql"] = (("version", "edition", "database_name"),
                                         [(version, comment, "app_owner")])
        with fake_pymysql(answers), project(DEV):
            code, out, _ = run("check")
        assert code == 0 and f"! {said}" in out, out
    for version in ("8.4.0", "9.5.0"):
        answers = dict(BASIC)
        answers["server-version.sql"] = (("version", "edition", "database_name"),
                                         [(version, "MySQL Community Server - GPL", "app_owner")])
        with fake_pymysql(answers), project(DEV):
            code, out, _ = run("check", "--json")
        assert code == 0 and json.loads(out)["below_floor"] is None, version


def test_check_reports_where_unqualified_names_land():
    with fake_pymysql(), project({"dev": dict(DEV["dev"], schema="reporting")}):
        code, out, _ = run("check")
    assert code == 0 and "current schema is 'app_owner'" in out


def test_check_turns_a_refused_login_into_advice():
    with fake_pymysql(fail=DriverError(1045, "Access denied for user 'app_agent'@'h'")), \
            project(DEV):
        expect_exit(lambda: run("check"), "access denied for app_agent")


def test_another_tools_config_is_not_ours():
    keep = os.getcwd()
    with tempfile.TemporaryDirectory() as td:
        for other in (".pythia/connections.json", ".pythia/postgres/connections.json",
                      ".pythia/mssql/connections.json"):
            path = pathlib.Path(td) / other
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"dev": {"user": "x"}}), encoding="utf-8")
        os.chdir(td)
        try:
            with fake_pymysql() as rec:
                expect_exit(lambda: run("check"), "no mysql connection")
            assert rec["connect"] == []
        finally:
            os.chdir(keep)


# --- the read tier: what MySQL keeps, rebuilt ------------------------------------------------

RESOLVE = ("schema_name", "name", "type")
T_ORDER = ("app_owner", "t_order", "TABLE")
V_PAID = ("app_owner", "v_paid", "VIEW")
F_TOTAL = ("app_owner", "f_total", "FUNCTION")
P_PAID = ("app_owner", "p_paid", "PROCEDURE")
TRG = ("app_owner", "trg_order_audit", "TRIGGER")
EV = ("app_owner", "ev_purge", "EVENT")


def resolving(*objs):
    return lambda b: (RESOLVE, [o for o in objs if o[0] == b["s"] and o[1] == b["n"]])


ROUTINE_COLS = ("type", "name", "returns", "returns_charset", "is_deterministic",
                "data_access", "security", "comment", "definer", "sql_mode",
                "language", "body", "schema_charset")
PARAM_COLS = ("routine_type", "position", "mode", "name", "data_type", "charset")
P_PAID_ROW = ("PROCEDURE", "p_paid", None, None, "NO", "MODIFIES SQL DATA", "INVOKER",
              "marks one order paid", "root@%", "STRICT_TRANS_TABLES", "SQL",
              "begin\n    -- mark it paid; a ; in a comment\n"
              "    update t_order set status = 'PAID' where id = p_id;\nend", "utf8mb4")
F_TOTAL_ROW = ("FUNCTION", "f_total", "varchar(20)", "latin1", "YES", "READS SQL DATA",
               "DEFINER", "", "app_owner@localhost", "STRICT_TRANS_TABLES", "SQL",
               "return (select total from t_order where id = p_id)", "utf8mb4")


def routine_catalog(*extra):
    answers = {
        "resolve.sql": resolving(T_ORDER, P_PAID, F_TOTAL),
        "routine.sql": lambda b: (ROUTINE_COLS, [r for r in (P_PAID_ROW, F_TOTAL_ROW)
                                                 if r[1] == b["n"]]),
        "routine-params.sql": lambda b: (PARAM_COLS, {
            "p_paid": [("PROCEDURE", 1, "IN", "p_id", "bigint", None),
                       ("PROCEDURE", 2, "INOUT", "p_note", "varchar(30)", "utf8mb4"),
                       ("PROCEDURE", 3, "OUT", "p_n", "int", None)],
            "f_total": [("FUNCTION", 1, "IN", "p_id", "bigint", None)]}.get(b["n"], [])),
    }
    for more in extra:
        answers.update(more)
    return CatalogConn(answers)


def test_a_routine_is_rebuilt_header_on_line_one_and_body_as_written():
    conn = routine_catalog()
    rows = read.source(conn, "app_owner", "`p_paid`")
    assert rows == [
        ("p_paid", 1, "CREATE DEFINER=`root`@`%` PROCEDURE `app_owner`.`p_paid`(IN `p_id` "
                      "bigint, INOUT `p_note` varchar(30), OUT `p_n` int) MODIFIES SQL DATA "
                      "SQL SECURITY INVOKER COMMENT 'marks one order paid'"),
        ("p_paid", 2, "begin"),
        ("p_paid", 3, "    -- mark it paid; a ; in a comment"),
        ("p_paid", 4, "    update t_order set status = 'PAID' where id = p_id;"),
        ("p_paid", 5, "end")], rows
    rows = read.source(conn, "app_owner", "f_total")
    # a string type in another character set than the schema's says so
    assert rows[0][2] == ("CREATE DEFINER=`app_owner`@`localhost` FUNCTION "
                          "`app_owner`.`f_total`(`p_id` bigint) RETURNS varchar(20) "
                          "CHARSET latin1 READS SQL DATA DETERMINISTIC"), rows
    assert rows[1] == ("f_total", 2, "return (select total from t_order where id = p_id)")
    assert read.source(conn, "app_owner", "t_order") == []      # a table has no source


def test_an_unreadable_body_is_no_source_and_a_ddl_that_says_why():
    hidden = list(P_PAID_ROW)
    hidden[11] = None                  # no SHOW_ROUTINE, and not the definer
    conn = routine_catalog({"routine.sql": (ROUTINE_COLS, [tuple(hidden)])})
    assert read.source(conn, "app_owner", "p_paid") == []
    assert "SHOW_ROUTINE" in read.ddl(conn, "app_owner", "p_paid")


VIEW_COLS = ("name", "definition", "check_option", "security", "definer")
TRIGGER_COLS = ("name", "timing", "event", "table_name", "action_order", "body",
                "definer", "sql_mode")
EVENT_COLS = ("name", "event_type", "execute_at", "interval_value", "interval_field",
              "starts", "ends", "on_completion", "status", "comment", "definer",
              "body", "sql_mode", "time_zone")


def test_views_triggers_and_events_are_rebuilt_too():
    conn = CatalogConn({
        "resolve.sql": resolving(V_PAID, TRG, EV),
        "view.sql": (VIEW_COLS, [("v_paid", "select `app_owner`.`t_order`.`id` AS `id` from "
                                  "`app_owner`.`t_order`", "CASCADED", "INVOKER", "root@%")]),
        "triggers.sql": lambda b: (TRIGGER_COLS, [
            ("trg_order_audit", "AFTER", "UPDATE", "t_order", 1,
             "insert into t_order_audit (order_id) values (new.id)", "root@%", "")]),
        "event.sql": (EVENT_COLS, [("ev_purge", "RECURRING", None, "1", "DAY",
                                    datetime.datetime(2030, 1, 1), None, "NOT PRESERVE",
                                    "DISABLED", "keeps 30 days", "root@%",
                                    "delete from t_order_audit", "", "SYSTEM")])})
    assert read.source(conn, "app_owner", "v_paid") == [
        ("v_paid", 1, "CREATE DEFINER=`root`@`%` SQL SECURITY INVOKER VIEW "
                      "`app_owner`.`v_paid` AS"),
        ("v_paid", 2, "select `app_owner`.`t_order`.`id` AS `id` from `app_owner`.`t_order` "
                      "WITH CASCADED CHECK OPTION")]
    assert read.source(conn, "app_owner", "trg_order_audit")[0][2] == (
        "CREATE DEFINER=`root`@`%` TRIGGER `app_owner`.`trg_order_audit` AFTER UPDATE ON "
        "`app_owner`.`t_order` FOR EACH ROW")
    assert "\n-- created under time_zone=SYSTEM: AT, STARTS and ENDS are times there\n" \
        in read.ddl(conn, "app_owner", "ev_purge")
    assert read.source(conn, "app_owner", "ev_purge")[:2] == [
        ("ev_purge", 1, "CREATE DEFINER=`root`@`%` EVENT `app_owner`.`ev_purge` ON SCHEDULE "
                        "EVERY 1 DAY STARTS '2030-01-01 00:00:00' ON COMPLETION NOT PRESERVE "
                        "DISABLE COMMENT 'keeps 30 days' DO"),
        ("ev_purge", 2, "delete from t_order_audit")]


def test_a_trigger_after_another_says_which():
    conn = CatalogConn({
        "resolve.sql": resolving(("app_owner", "trg_b", "TRIGGER")),
        "triggers.sql": lambda b: (TRIGGER_COLS, [
            row for row in (
                ("trg_a", "BEFORE", "INSERT", "t_order", 1, "set new.total = 0", "root@%", ""),
                ("trg_b", "BEFORE", "INSERT", "t_order", 2, "set new.status = 'DRAFT'",
                 "root@%", ""))
            if b["n"] is None or row[0] == b["n"]])})
    assert read.source(conn, "app_owner", "trg_b")[0][2].endswith(
        "BEFORE INSERT ON `app_owner`.`t_order` FOR EACH ROW FOLLOWS `trg_a`")


TABLE_HEAD = ("engine", "charset", "collation", "options", "comment", "partitioned")
TABLE_COLS = ("name", "type", "nullable", "default_value", "extra", "generation",
              "charset", "collation", "comment", "srs_id")
INDEX_COLS = ("name", "non_unique", "seq", "column_name", "sub_part", "direction",
              "index_type", "expression", "visible", "comment")
FK_COLS = ("name", "column_name", "ref_schema", "ref_table", "ref_column", "on_update",
           "on_delete")
CHECK_COLS = ("name", "clause", "enforced")


def table_catalog(partitioned=0, triggers=()):
    return CatalogConn({
        "resolve.sql": resolving(T_ORDER),
        "table-head.sql": (TABLE_HEAD, [("InnoDB", "utf8mb4", "utf8mb4_0900_ai_ci",
                                         "row_format=DYNAMIC stats_persistent=1 partitioned",
                                         "Orders, 'all'", partitioned)]),
        "table-columns.sql": (TABLE_COLS, [
            ("id", "bigint unsigned", "NO", None, "auto_increment", "", None, None, "", None),
            ("code", "varchar(20)", "NO", None, "", "", "latin1", "latin1_bin", "it's", None),
            ("status", "enum('DRAFT','PAID')", "NO", "DRAFT", "", "", "utf8mb4",
             "utf8mb4_0900_ai_ci", "", None),
            ("total", "decimal(12,2)", "NO", "0.00", "", "", None, None, "", None),
            ("ratio", "double", "YES", None, "", "", None, None, "", None),
            ("created", "timestamp(3)", "NO", "CURRENT_TIMESTAMP(3)",
             "DEFAULT_GENERATED on update CURRENT_TIMESTAMP(3)", "", None, None, "", None),
            ("token", "char(36)", "NO", "uuid()", "DEFAULT_GENERATED", "", "utf8mb4",
             "utf8mb4_0900_ai_ci", "", None),
            ("doubled", "decimal(13,2)", "YES", None, "VIRTUAL GENERATED", "(`total` * 2)",
             None, None, "", None),
            ("flag", "bit(1)", "NO", "b'1'", "", "", None, None, "", None),
            ("secret", "int", "YES", None, "INVISIBLE", "", None, None, "", None),
            ("spot", "point", "NO", None, "", "", None, None, "", 4326)]),
        "table-indexes.sql": (INDEX_COLS, [
            ("PRIMARY", 0, 1, "id", None, "A", "BTREE", None, "YES", ""),
            ("ix_expr", 1, 1, None, None, "A", "BTREE", "lower(`code`)", "YES", ""),
            ("ix_prefix", 1, 1, "code", 5, "A", "BTREE", None, "NO", "prefix"),
            ("ix_status_total", 1, 1, "status", None, "A", "BTREE", None, "YES", ""),
            ("ix_status_total", 1, 2, "total", None, "D", "BTREE", None, "YES", ""),
            ("ft_code", 1, 1, "code", None, None, "FULLTEXT", None, "YES", ""),
            ("uk_code", 0, 1, "code", None, "A", "BTREE", None, "YES", "")]),
        "table-foreign-keys.sql": (FK_COLS, [
            ("fk_parent", "id", "app_owner", "t_parent", "id", "NO ACTION", "CASCADE"),
            ("fk_other", "code", "reporting", "t_code", "code", "RESTRICT", "NO ACTION")]),
        "table-checks.sql": (CHECK_COLS, [("ck_total", "(`total` >= 0)", "YES"),
                                          ("ck_ratio", "(`ratio` < 1)", "NO")]),
        "triggers.sql": (TRIGGER_COLS, list(triggers)),
    })


def test_a_table_is_rebuilt_column_by_column():
    ddl = read.ddl(table_catalog(), "app_owner", "t_order")
    assert ddl.startswith("-- rebuilt from information_schema by pythia-mysql")
    body = ddl[ddl.index("CREATE TABLE"):]
    assert body == (
        "CREATE TABLE `app_owner`.`t_order` (\n"
        "  `id` bigint unsigned NOT NULL AUTO_INCREMENT,\n"
        "  `code` varchar(20) CHARACTER SET latin1 COLLATE latin1_bin NOT NULL COMMENT 'it''s',\n"
        "  `status` enum('DRAFT','PAID') NOT NULL DEFAULT 'DRAFT',\n"
        "  `total` decimal(12,2) NOT NULL DEFAULT '0.00',\n"
        "  `ratio` double DEFAULT NULL,\n"
        "  `created` timestamp(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) "
        "ON UPDATE CURRENT_TIMESTAMP(3),\n"
        "  `token` char(36) NOT NULL DEFAULT (uuid()),\n"
        "  `doubled` decimal(13,2) GENERATED ALWAYS AS ((`total` * 2)) VIRTUAL,\n"
        "  `flag` bit(1) NOT NULL DEFAULT b'1',\n"
        "  `secret` int DEFAULT NULL INVISIBLE,\n"
        "  `spot` point NOT NULL SRID 4326,\n"
        "  PRIMARY KEY (`id`),\n"
        "  UNIQUE KEY `uk_code` (`code`),\n"
        "  KEY `ix_expr` ((lower(`code`))),\n"
        "  KEY `ix_prefix` (`code`(5)) COMMENT 'prefix' INVISIBLE,\n"
        "  KEY `ix_status_total` (`status`,`total` DESC),\n"
        "  FULLTEXT KEY `ft_code` (`code`),\n"
        "  CONSTRAINT `fk_other` FOREIGN KEY (`code`) REFERENCES `reporting`.`t_code` "
        "(`code`) ON UPDATE RESTRICT,\n"
        "  CONSTRAINT `fk_parent` FOREIGN KEY (`id`) REFERENCES `app_owner`.`t_parent` "
        "(`id`) ON DELETE CASCADE,\n"
        "  CONSTRAINT `ck_ratio` CHECK ((`ratio` < 1)) NOT ENFORCED,\n"
        "  CONSTRAINT `ck_total` CHECK ((`total` >= 0))\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci "
        "ROW_FORMAT=DYNAMIC STATS_PERSISTENT=1 COMMENT='Orders, ''all''';"), body


def test_expressions_lose_the_escaping_information_schema_adds():
    """information_schema keeps an expression with one more level of
    backslash escaping than SHOW CREATE TABLE prints — a check clause, a
    generated column, an expression default, a functional index."""
    conn = table_catalog()
    conn.answers["table-columns.sql"] = (TABLE_COLS, [
        ("a", "varchar(20)", "YES", "it's", "", "", None, None, "", None),
        ("b", "varchar(20)", "YES", None, "VIRTUAL GENERATED",
         "concat(`a`,_utf8mb4\\'x\\\\\\'y\\\\\\\\z\\')", None, None, "", None),
        ("c", "varchar(30)", "YES", "concat(_utf8mb4\\'p\\\\\\'q\\')", "DEFAULT_GENERATED",
         "", None, None, "", None)])
    conn.answers["table-indexes.sql"] = (INDEX_COLS, [
        ("ix_q", 1, 1, None, None, "A", "BTREE", "concat(`a`,_utf8mb4\\'k\\')", "YES", "")])
    conn.answers["table-checks.sql"] = (CHECK_COLS, [
        ("ck_q", "(`a` in (_utf8mb4\\'DRAFT\\',_utf8mb4\\'PAID\\'))", "YES")])
    conn.answers["table-foreign-keys.sql"] = (FK_COLS, [])
    ddl = read.ddl(conn, "app_owner", "t_order")
    assert "  `a` varchar(20) DEFAULT 'it''s',\n" in ddl, ddl
    assert "GENERATED ALWAYS AS (concat(`a`,_utf8mb4'x\\'y\\\\z')) VIRTUAL" in ddl, ddl
    assert "DEFAULT (concat(_utf8mb4'p\\'q'))" in ddl, ddl
    assert "KEY `ix_q` ((concat(`a`,_utf8mb4'k')))" in ddl, ddl
    assert "CHECK ((`a` in (_utf8mb4'DRAFT',_utf8mb4'PAID')))" in ddl, ddl


def test_a_table_says_what_it_does_not_rebuild_and_brings_its_triggers():
    trg = ("trg_order_audit", "AFTER", "UPDATE", "t_order", 1,
           "begin\n  insert into t_order_audit (order_id) values (new.id);\nend",
           "root@%", "STRICT_TRANS_TABLES")
    ddl = read.ddl(table_catalog(partitioned=1, triggers=[trg]), "app_owner", "t_order")
    assert "-- partitioned: the PARTITION BY clause is not rebuilt" in ddl
    # a trigger body holds ';': the mysql client and Flyway need a DELIMITER
    assert ddl.endswith(
        "\nDELIMITER //\n"
        "-- created under sql_mode=STRICT_TRANS_TABLES\n"
        "CREATE DEFINER=`root`@`%` TRIGGER `app_owner`.`trg_order_audit` AFTER UPDATE ON "
        "`app_owner`.`t_order` FOR EACH ROW\n"
        "begin\n  insert into t_order_audit (order_id) values (new.id);\nend\n//\n"
        "DELIMITER ;"), ddl


def test_a_routine_ddl_carries_its_sql_mode_and_a_delimiter():
    ddl = read.ddl(routine_catalog(), "app_owner", "p_paid")
    assert ddl.startswith("-- rebuilt from information_schema by pythia-mysql")
    assert "\nDELIMITER //\n-- created under sql_mode=STRICT_TRANS_TABLES\n" \
           "CREATE DEFINER=`root`@`%` PROCEDURE `app_owner`.`p_paid`(" in ddl
    assert ddl.endswith("\nend\n//\nDELIMITER ;")


def test_cols_reads_a_table_or_a_view_and_nothing_else():
    cols = ("position", "column_name", "data_type", "nullable", "column_default",
            "extra", "comment")
    conn = CatalogConn({"columns.sql": lambda b: (cols, [
        (1, "id", "bigint", "NO", None, "auto_increment", "")] if b["n"] == "t_order" else [])})
    found = read.columns(conn, "app_owner", "`t_order`")
    assert found[0][1] == "COLUMN_NAME" and found[1] == [(1, "id", "bigint", "NO", None,
                                                          "auto_increment", "")]
    assert read.columns(conn, "app_owner", "p_paid") is None


def test_grep_escapes_like_and_numbers_lines_as_src_does():
    conn = CatalogConn({"grep.sql": (("unit", "type", "definition"), [
        ("f_a", "FUNCTION", "begin\nselect 50% off;\nselect 50% OFF again;\nend"),
        ("v_b", "VIEW", "select 50% off")])})
    cols, rows = read.grep(conn, "app_owner", "50% off", 10)
    # line 1 is the CREATE header src rebuilds: the body starts on line 2
    assert rows == [("f_a", "FUNCTION", 3, "select 50% off;"),
                    ("f_a", "FUNCTION", 4, "select 50% OFF again;"),
                    ("v_b", "VIEW", 2, "select 50% off")], rows
    assert conn.asked[0][1] == {"s": "app_owner", "p": "%50!% off%"}
    assert len(read.grep(conn, "app_owner", "50% off", 1)[1]) == 1


# --- what this account may see ------------------------------------------------------------

def grants(*lines):
    return CatalogConn({"grants.sql": (("Grants for agent@%",), [(g,) for g in lines])})


def test_grants_say_what_mysql_hides_from_this_account():
    hidden = read.hidden_kinds(grants(
        "GRANT USAGE ON *.* TO `agent`@`%`",
        "GRANT SELECT, SHOW VIEW ON `app_owner`.* TO `agent`@`%`"), "app_owner")
    assert set(hidden) == {"routine", "trigger", "event"}
    assert "SHOW_ROUTINE" in hidden["routine"]
    assert "TRIGGER" in hidden["trigger"] and "app_owner" in hidden["trigger"]
    # role privileges are merged into SHOW GRANTS once the role is active
    assert read.hidden_kinds(grants(
        "GRANT SHOW_ROUTINE ON *.* TO `agent`@`%`",
        "GRANT SELECT, SHOW VIEW, EVENT, TRIGGER ON `app_owner`.* TO `agent`@`%`",
        "GRANT `r_reader`@`%` TO `agent`@`%`"), "app_owner") == {}
    # a database pattern, ALL PRIVILEGES and a global SELECT all count
    assert read.hidden_kinds(grants(
        "GRANT SELECT ON *.* TO `agent`@`%`",
        "GRANT ALL PRIVILEGES ON `app\\_%`.* TO `agent`@`%`"), "app_owner") == {}
    assert set(read.hidden_kinds(grants(
        "GRANT ALL PRIVILEGES ON `app\\_%`.* TO `agent`@`%`"), "apple")) == {
        "routine", "trigger", "event"}
    # TRIGGER on one table is not on the schema; column grants do not confuse it
    hidden = read.hidden_kinds(grants(
        "GRANT SHOW_ROUTINE ON *.* TO `agent`@`%`",
        "GRANT SELECT (`id`, `total`), TRIGGER ON `app_owner`.`t_order` TO `agent`@`%`",
        "GRANT EVENT ON `app_owner`.* TO `agent`@`%`"), "app_owner")
    assert set(hidden) == {"trigger"}
    assert read.hidden_kinds(grants(
        "GRANT ALL PRIVILEGES ON *.* TO `root`@`%` WITH GRANT OPTION"), "app_owner") == {}


# --- dependency walks -----------------------------------------------------------------------

ALL_SEEN = ("GRANT SELECT, TRIGGER, EVENT ON *.* TO `agent`@`%`",)


def walk_catalog(grant_lines=ALL_SEEN):
    tree = ("schema_name", "name", "type")
    catalog = {
        ("app_owner", "t_order", "TABLE"): [("app_owner", "v_paid", "VIEW"),
                                            ("app_owner", "t_line", "TABLE"),
                                            ("app_owner", "trg_order_audit", "TRIGGER"),
                                            ("reporting", "v_report", "VIEW")],
        ("app_owner", "f_total", "FUNCTION"): [("app_owner", "v_total", "VIEW")],
    }
    bodies = [
        ("app_owner", "p_paid", "PROCEDURE", "update t_order set status = 'PAID'"),
        ("app_owner", "p_dyn", "PROCEDURE", "set @s = 'select * from `t_order`'"),
        ("app_owner", "p_other", "PROCEDURE", "select * from t_order_line"),
        ("app_owner", "p_elsewhere", "PROCEDURE", "select * from reporting.t_order"),
        ("reporting", "p_cross", "PROCEDURE", "select * from app_owner.t_order"),
        ("reporting", "p_local", "PROCEDURE", "select * from t_order"),
        ("app_owner", "trg_order_audit", "TRIGGER", "insert into t_audit values (new.t_order)"),
        ("app_owner", "f_total", "FUNCTION", "return (select total from t_order)"),
    ]
    return CatalogConn({
        "resolve.sql": resolving(T_ORDER, F_TOTAL, P_PAID, TRG),
        "dependents-catalog.sql": lambda b: (tree, catalog.get((b["s"], b["n"], b["t"]), [])),
        "dependents-text.sql": lambda b: (tree + ("definition",), [
            r for r in bodies if b["p"].strip("%").replace("!_", "_") in r[3].lower()]),
        "grants.sql": (("Grants",), [(g,) for g in grant_lines]),
    })


def test_impact_joins_the_catalog_and_names_found_in_bodies():
    rows, blind = read.dependents(walk_catalog(), "app_owner", "t_order", 1)
    assert rows == [
        (1, "app_owner", "t_line", "TABLE", "catalog"),
        (1, "app_owner", "trg_order_audit", "TRIGGER", "catalog"),
        (1, "app_owner", "v_paid", "VIEW", "catalog"),
        (1, "reporting", "v_report", "VIEW", "catalog"),
        # the body search: a qualifier names the schema, none means the body's own
        (1, "app_owner", "f_total", "FUNCTION", "text"),
        (1, "app_owner", "p_dyn", "PROCEDURE", "text"),
        (1, "app_owner", "p_paid", "PROCEDURE", "text"),
        (1, "reporting", "p_cross", "PROCEDURE", "text")], rows
    assert any("records no dependencies" in b for b in blind)
    assert any("privileges reach" in b for b in blind)
    assert not any("hides" in b for b in blind)


def test_impact_walks_down_and_says_what_this_account_cannot_see():
    rows, blind = read.dependents(walk_catalog(("GRANT SELECT ON `app_owner`.* TO `a`@`%`",)),
                                  "app_owner", "f_total", 2)
    assert rows == [(1, "app_owner", "v_total", "VIEW", "catalog")], rows
    assert any("SHOW_ROUTINE" in b for b in blind)
    assert any("TRIGGER" in b for b in blind) and any("EVENT" in b for b in blind)
    assert read.dependents(walk_catalog(), "app_owner", "nope", 2) is None


def test_deps_reads_the_view_catalog_and_names_in_bodies():
    tree = ("schema_name", "name", "type")
    conn = CatalogConn({
        "resolve.sql": resolving(V_PAID, P_PAID, TRG),
        "dependencies-catalog.sql": lambda b: (tree, {
            "v_paid": [("app_owner", "t_order", "TABLE"), ("app_owner", "f_gone", "UNRESOLVED")],
            "trg_order_audit": [("app_owner", "t_order", "TABLE")]}.get(b["n"], [])),
        "routine.sql": (ROUTINE_COLS, [P_PAID_ROW]),
        "triggers.sql": (TRIGGER_COLS, [("trg_order_audit", "AFTER", "UPDATE", "t_order", 1,
                                         "insert into app_owner.t_audit values (new.id)",
                                         "root@%", "")]),
        "dependencies-text.sql": lambda b: (tree, [
            ("app_owner", "t_order", "TABLE"), ("app_owner", "t_audit", "TABLE"),
            ("reporting", "t_order", "TABLE"), ("app_owner", "p_paid", "PROCEDURE")]),
        "grants.sql": (("Grants",), [(g,) for g in ALL_SEEN])})
    rows, _blind = read.dependencies(conn, "app_owner", "v_paid", 1)
    assert rows == [(1, "app_owner", "f_gone", "UNRESOLVED", "catalog"),
                    (1, "app_owner", "t_order", "TABLE", "catalog")], rows
    rows, blind = read.dependencies(conn, "app_owner", "p_paid", 1)
    # t_order unqualified is the procedure's own schema's; p_paid is itself
    assert rows == [(1, "app_owner", "t_order", "TABLE", "text")], rows
    assert any("read against the names" in b for b in blind)
    rows, _ = read.dependencies(conn, "app_owner", "trg_order_audit", 1)
    assert rows == [(1, "app_owner", "t_order", "TABLE", "catalog"),
                    (1, "app_owner", "t_audit", "TABLE", "text")], rows


# --- errors -------------------------------------------------------------------------------------

def test_errors_name_broken_views_and_say_code_was_not_checked():
    invalid = ("View 'app_owner.v_note' references invalid table(s) or column(s) or "
               "function(s) or definer/invoker of view lack rights to use them")
    conn = CatalogConn({
        "resolve.sql": resolving(T_ORDER, V_PAID, P_PAID, ("app_owner", "v_note", "VIEW")),
        "view-errors.sql": lambda b: (("name", "message"), [
            ("v_note", invalid)] if b["n"] in (None, "v_note") else []),
        "unchecked.sql": (("name", "type"), [("p_late", "PROCEDURE"), ("trg_a", "TRIGGER")]),
        "grants.sql": (("Grants",), [(g,) for g in ALL_SEEN])})
    rows, blind = read.compile_errors(conn, "app_owner", None)
    assert rows == [("v_note", "VIEW", None, None, "error", invalid)], rows
    assert "only when they run" in blind and "p_late" in blind and "trg_a" in blind
    assert read.compile_errors(conn, "app_owner", "v_paid") == ([], None)
    rows, blind = read.compile_errors(conn, "app_owner", "v_note")
    assert len(rows) == 1 and blind is None
    rows, blind = read.compile_errors(conn, "app_owner", "p_paid")
    assert rows == [] and "only when it runs" in blind
    rows, blind = read.compile_errors(conn, "app_owner", "t_order")
    assert rows == [] and "is a table" in blind
    assert read.compile_errors(conn, "app_owner", "nope") is None


def test_errors_are_verified_only_when_nothing_is_hidden_or_unchecked():
    conn = CatalogConn({"view-errors.sql": (("name", "message"), []),
                        "unchecked.sql": (("name", "type"), []),
                        "grants.sql": (("Grants",), [(g,) for g in ALL_SEEN])})
    assert read.compile_errors(conn, "app_owner", None) == ([], None)
    conn.answers["grants.sql"] = (("Grants",), [("GRANT SELECT ON `app_owner`.* TO `a`@`%`",)])
    rows, blind = read.compile_errors(conn, "app_owner", None)
    assert rows == [] and "SHOW_ROUTINE" in blind


# --- the write tier: reading MySQL's SQL, without a database ---------------------------

from pythia_mysql import write  # noqa: E402


def test_the_reader_knows_mysql_quoting():
    text = ("select 'a;b', 'it''s; ok', 'back\\'slash;', \"dq;x\", `semi;colon`, 1--1 # not a cut ;\n"
            "-- nor this ;\n/* nor ; this */ from t;")
    lexed = write.lex(text)
    assert not lexed.unterminated and not lexed.executable
    assert len(lexed.masked) == len(text)
    for hidden in ("a;b", "it", "slash", "dq", "semi", "not a cut", "nor this", "nor ; this"):
        assert hidden not in lexed.masked, hidden
    assert "1--1" in lexed.masked                  # "--" with no space is arithmetic
    assert lexed.cuts == [len(text) - 1]
    assert write.lex("select 'open").unterminated
    assert write.lex("select `open").unterminated
    assert write.lex("/* open").unterminated
    assert write.lex("/*!50000 drop table t */").executable


def test_statements_are_cut_as_the_mysql_client_cuts_them():
    routine = ("create procedure p()\nbegin\n  update t set a = 1;\n  select 1;\nend;")
    assert write.split_script(routine) == [(1, routine[:-1])]
    script = ("insert into t values (1);\n\nDELIMITER //\n"
              "create trigger trg before insert on t for each row\nbegin\n  set new.a = 1;\nend//\n"
              "DELIMITER ;\nupdate t set a = 2 where id = 1;")
    got = write.split_script(script)
    assert [line for line, _ in got] == [1, 4, 9], got
    assert got[1][1].startswith("create trigger") and got[1][1].endswith("end")
    assert got[2][1] == "update t set a = 2 where id = 1"
    assert write.split_script("-- only a comment\n") == []


def classified(text):
    group, why = write.classify(text)
    assert group, (text, why)
    return group


def refusal(text):
    group, why = write.classify(text)
    assert group is None, (text, group)
    return why


def test_classify_sorts_every_statement_or_says_why_not():
    for text, group in (
            ("create view v as select 1", "source"),
            ("CREATE OR REPLACE ALGORITHM=MERGE DEFINER=`root`@`%` SQL SECURITY INVOKER "
             "VIEW app_owner.v AS SELECT 1", "source"),
            ("create definer=current_user procedure p() begin select 1; end", "source"),
            ("create definer='app'@'localhost' function f() returns int deterministic return 1",
             "source"),
            ("create trigger trg before insert on t for each row set new.a = 1", "source"),
            ("create event e on schedule every 1 day do delete from t where id = 0", "source"),
            ("alter view v as select 2", "source"),
            ("alter procedure p comment 'x'", "source"),
            ("alter event e disable", "source"),
            ("create procedure p()\nbegin\n  if 1 then begin select 1; end; end if;\n"
             "  select case when 1 then 2 else 3 end into @x;\n  l: loop leave l; end loop;\n"
             "end;", "source"),
            ("insert into t values (1)", "data_dml"),
            ("replace into t values (1)", "data_dml"),
            ("update t set a = 1 where id = 1", "data_dml"),
            ("delete from t where id = 1", "data_dml"),
            ("alter table t_order comment = 'Orders'", "comments"),
            ("ALTER TABLE `app_owner`.`t_order` COMMENT 'it''s'", "comments"),
            ("alter table t comment = 'x', add column y int", "structural"),
            ("create table t (id int primary key)", "structural"),
            ("alter table t add column x int", "structural"),
            ("drop table t", "structural"),
            ("rename table a to b", "structural"),
            ("truncate table t", "structural"),
            ("create index ix on t (a)", "structural"),
            ("drop procedure p", "structural"),
            ("grant select on app_owner.* to 'u'@'%'", "grants"),
            ("revoke execute on procedure app_owner.p from 'u'@'%'", "grants"),
            ("set @x = 1", "session"),
            ("set names utf8mb4", "session"),
            ("set session sql_mode = 'STRICT_TRANS_TABLES'", "session")):
        assert classified(text) == group, (text, group)
    for text, said in (
            ("start transaction", "owns the transaction"),
            ("begin; update t set a = 1 where id = 1; commit;", "owns the transaction"),
            ("set autocommit = 0", "owns the transaction"),
            ("lock tables t write", "owns the transaction"),
            ("declare x int", "stored program"),
            ("use app_owner", "USE"),
            ("with x as (select 1) update t set a = 1", "CTE"),
            ("select * from t", "apply takes writes"),
            ("show tables", "apply takes writes"),
            ("(select 1)", "apply takes writes"),
            ("call p()", "CALL"),
            ("do sleep(1)", "CALL"),
            ("prepare s from 'select 1'", "CALL"),
            ("load data infile '/x' into table t", "LOAD"),
            ("create temporary table t (id int)", "temporary"),
            ("create database d", "server"),
            ("create user 'u'@'%'", "server"),
            ("set global max_connections = 10", "server"),
            ("flush privileges", "server"),
            ("optimize table t", "maintain"),
            ("create function f returns string soname 'udf.so'", "server"),
            ("grant all on *.* to 'u'@'%'", "*.*"),
            ("grant 'r_reader' to 'u'@'%'", "role"),
            ("create procedure if not exists p() begin end", "IF NOT EXISTS"),
            ("alter event e rename to e2", "RENAME TO"),
            ("/*!50000 drop table t */", "executable comment"),
            ("select 'open", "ends inside a quote"),
            ("insert into t values (1); insert into t values (2)", "2 statements"),
            ("create procedure p() begin select 1; end;\ncreate procedure q() begin select 2; end",
             "Several statements"),
            ("create procedure p() begin select 1; end; drop table t", "Several statements"),
            ("create trigger trg before insert on t for each row set new.a = 1; drop table t",
             "Several statements"),
            ("create event e on schedule every 1 day do delete from t where id = 0; drop table t",
             "Several statements"),
            ("", "no statement"),
            ("frobnicate", "Cannot classify")):
        assert said.lower() in refusal(text).lower(), (text, refusal(text))


def test_parse_object_reads_the_name_as_mysql_would():
    got = write.parse_object("CREATE OR REPLACE ALGORITHM=MERGE DEFINER=`root`@`%` SQL "
                             "SECURITY INVOKER VIEW app_owner.`v_paid` AS SELECT 1", "source")
    assert {k: got[k] for k in ("type", "name", "schema", "verb", "replace", "definer")} == {
        "type": "VIEW", "name": "v_paid", "schema": "app_owner", "verb": "create",
        "replace": True, "definer": "`root`@`%`"}, got
    got = write.parse_object("create procedure p_paid() begin end", "source")
    assert (got["type"], got["name"], got["schema"], got["definer"]) == (
        "PROCEDURE", "p_paid", None, None)
    stmt = "create procedure p_paid() begin end"
    assert stmt[slice(*got["span"])] == "p_paid"
    got = write.parse_object("create trigger app_owner.trg before update on `t_order` for "
                             "each row set new.a = 1", "source")
    assert (got["type"], got["name"], got["table"]) == ("TRIGGER", "trg", "t_order")
    got = write.parse_object("ALTER TABLE `t_order` COMMENT = 'it''s \\'ok\\''", "comments")
    assert (got["name"], got["value"], got["schema"]) == ("t_order", "it's 'ok'", None)
    assert write.parse_object("update t set a = 1", "data_dml") is None


def test_destruction_is_named():
    for text, group, said in (
            ("drop table t", "structural", "DROP"),
            ("truncate table t", "structural", "TRUNCATE"),
            ("rename table a to b", "structural", "old name"),
            ("alter table t drop column a", "structural", "column"),
            ("alter table t modify a bigint", "structural", "rewrites"),
            ("replace into t values (1)", "data_dml", "REPLACE"),
            ("update t set a = 1", "data_dml", "every row"),
            ("delete from t where 1 = 1", "data_dml", "always true"),
            ("revoke select on app_owner.* from 'u'@'%'", "grants", "REVOKE"),
            ("grant select on app_owner.* to 'u'@'%' with grant option", "grants", "pass")):
        assert said in (write.destructive_reason(text, group) or ""), (text, said)
    for text, group in (("create view v as select 1", "source"),
                        ("update t set a = 1 where id = 1", "data_dml"),
                        ("alter table t add column b int", "structural")):
        assert write.destructive_reason(text, group) is None, text


def test_dml_probe_finds_the_rows_or_refuses_to_guess():
    assert write.dml_probe("update app_owner.t_order set status = 'PAID' where id = 1;") == \
        ("app_owner.t_order", "id = 1")
    assert write.dml_probe("delete from `t_order` where status = 'X' -- trailing") == \
        ("`t_order`", "status = 'X'")
    assert write.dml_probe("update t set a = 1") == ("t", None)
    assert write.dml_probe("insert into t values (1)") is None
    for text, said in (("update ignore t set a = 1 where id = 1", "IGNORE"),
                       ("update t set a = 1 where id = 1 limit 1", "LIMIT"),
                       ("update t join u on u.id = t.id set t.a = 1", "target"),
                       ("update t, u set t.a = u.a where t.id = u.id", "target"),
                       ("delete t from t join u on u.id = t.id", "target"),
                       ("delete from t using t, u where t.id = u.id", "target"),
                       ("update t set a = 1 where id in (select id from u)", "subquery"),
                       ("update t set a = 1 where (id = 1", "parentheses"),
                       ("delete from t where id = 1) or (1 = 1", "parentheses")):
        expect_exit(lambda: write.dml_probe(text), said)


class ScriptCursor(CatalogCursor):
    """A query file is answered by name; any other text is the statement
    itself, or a probe built around it, answered by on_text."""

    def __init__(self, conn):
        super().__init__(conn)
        self.rowcount = -1

    def execute(self, sql, params=None):
        if params is not None:
            return super().execute(sql, params)
        self.conn.texts.append(sql)
        cols, rows, count = self.conn.on_text(sql)
        self.description = [(c,) for c in cols] if cols else None
        self._rows, self.rowcount = list(rows), count


class ScriptConn(CatalogConn):
    def __init__(self, answers, on_text=None):
        super().__init__(answers)
        self.texts = []
        self.on_text = on_text or (lambda sql: ((), [], 0))

    def cursor(self):
        return ScriptCursor(self)


def test_the_row_set_is_measured_over_every_column():
    def on_text(sql):
        if sql.lstrip().startswith("-- Purpose: how many"):
            return ("n", "fingerprint"), [(3, 123456789)], 1
        return ("id", "status"), [(i, "DRAFT") for i in range(12)], 12
    conn = ScriptConn({"columns.sql": (("position", "column_name"), [(1, "id"), (2, "status")])},
                      on_text)
    got = write.measure_row_set(conn, "app_owner.t_order", "status = 'DRAFT'")
    assert (got["count"], got["hash"], got["truncated"], len(got["sample"])) == (3, "123456789",
                                                                              True, 10)
    count_sql = conn.texts[0]
    assert "json_array(`id`, `status`)" in count_sql and "from app_owner.t_order" in count_sql
    assert "where (status = 'DRAFT')" in count_sql
    assert conn.asked[0] == ("columns.sql", {"s": "app_owner", "n": "t_order"})
    conn = ScriptConn({"columns.sql": (("position", "column_name"), []),
                       "current-schema.sql": (("s",), [("app_owner",)])}, on_text)
    expect_exit(lambda: write.measure_row_set(conn, "t_gone", None), "no table t_gone")


def test_a_snapshot_is_the_rebuilt_definition_or_a_refusal():
    conn = routine_catalog()
    ident = write.parse_object("create procedure p_paid() begin end", "source")
    snap = write.snapshot(conn, "app_owner", "source", ident)
    assert snap["p_paid"].startswith("CREATE DEFINER=`root`@`%` PROCEDURE `app_owner`.`p_paid`(")
    assert snap["p_paid"].endswith("\nend")
    new = write.parse_object("create procedure p_new() begin end", "source")
    assert write.snapshot(conn, "app_owner", "source", new) == {}
    hidden = list(P_PAID_ROW)
    hidden[11] = None
    conn = routine_catalog({"routine.sql": (ROUTINE_COLS, [tuple(hidden)])})
    expect_exit(lambda: write.snapshot(conn, "app_owner", "source", ident), "SHOW_ROUTINE")
    view = CatalogConn({"resolve.sql": resolving(V_PAID),
                        "view.sql": (VIEW_COLS, [("v_paid", "select 1 AS `1`", "NONE",
                                                  "DEFINER", "root@%")])})
    vid = write.parse_object("create or replace view v_paid as select 2", "source")
    assert write.snapshot(view, "app_owner", "source", vid)["v_paid"].startswith(
        "CREATE OR REPLACE DEFINER=`root`@`%` VIEW")
    comments = CatalogConn({"table-comment.sql": (("comment",), [("Orders",)])})
    cid = write.parse_object("alter table t_order comment = 'All orders'", "comments")
    assert write.snapshot(comments, "app_owner", "comments", cid) == {"t_order": "Orders"}


def test_restore_puts_back_or_drops():
    cid = write.parse_object("alter table t_order comment = 'All orders'", "comments")
    assert write.restore_statement("comments", cid, "it's old", {"schema": "app_owner"}) == \
        "ALTER TABLE `app_owner`.`t_order` COMMENT = 'it''s old'"
    pid = write.parse_object("create procedure p_new() begin end", "source")
    assert write.restore_statement("source", pid, "", {"schema": "app_owner"}) == \
        "DROP PROCEDURE `app_owner`.`p_new`"
    assert write.restore_statement("source", pid, "CREATE ... old", {"schema": "app_owner"}) == \
        "CREATE ... old"


DML = "update app_owner.t_order set status = 'PAID' where id = 1"
INNODB = (("engine", "transactional"), [("InnoDB", "YES")])


def test_a_data_change_runs_twice_first_in_a_savepoint():
    conn = ScriptConn({"table-engine.sql": INNODB, "warnings.sql": (("l", "c", "m"), [])},
                      lambda sql: ((), [], 2))
    out = write.rehearse(conn, "app_owner", "data_dml", DML, None, {}, DriverError)
    assert out["error"] is None and out["rows"] == 2 and out["verified"] is True, out
    assert "predicted" not in out
    assert conn.names() == ["rehearsal-settings.sql", "table-engine.sql", "savepoint.sql",
                            "rollback-to-savepoint.sql", "warnings.sql"]
    assert conn.texts == [DML, DML]
    assert any("twice" in n for n in out["notes"])


def test_a_write_mysql_could_not_roll_back_is_reported_escaped():
    leak = ("Warning", 1196, "Some non-transactional changed tables couldn't be rolled back")
    conn = ScriptConn({"table-engine.sql": INNODB, "warnings.sql": (("l", "c", "m"), [leak])},
                      lambda sql: ((), [], 1))
    out = write.rehearse(conn, "app_owner", "data_dml", DML, None, {}, DriverError)
    assert "MyISAM" in out["escaped"] and out["error"].startswith("1196"), out
    assert conn.texts == [DML]                       # never run a second time
    myisam = ScriptConn({"table-engine.sql": (("engine", "transactional"), [("MyISAM", "NO")])})
    out = write.rehearse(myisam, "app_owner", "data_dml", DML, None, {}, DriverError)
    assert "MyISAM table" in out["error"] and myisam.texts == [], out

    def refuse(sql):
        raise DriverError(1062, "Duplicate entry '1' for key 'PRIMARY'")
    failed = ScriptConn({"table-engine.sql": INNODB}, refuse)
    out = write.rehearse(failed, "app_owner", "data_dml", DML, None, {}, DriverError)
    assert out["error"] == "1062: Duplicate entry '1' for key 'PRIMARY'"
    assert failed.names()[-1] == "rollback-to-savepoint.sql"


VIEW_SQL = "create or replace view app_owner.v_paid as select id from t_order where status = 'PAID'"


def predicting(extra=None, on_text=None):
    answers = {"invalid-views.sql": (("s", "n", "m"), []), "dependents-text.sql": ((), []),
               "current-user.sql": (("account",), [("app_agent@%",)])}
    answers.update(extra or {})
    return ScriptConn(answers, on_text)


def test_a_view_is_predicted_from_its_select_and_the_views_on_top():
    probe = []

    def on_text(sql):
        probe.append(sql)
        return ("id",), [], 0
    conn = predicting({
        "columns.sql": (("position", "column_name"), [(1, "id"), (2, "total")]),
        "views-using.sql": lambda b: (("s", "n"), [("app_owner", "v_paid_big")]
                                      if "`v_paid`.`total`" in b["p"].replace("!_", "_") else []),
        "views-reading.sql": lambda b: (("s", "n"), [("reporting", "v_top")]
                                        if b["n"] == "v_paid_big" else [])}, on_text)
    ident = write.parse_object(VIEW_SQL, "source")
    out = write.rehearse(conn, "app_owner", "source", VIEW_SQL, ident,
                         {"v_paid": "CREATE OR REPLACE ... AS\nselect"}, DriverError)
    assert out["predicted"] is True and out["error"] is None, out
    assert probe == ["select * from (select id from t_order where status = 'PAID') as "
                     "pythia_view_probe limit 0"]
    assert out["broken"] == [
        ("reporting.v_top", "VIEW", "would be marked invalid: it reads "
                                    "app_owner.v_paid_big, which would be invalid"),
        ("v_paid_big", "VIEW", "would be marked invalid: it reads app_owner.v_paid.total, "
                               "which this drops")], out["broken"]
    assert out["prediction"]["broken"] == ["reporting.v_top", "v_paid_big"]
    assert not any("definer" in n for n in out["notes"])     # "..." names no DEFINER
    snap = {"v_paid": "CREATE OR REPLACE DEFINER=`root`@`%` VIEW `app_owner`.`v_paid` AS\nx"}
    out = write.rehearse(conn, "app_owner", "source", VIEW_SQL, ident, snap, DriverError)
    notes = " ".join(out["notes"])
    assert "definer changes from root@% to app_agent@%" in notes and "later" in notes, notes
    plain = VIEW_SQL.replace("create or replace view", "create view")
    out = write.rehearse(conn, "app_owner", "source", plain, write.parse_object(plain, "source"),
                         {"v_paid": "..."}, DriverError)
    assert "CREATE OR REPLACE" in out["error"], out

    def unknown(sql):
        raise DriverError(1054, "Unknown column 'status' in 'where clause'")
    out = write.rehearse(predicting(on_text=unknown), "app_owner", "source", VIEW_SQL, ident, {},
                         DriverError)
    assert out["error"].startswith("1054: Unknown column") and out["predicted"], out


def test_a_routine_is_predicted_not_verified_and_its_replacement_named():
    stmt = "create procedure app_owner.p_paid(in p_id bigint) begin select p_id; end"
    ident = write.parse_object(stmt, "source")
    snap = {"p_paid": "CREATE DEFINER=`root`@`%` PROCEDURE `app_owner`.`p_paid`()\nbegin end"}
    out = write.rehearse(predicting(), "app_owner", "source", stmt, ident, snap, DriverError)
    assert out["predicted"] and out["verified"] is False and "only when it runs" in out["blind"]
    notes = " ".join(out["notes"])
    assert "no CREATE OR REPLACE PROCEDURE" in notes and "scratch name" in notes
    assert "definer changes from root@% to app_agent@%" in notes, notes
    assert "cannot put the old one back" in notes and "SET_ANY_DEFINER" in notes, notes
    may = predicting({"grants.sql": (("g",), [("GRANT SET_ANY_DEFINER ON *.* TO `a`@`%`",)])})
    out = write.rehearse(may, "app_owner", "source", stmt, ident, snap, DriverError)
    assert "cannot put the old one back" not in " ".join(out["notes"])
    trig = "create trigger trg before insert on t_gone for each row set new.a = 1"
    out = write.rehearse(predicting({"table-engine.sql": ((), [])}), "app_owner", "source", trig,
                         write.parse_object(trig, "source"), {}, DriverError)
    assert "no table t_gone" in out["error"], out


def test_ddl_predicts_the_views_it_marks_invalid():
    conn = predicting({
        "views-using.sql": lambda b: (("s", "n"), [("app_owner", "v_note")]
                                      if "`t_order`.`note`" in b["p"].replace("!_", "_") else []),
        "views-reading.sql": lambda b: (("s", "n"), {
            "v_note": [("app_owner", "v_note2")],
            "t_order": [("app_owner", "v_paid")]}.get(b["n"], [])),
        "views-using-function.sql": (("s", "n"), [("app_owner", "v_total")]),
        "dependents-text.sql": lambda b: (("s", "n", "t", "d"), [
            ("app_owner", "p_paid", "PROCEDURE", "update t_order set status = 'PAID'")]
            if "t!_order" in b["p"] else [])})
    stmt = "alter table app_owner.t_order drop column note, add column x int"
    out = write.rehearse(conn, "app_owner", "structural", stmt, None, {}, DriverError)
    assert [b[0] for b in out["broken"]] == ["v_note", "v_note2"] and out["verified"], out
    assert "app_owner.t_order.note, which this drops" in out["broken"][0][2]
    out = write.rehearse(conn, "app_owner", "structural", "drop table t_order restrict", None,
                         {}, DriverError)
    assert [b[0] for b in out["broken"]] == ["v_paid"], out
    assert out["verified"] is False and "p_paid" in out["blind"] and "[text]" in out["blind"]
    out = write.rehearse(conn, "app_owner", "structural", "rename table t_order to t_orders",
                         None, {}, DriverError)
    assert [b[0] for b in out["broken"]] == ["v_paid"], out
    out = write.rehearse(conn, "app_owner", "structural", "drop function f_total", None, {},
                         DriverError)
    assert [b[0] for b in out["broken"]] == ["v_total"], out
    out = write.rehearse(conn, "app_owner", "structural",
                         "alter table t_order add column y int, change note note text", None,
                         {}, DriverError)
    assert out["broken"] == [] and out["verified"], out


def replacing(fail=None):
    """A catalog holding p_paid, and a server that fails the texts named."""
    ran = []

    def on_text(sql):
        ran.append(sql)
        for needle, error in (fail or {}).items():
            if needle in sql:
                raise error
        return (), [], 0
    conn = routine_catalog({"rehearsal-settings.sql": ((), [])})
    conn.__class__ = ScriptConn
    conn.texts, conn.on_text = [], on_text
    return conn, ran


NEW_P = "create procedure app_owner.p_paid(in p_id bigint) begin select p_id; end"


def test_a_routine_is_checked_under_a_scratch_name_then_replaced():
    ident = write.parse_object(NEW_P, "source")
    conn, ran = replacing()
    assert write.execute(conn, "app_owner", "source", NEW_P, ident, DriverError) == {}
    assert ran == [NEW_P.replace("app_owner.p_paid", "app_owner.`p_paid__pythia_check`"),
                   "DROP PROCEDURE IF EXISTS `app_owner`.`p_paid__pythia_check`",
                   "DROP PROCEDURE `app_owner`.`p_paid`", NEW_P], ran
    conn, ran = replacing({"p_paid__pythia_check`(": DriverError(1064, "You have an error")})
    out = write.execute(conn, "app_owner", "source", NEW_P, ident, DriverError)
    assert "1064" in out["error"] and "was not touched" in out["error"] and len(ran) == 1, out


def test_a_refused_replacement_puts_the_old_one_back_or_says_it_could_not():
    ident = write.parse_object(NEW_P, "source")
    refuse = DriverError(1227, "Access denied; you need the SET_USER_ID privilege")
    conn, ran = replacing({"select p_id; end": refuse})
    # the scratch copy holds the same body: let it pass, refuse only the real one
    conn.on_text = (lambda inner: (lambda sql: inner(sql) if "pythia_check" not in sql
                                   else (ran.append(sql), ((), [], 0))[1]))(conn.on_text)
    out = write.execute(conn, "app_owner", "source", NEW_P, ident, DriverError)
    assert "put back" in out["error"] and ran[-1].startswith("CREATE DEFINER=`root`@`%`"), out
    conn, ran = replacing({"select p_id; end": refuse, "CREATE DEFINER": refuse})
    conn.on_text = (lambda inner: (lambda sql: inner(sql) if "pythia_check" not in sql
                                   else (ran.append(sql), ((), [], 0))[1]))(conn.on_text)
    out = write.execute(conn, "app_owner", "source", NEW_P, ident, DriverError)
    assert "does not exist now" in out["escaped"], out
    lost = DriverError(2013, "Lost connection to MySQL server during query")
    conn, ran = replacing({"DROP PROCEDURE `app_owner`": lost})
    out = write.execute(conn, "app_owner", "source", NEW_P, ident, DriverError)
    assert "no answer" in out["escaped"], out


def test_a_trigger_is_dropped_and_created_and_a_new_object_just_created():
    trg = ("create trigger app_owner.trg_order_audit after update on t_order for each row "
           "insert into t_order_audit (order_id) values (new.id)")
    conn = ScriptConn({"resolve.sql": resolving(TRG), "rehearsal-settings.sql": ((), []),
                       "triggers.sql": (TRIGGER_COLS, [
                           ("trg_order_audit", "AFTER", "UPDATE", "t_order", 1, "set @x = 1",
                            "root@%", "")])})
    out = write.execute(conn, "app_owner", "source", trg, write.parse_object(trg, "source"),
                        DriverError)
    assert out == {} and conn.texts == ["DROP TRIGGER `app_owner`.`trg_order_audit`", trg]
    fresh = ScriptConn({"resolve.sql": resolving(), "rehearsal-settings.sql": ((), [])})
    out = write.execute(fresh, "app_owner", "structural", "drop table t", None, DriverError)
    assert out == {} and fresh.texts == ["drop table t"]


def test_what_landed_is_read_back_and_compared_with_the_prediction():
    conn = ScriptConn({"invalid-views.sql": (("s", "n", "m"), [
        ("app_owner", "v_old", "x"), ("app_owner", "v_note", "1356 v_note"),
        ("reporting", "v_extra", "1356 v_extra")])})
    outcome = {"prediction": {"invalid_before": {"app_owner.v_old": "x"},
                              "broken": ["v_gone", "v_note"]}}
    got = write.verify_written(conn, "app_owner", "structural", "drop table t", None, outcome,
                               DriverError)
    assert [b[0] for b in got["broken"]] == ["reporting.v_extra", "v_note"], got
    assert got["differs"] == [
        "reporting.v_extra is marked invalid now; the prediction did not say so",
        "v_gone was predicted invalid, and MySQL did not mark it"], got
    view = write.parse_object("create or replace view v_note as select 1", "source")
    conn.answers.update({"resolve.sql": resolving(("app_owner", "v_note", "VIEW")),
                         "view.sql": (VIEW_COLS, [("v_note", "select 1", "NONE", "DEFINER",
                                                   "root@%")])})
    got = write.verify_written(conn, "app_owner", "source", "create or replace view v_note as "
                               "select 1", view, {"prediction": {"invalid_before": {},
                                                                 "broken": []}}, DriverError)
    assert [o[0] for o in got["own_errors"]] == ["v_note"], got
    cid = write.parse_object("alter table t_order comment = 'All orders'", "comments")
    conn = ScriptConn({"invalid-views.sql": ((), []),
                       "table-comment.sql": (("comment",), [("Orders",)])})
    got = write.verify_written(conn, "app_owner", "comments", "", cid, {}, DriverError)
    assert "reads back as 'Orders'" in got["differs"][0], got
    conn = routine_catalog({"invalid-views.sql": ((), [])})
    pid = write.parse_object(NEW_P, "source")
    got = write.verify_written(conn, "app_owner", "source", NEW_P, pid, {}, DriverError)
    assert "not the one written" in got["differs"][0], got


def test_an_account_that_can_do_far_more_is_named():
    def warn(*lines):
        return write.privilege_warning(CatalogConn({
            "grants.sql": (("g",), [(ln,) for ln in lines]),
            "current-user.sql": (("a",), [("app_agent@%",)])}), "app_owner")
    assert "every privilege" in warn("GRANT ALL PRIVILEGES ON *.* TO `app_agent`@`%`")
    assert "any account" in warn("GRANT SYSTEM_USER,SET_USER_ID ON *.* TO `app_agent`@`%`")
    assert warn("GRANT SELECT, INSERT ON `app_owner`.* TO `app_agent`@`%`") is None


def test_the_engine_answers_the_write_and_predict_tiers():
    assert engine_problems(MySqlEngine(), tiers=("connect", "read", "write", "predict")) == []
    assert set(MySqlEngine.rollback_notes) == {"source", "comments", "data_dml", "structural",
                                                "grants", "session"}


# --- the release's paperwork ---------------------------------------------------------------------

def test_the_version_has_its_changelog_entry():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(rf"^## {re.escape(pythia_mysql.__version__)} ", text, re.M), \
        f"CHANGELOG.md has no entry for {pythia_mysql.__version__}"


def test_it_asks_for_the_core_of_its_release_series():
    # 0.x: a minor version of pythia-core may change the engine contract
    assert re.search(r'"pythia-core>=0\.1\.\d+,<0\.2"', pyproject()), \
        "pythia-core is asked for outside its 0.1 series"


def readme_shape(text):
    """What the two READMEs must share: the heading levels in order, and
    every fenced block, byte for byte — the commands do not translate."""
    levels = [len(m.group(1)) for m in re.finditer(r"^(#+) ", text, re.M)]
    blocks = re.findall(r"^```[^\n]*\n(.*?)^```", text, re.M | re.S)
    return levels, blocks


def test_the_vietnamese_readme_matches_the_english_one():
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    vi = (ROOT / "README.vi.md").read_text(encoding="utf-8")
    assert readme_shape(vi) == readme_shape(en), "README.vi.md has drifted from README.md"
    assert re.search(r"\[Tiếng Việt\]\([^)]*README\.vi\.md\)", en), "README.md links no translation"
    assert re.search(r"\[English\]\([^)]*README\.md\)", vi), "README.vi.md links no original"


def test_the_package_says_what_it_is_on_pypi():
    text = pyproject()
    if re.match(r"0\.\d+\.\d+$", pythia_mysql.__version__):
        assert '"Development Status :: 3 - Alpha"' in text
    for needle in ('readme = "README.md"', '"Programming Language :: Python :: 3.9"',
                   '"Programming Language :: Python :: 3.13"', "Changelog = "):
        assert needle in text, needle


def main():
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except (Exception, SystemExit) as e:  # noqa: BLE001 — keep going
                failed += 1
                print(f"FAIL {name}: {e!r}")
    if failed:
        sys.exit(f"{failed} test(s) failed")
    print("OK")


if __name__ == "__main__":
    main()
