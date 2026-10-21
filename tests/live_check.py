#!/usr/bin/env python3
"""pythia-mysql against a real MySQL — a disposable one only.

1. Always (when PYTHIA_MYSQL_LIVE_HOST is set): connect and `check`.
2. With PYTHIA_MYSQL_LIVE_DISPOSABLE=1 only: the databases app_owner,
   reporting and pythia_copy are dropped and created,
   tests/fixtures/app_owner.sql is loaded, an account pythia_agent is made
   (SELECT and SHOW VIEW on both schemas, SHOW_ROUTINE), and every read
   command runs through the command line as that account — first without
   TRIGGER and EVENT, which MySQL hides triggers and events behind, then
   with them. A read session must refuse DDL.
3. Every object's `ddl` is run into pythia_copy, and the copy must match the
   original in information_schema and in SHOW CREATE TABLE.

Never point this at a shared server: it creates an account and drops
databases. Skipped unless PYTHIA_MYSQL_LIVE_HOST is set:

    PYTHIA_MYSQL_LIVE_HOST=127.0.0.1 PYTHIA_MYSQL_LIVE_PORT=3306 \\
    PYTHIA_MYSQL_LIVE_USER=root PYTHIA_MYSQL_LIVE_PASSWORD=... \\
    PYTHIA_MYSQL_LIVE_DISPOSABLE=1 python tests/live_check.py
"""
import contextlib
import io
import json
import os
import pathlib
import re
import secrets
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
for candidate in (os.environ.get("PYTHIA_CORE_SRC"), ROOT.parent / "pythia-core" / "src"):
    if candidate and pathlib.Path(candidate).is_dir():
        sys.path.insert(1, str(candidate))
        break

AGENT = "pythia_agent"
COPY = "pythia_copy"


def ok(what):
    print(f"PASS {what}")


def admin_entry():
    env = os.environ
    return {"host": env["PYTHIA_MYSQL_LIVE_HOST"],
            "port": int(env.get("PYTHIA_MYSQL_LIVE_PORT") or 3306),
            "user": env.get("PYTHIA_MYSQL_LIVE_USER") or "root",
            "password": env["PYTHIA_MYSQL_LIVE_PASSWORD"]}


@contextlib.contextmanager
def admin(entry, database=None):
    import pymysql
    conn = pymysql.connect(host=entry["host"], port=entry["port"], user=entry["user"],
                           password=entry["password"], database=database,
                           autocommit=True, charset="utf8mb4")
    try:
        yield conn
    finally:
        conn.close()


def statements(script):
    """The statements of a script as the mysql client cuts them: at the
    current delimiter, which a DELIMITER line changes."""
    delim, buf, out = ";", [], []
    for line in script.splitlines():
        m = re.match(r"\s*DELIMITER\s+(\S+)\s*$", line, re.I)
        if m:
            delim = m.group(1)
            continue
        buf.append(line)
        if line.rstrip().endswith(delim):
            text = "\n".join(buf).rstrip()[:-len(delim)].strip()
            buf = []
            if any(t.strip() and not t.strip().startswith("--") for t in text.splitlines()):
                out.append(text)
    return out


def run_script(entry, script, database=None):
    with admin(entry, database) as conn:
        cur = conn.cursor()
        for stmt in statements(script):
            cur.execute(stmt)


def rows(entry, sql, args=None):
    with admin(entry) as conn:
        cur = conn.cursor()
        cur.execute(sql, args)
        return cur.fetchall()


class Project:
    """A project folder whose connection is one account."""

    def __init__(self, entry):
        self.td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.td.name)
        state = self.root / ".pythia" / "mysql"
        state.mkdir(parents=True)
        path = state / "connections.json"
        path.write_text(json.dumps({"live": entry}), encoding="utf-8")
        if os.name == "posix":
            os.chmod(path, 0o600)

    def run(self, *argv):
        """(exit code, stdout, the refusal message or '')"""
        from pythia_mysql import cli
        keep = os.getcwd()
        os.chdir(self.root)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(io.StringIO()):
                code, why = cli.main(list(argv)) or 0, ""
        except SystemExit as e:
            code, why = (e.code, "") if isinstance(e.code, int) else (1, str(e))
        finally:
            os.chdir(keep)
        return code, out.getvalue(), why

    def json(self, *argv):
        code, out, why = self.run(*argv, "--json")
        assert code == 0, (argv, why, out)
        return json.loads(out.strip().splitlines()[-1])

    def text(self, *argv):
        code, out, why = self.run(*argv)
        assert code == 0, (argv, why, out)
        return out


def check_connect(entry):
    p = Project(dict(entry, database="mysql"))
    doc = p.json("check")
    server = {r["ITEM"]: r["VALUE"] for r in doc["rows"]}["server"]
    assert server.startswith("MySQL ") and "database mysql" in server, server
    assert doc["below_floor"] is None, doc["below_floor"]    # CI runs 8.4 and up
    ok(f"check: {server}, at or above the floor")


def load_fixture(entry):
    run_script(entry, (ROOT / "tests" / "fixtures" / "app_owner.sql").read_text(encoding="utf-8"))
    password = "Agent#" + secrets.token_hex(8)
    run_script(entry, f"""
drop user if exists '{AGENT}'@'%';
create user '{AGENT}'@'%' identified by '{password}';
grant select, show view on app_owner.* to '{AGENT}'@'%';
grant select, show view on reporting.* to '{AGENT}'@'%';
grant show_routine on *.* to '{AGENT}'@'%';
""")
    return {"host": entry["host"], "port": entry["port"], "database": "app_owner",
            "user": AGENT, "password": password}


def tree(doc):
    return [(r["LEVEL"], r["SCHEMA"], r["NAME"], r["TYPE"], r["HOW"]) for r in doc["rows"]]


def check_reads_hidden(agent):
    p = Project(agent)
    doc = p.json("check")
    assert doc["schema_drift"] is False, doc
    ok("check: the agent lands unqualified names in app_owner")

    doc = p.json("impact", "t_order")
    names = {(r[1], r[2]) for r in tree(doc)}
    assert ("app_owner", "trg_order_audit") not in names, names
    assert any("no TRIGGER privilege on app_owner" in b for b in doc["blind_spots"]), doc
    assert any("no EVENT privilege" in b for b in doc["blind_spots"]), doc
    ok("impact: what MySQL hides from the account is said, not passed over")

    doc = p.json("errors")
    assert "no TRIGGER privilege" in doc["blind_spot"] and doc["verified"] is False, doc
    ok("errors: never verified while triggers are hidden")


def check_reads(agent):
    p = Project(agent)
    names = [r["NAME"] for r in p.json("ls", "t_order%")["rows"]]
    assert names == ["t_order", "t_order_audit", "t_order_line"], names
    names = {(r["NAME"], r["TYPE"]) for r in p.json("ls", "%")["rows"]}
    assert {("trg_order_audit", "TRIGGER"), ("ev_purge_audit", "EVENT"),
            ("p_order_paid", "PROCEDURE"), ("f_order_total", "FUNCTION"),
            ("v_total", "VIEW")} <= names, names
    ok("ls: tables, views, routines, triggers and events by LIKE pattern")

    rows_ = p.json("src", "f_order_total")["rows"]
    assert rows_[0]["LINE"] == 1 and rows_[0]["TEXT"].startswith(
        "CREATE DEFINER=`root`@`%` FUNCTION `app_owner`.`f_order_total`("), rows_[0]
    assert rows_[1]["TEXT"] == "begin" and rows_[2]["TEXT"].strip() == "-- the total of one order"
    ok("src: the header rebuilt on line 1, the body as written below it")

    hits = p.json("grep", "TOTAL OF ONE")["rows"]
    assert [(h["NAME"], h["LINE"]) for h in hits] == [("f_order_total", 3)], hits
    ok("grep: in any case, numbered as src numbers")

    cols = [(r["COLUMN_NAME"], r["DATA_TYPE"]) for r in p.json("cols", "t_order")["rows"]]
    assert cols[:3] == [("id", "bigint unsigned"), ("status", "varchar(10)"),
                        ("total", "decimal(12,2)")], cols
    ok("cols: a table's columns as MySQL types them")

    doc = p.json("impact", "t_order")
    found = tree(doc)
    for row in [(1, "app_owner", "t_order_line", "TABLE", "catalog"),
                (1, "app_owner", "trg_order_audit", "TRIGGER", "catalog"),
                (1, "app_owner", "v_order_summary", "VIEW", "catalog"),
                (1, "app_owner", "v_total", "VIEW", "catalog"),
                (1, "reporting", "v_paid", "VIEW", "catalog"),
                (1, "app_owner", "f_order_total", "FUNCTION", "text"),
                (1, "app_owner", "p_order_count", "PROCEDURE", "text"),
                (1, "app_owner", "p_order_paid", "PROCEDURE", "text")]:
        assert row in found, (row, found)
    assert (2, "app_owner", "v_total", "VIEW", "catalog") in found, found
    assert doc["summary"]["other_schemas"] == ["reporting.v_paid"], doc["summary"]
    assert doc["summary"]["needs_review"] is True
    assert not any("privilege on app_owner" in b for b in doc["blind_spots"]), doc
    ok("impact: views, a foreign key, a trigger, and bodies that name it ([text])")

    found = tree(p.json("deps", "trg_order_audit"))
    assert found == [(1, "app_owner", "t_order", "TABLE", "catalog"),
                     (1, "app_owner", "t_order_audit", "TABLE", "text")], found
    found = tree(p.json("deps", "v_total", "--depth", "1"))
    assert found == [(1, "app_owner", "f_order_total", "FUNCTION", "catalog"),
                     (1, "app_owner", "t_order", "TABLE", "catalog")], found
    ok("deps: a view's catalog, a trigger's table and the names in its body")

    doc = p.json("errors")
    assert [(r["NAME"], r["TYPE"]) for r in doc["rows"]] == [("v_note", "VIEW")], doc
    assert "p_broken" in doc["blind_spot"] and doc["verified"] is False, doc
    assert p.json("errors", "v_total")["verified"] is True
    doc = p.json("errors", "p_broken")
    assert doc["rows"] == [] and "only when it runs" in doc["blind_spot"], doc
    ok("errors: the broken view found, routines named unchecked")

    ddl = p.text("ddl", "t_order")
    assert "CREATE TABLE `app_owner`.`t_order` (" in ddl and "DELIMITER //" in ddl, ddl
    ok("ddl: a table with its trigger")


def check_read_session_refuses_writes(entry):
    from pythia_mysql.engine import MySqlEngine
    e = MySqlEngine()
    conn = e.session(e.connect(dict(entry, database="app_owner")), True)
    try:
        for stmt in ("create table t_should_not_exist (id int)",
                     "insert into t_order (status, total) values ('DRAFT', 1)",
                     "drop view v_order_summary"):
            try:
                conn.cursor().execute(stmt)
            except e.driver_errors() as exc:
                assert exc.args[0] == 1792, exc
            else:
                raise AssertionError(f"a read session ran: {stmt}")
    finally:
        e.close(conn)
    ok("a read session refuses DDL and DML alike (1792)")


def normalized_create(entry, schema, table):
    text = rows(entry, f"show create table `{schema}`.`{table}`")[0][1]
    text = re.sub(r" AUTO_INCREMENT=\d+", "", text)
    return sorted(line.strip().rstrip(",") for line in text.splitlines())


CATALOG = {
    "columns": ("select table_name, column_name, ordinal_position, column_default, "
                "is_nullable, column_type, character_set_name, collation_name, extra, "
                "generation_expression, column_comment from information_schema.columns "
                "where table_schema = %s order by 1, 3"),
    "routines": ("select routine_name, routine_type, dtd_identifier, routine_definition, "
                 "is_deterministic, sql_data_access, security_type, routine_comment "
                 "from information_schema.routines where routine_schema = %s order by 1, 2"),
    "parameters": ("select specific_name, ordinal_position, parameter_mode, parameter_name, "
                   "dtd_identifier from information_schema.parameters "
                   "where specific_schema = %s order by 1, 2"),
    "views": ("select table_name, view_definition, check_option, security_type "
              "from information_schema.views where table_schema = %s order by 1"),
    "triggers": ("select trigger_name, event_manipulation, action_timing, action_order, "
                 "event_object_table, action_statement from information_schema.triggers "
                 "where trigger_schema = %s order by 1"),
    "events": ("select event_name, event_type, interval_value, interval_field, starts, "
               "on_completion, status, event_comment, event_definition "
               "from information_schema.events where event_schema = %s order by 1"),
}


def catalog_of(entry, schema):
    out = {}
    for what, sql in CATALOG.items():
        out[what] = [tuple(str(v).replace(f"`{schema}`", "`S`").replace(f"{schema}.", "S.")
                           if isinstance(v, str) else v for v in r)
                     for r in rows(entry, sql, (schema,))]
    return out


def check_ddl_round_trip(entry, agent):
    p = Project(agent)
    run_script(entry, f"drop database if exists {COPY};\ncreate database {COPY};")
    objects = ["t_order", "t_order_line", "t_order_audit", "v_order_summary",
               "f_order_total", "v_total", "p_order_paid", "p_order_count", "p_broken",
               "ev_purge_audit"]
    for name in objects:
        script = p.text("ddl", name).replace("`app_owner`.", f"`{COPY}`.") \
                                    .replace("app_owner.", f"{COPY}.")
        run_script(entry, script, COPY)
    for table in ("t_order", "t_order_line", "t_order_audit"):
        assert normalized_create(entry, "app_owner", table) == \
            normalized_create(entry, COPY, table), table
    ok("ddl: every table rebuilt to the same SHOW CREATE TABLE")
    original, copy = catalog_of(entry, "app_owner"), catalog_of(entry, COPY)
    for what in CATALOG:
        theirs = [r for r in original[what] if not (what in ("columns", "views")
                                                    and r[0] == "v_note")]
        assert theirs == copy[what], (what, theirs, copy[what])
    ok("ddl: columns, routines, parameters, views, triggers and events rebuilt alike")


def main():
    if not os.environ.get("PYTHIA_MYSQL_LIVE_HOST"):
        print("SKIP live check: PYTHIA_MYSQL_LIVE_HOST is not set")
        return
    entry = admin_entry()
    check_connect(entry)
    if os.environ.get("PYTHIA_MYSQL_LIVE_DISPOSABLE") != "1":
        print("SKIP the rest: PYTHIA_MYSQL_LIVE_DISPOSABLE=1 is not set")
        return
    agent = load_fixture(entry)
    check_reads_hidden(agent)
    run_script(entry, f"grant trigger, event on app_owner.* to '{AGENT}'@'%';")
    check_reads(agent)
    check_read_session_refuses_writes(entry)
    check_ddl_round_trip(entry, agent)
    print("OK")


if __name__ == "__main__":
    main()
