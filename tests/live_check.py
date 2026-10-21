#!/usr/bin/env python3
"""pythia-mysql against a real MySQL or MariaDB — a disposable one only.

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
4. The fixture is loaded again, the account may write, and every write path
   runs through the gate: a procedure created, replaced (checked under a
   scratch name), refused and restored; a view replaced that breaks the
   view on top, as predicted (exit 3), and restored; rows that move, rows
   written, triggers fired; a trigger writing to MyISAM inside a preview
   (WRITTEN?, exit 3); a dropped column and a rename that break views as
   predicted, and a prediction that moved after approval; a table comment;
   a session setting; an account that can do far more. Then a data release
   through `deploy` (and DDL in one refused), a lint error in a real
   preview, and a write under an autopilot lease.

On MariaDB (Phase 11) everything runs on tests/fixtures/app_owner_mariadb.sql
— a sequence, a package and a column-level check besides — with the
privilege MariaDB shows routines behind (SHOW CREATE ROUTINE from 11.3,
SELECT on mysql.proc before). The writes are the same, but where MariaDB
differs: a routine replaced in one step, SET USER for another definer, views
read back with CHECK TABLE, and a sequence written and a package refused.

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
MARIADB = None          # (major, minor) of the MariaDB under test; None on MySQL


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

    def file(self, name, text):
        (self.root / name).write_text(text, encoding="utf-8")
        return name

    def preview(self, name, text):
        return self.json("apply", self.file(name, text))

    def approve(self, token):
        """The developer's own act, at their own console."""
        from pythia_core import human
        human.FORCE_CONSOLE = True
        try:
            code, _, why = self.run("approve", token)
            assert code == 0, why
        finally:
            human.FORCE_CONSOLE = False

    def confirm(self, *argv):
        """(exit code, the last JSON line or None, the refusal)"""
        code, out, why = self.run(*argv, "--json")
        lines = out.strip().splitlines()
        return code, (json.loads(lines[-1]) if lines and lines[-1].startswith("{")
                      else None), why

    def write(self, name, text):
        """Preview, approve, confirm: (exit code, result, refusal)."""
        doc = self.preview(name, text)
        self.approve(doc["token"])
        return self.confirm("apply", name, "--confirm", doc["token"])

    def restore(self, result):
        eid = result["restore"].split()[-1]
        doc = self.json("journal", "restore", eid)
        self.approve(doc["token"])
        return self.confirm("journal", "restore", eid, "--confirm", doc["token"])

    def policy(self, **groups):
        (self.root / ".pythia" / "mysql" / "policy.json").write_text(
            json.dumps(groups), encoding="utf-8")


def which_server(entry):
    global MARIADB
    version = rows(entry, "select version()")[0][0]
    m = re.match(r"(\d+)\.(\d+)", version)
    MARIADB = (int(m.group(1)), int(m.group(2))) if "mariadb" in version.lower() else None


def check_connect(entry):
    p = Project(dict(entry, database="mysql"))
    doc = p.json("check")
    server = {r["ITEM"]: r["VALUE"] for r in doc["rows"]}["server"]
    name = "MariaDB" if MARIADB else "MySQL"
    assert server.startswith(name + " ") and "database mysql" in server, server
    assert doc["below_floor"] is None, doc["below_floor"]    # CI runs 8.4 and 10.11 up
    ok(f"check: {server}, at or above the floor")


def load_fixture(entry):
    fixture = "app_owner_mariadb.sql" if MARIADB else "app_owner.sql"
    run_script(entry, (ROOT / "tests" / "fixtures" / fixture).read_text(encoding="utf-8"))
    password = "Agent#" + secrets.token_hex(8)
    # what lets an account read routines it did not define
    routines = ("show_routine on *.*" if not MARIADB else
                "show create routine on *.*" if MARIADB >= (11, 3) else "select on mysql.proc")
    run_script(entry, f"""
drop user if exists '{AGENT}'@'%';
create user '{AGENT}'@'%' identified by '{password}';
grant select, show view on app_owner.* to '{AGENT}'@'%';
grant select, show view on reporting.* to '{AGENT}'@'%';
grant {routines} to '{AGENT}'@'%';
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
    if MARIADB:
        assert {("s_order", "SEQUENCE"), ("pkg_order", "PACKAGE"),
                ("pkg_order", "PACKAGE BODY")} <= names, names
    ok("ls: tables, views, routines, triggers and events by LIKE pattern"
       + (", and MariaDB's sequences and packages" if MARIADB else ""))

    rows_ = p.json("src", "f_order_total")["rows"]
    assert rows_[0]["LINE"] == 1 and rows_[0]["TEXT"].startswith(
        "CREATE DEFINER=`root`@`%` FUNCTION `app_owner`.`f_order_total`("), rows_[0]
    assert rows_[1]["TEXT"] == "begin" and rows_[2]["TEXT"].strip() == "-- the total of one order"
    ok("src: the header rebuilt on line 1, the body as written below it")

    hits = p.json("grep", "TOTAL OF ONE")["rows"]
    assert [(h["NAME"], h["LINE"]) for h in hits] == [("f_order_total", 3)], hits
    ok("grep: in any case, numbered as src numbers")

    cols = [(r["COLUMN_NAME"], r["DATA_TYPE"]) for r in p.json("cols", "t_order")["rows"]]
    assert cols[:3] == [("id", "bigint(20) unsigned" if MARIADB else "bigint unsigned"),
                        ("status", "varchar(10)"), ("total", "decimal(12,2)")], cols
    ok("cols: a table's columns as the server types them")

    # MariaDB records no view usage: its views are read in their definitions
    view_how = "definition" if MARIADB else "catalog"
    doc = p.json("impact", "t_order")
    found = tree(doc)
    for row in [(1, "app_owner", "t_order_line", "TABLE", "catalog"),
                (1, "app_owner", "trg_order_audit", "TRIGGER", "catalog"),
                (1, "app_owner", "v_order_summary", "VIEW", view_how),
                (1, "app_owner", "v_total", "VIEW", view_how),
                (1, "reporting", "v_paid", "VIEW", view_how),
                (1, "app_owner", "f_order_total", "FUNCTION", "text"),
                (1, "app_owner", "p_order_count", "PROCEDURE", "text"),
                (1, "app_owner", "p_order_paid", "PROCEDURE", "text")]:
        assert row in found, (row, found)
    assert (2, "app_owner", "v_total", "VIEW", view_how) in found, found
    if MARIADB:
        assert (1, "app_owner", "pkg_order", "PACKAGE BODY", "text") in found, found
    assert doc["summary"]["other_schemas"] == ["reporting.v_paid"], doc["summary"]
    assert doc["summary"]["needs_review"] is True
    assert not any("privilege on app_owner" in b for b in doc["blind_spots"]), doc
    ok("impact: views, a foreign key, a trigger, and bodies that name it ([text])")

    found = tree(p.json("deps", "trg_order_audit"))
    assert found == [(1, "app_owner", "t_order", "TABLE", "catalog"),
                     (1, "app_owner", "t_order_audit", "TABLE", "text")], found
    found = tree(p.json("deps", "v_total", "--depth", "1"))
    assert found == [(1, "app_owner", "f_order_total", "FUNCTION", view_how),
                     (1, "app_owner", "t_order", "TABLE", view_how)], found
    ok("deps: a view's " + ("definition" if MARIADB else "catalog")
       + ", a trigger's table and the names in its body")
    if MARIADB:
        found = tree(p.json("impact", "s_order"))
        assert found == [(1, "app_owner", "p_order_number", "PROCEDURE", "text")], found
        src = p.json("src", "pkg_order")["rows"]
        assert src[0]["TEXT"] == ("CREATE DEFINER=`root`@`%` PACKAGE "
                                  "`app_owner`.`pkg_order`"), src[0]
        ok("impact of a sequence; src of a package and its body")

    doc = p.json("errors")
    assert [(r["NAME"], r["TYPE"]) for r in doc["rows"]] == [("v_note", "VIEW")], doc
    assert "p_broken" in doc["blind_spot"] and doc["verified"] is False, doc
    if MARIADB:                  # CHECK TABLE names the cause, not just the view
        assert "app_owner.t_note" in doc["rows"][0]["MESSAGE"], doc["rows"]
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
    if MARIADB:
        objects += ["p_order_number", "s_order", "pkg_order"]
    for name in objects:
        script = p.text("ddl", name).replace("`app_owner`.", f"`{COPY}`.") \
                                    .replace("app_owner.", f"{COPY}.")
        run_script(entry, script, COPY)
    for table in ("t_order", "t_order_line", "t_order_audit"):
        assert normalized_create(entry, "app_owner", table) == \
            normalized_create(entry, COPY, table), table
    if MARIADB:
        assert rows(entry, "show create sequence app_owner.s_order")[0][1] == \
            rows(entry, f"show create sequence {COPY}.s_order")[0][1]
    ok("ddl: every table rebuilt to the same SHOW CREATE TABLE"
       + (", and the sequence to the same SHOW CREATE SEQUENCE" if MARIADB else ""))
    original, copy = catalog_of(entry, "app_owner"), catalog_of(entry, COPY)
    for what in CATALOG:
        theirs = [r for r in original[what] if not (what in ("columns", "views")
                                                    and r[0] == "v_note")]
        assert theirs == copy[what], (what, theirs, copy[what])
    ok("ddl: columns, routines, parameters, views, triggers and events rebuilt alike")


# --- the write path, through the gate ----------------------------------------------------

RELEASE = """-- a data release: three statements, one transaction
insert into app_owner.t_order (status, total) values ('DRAFT', 7);
update app_owner.t_order set total = total + 100 where id = 1;

delete from app_owner.t_order_line where order_id = 1 and qty = 99;
"""

def scalar(entry, sql):
    found = rows(entry, sql)
    return found[0][0] if found else None


def body(entry, name):
    return scalar(entry, "select routine_definition from information_schema.routines "
                         f"where routine_schema = 'app_owner' and routine_name = '{name}'")


def view_ok(entry, schema, name):
    if MARIADB:                  # it marks no view invalid: CHECK TABLE opens it
        return rows(entry, f"check table `{schema}`.`{name}`")[-1][3] == "OK"
    return scalar(entry, "select table_comment from information_schema.tables where "
                         f"table_schema = '{schema}' and table_name = '{name}'") == "VIEW"


def check_writes(entry):
    from pythia_core import human
    human.FORCE_CONSOLE = False             # no person here unless one approves
    agent = load_fixture(entry)
    run_script(entry, f"""
grant select, insert, update, delete, create, alter, drop, index, references, create view,
      show view, create routine, alter routine, execute, trigger, event on app_owner.* to '{AGENT}'@'%';
grant select, show view on reporting.* to '{AGENT}'@'%';
""")
    p = Project(agent)
    p.policy(structural="confirm", data_dml="confirm")
    try:
        _routines(entry, p)
        _views(entry, p)
        _rows(entry, p)
        _leaks(entry, p)
        _breakage(entry, p)
        _comments_and_session(entry, p)
        _release(entry, p)
        _lint(entry, p)
        _lease(entry, p)
        if MARIADB:
            _mariadb(entry, p)
    finally:
        human.FORCE_CONSOLE = None


P_NEW = """create procedure app_owner.p_new(in p_id bigint unsigned)
begin
    select status from app_owner.t_order where id = p_id;
end"""


def _routines(entry, p):
    doc = p.preview("p_new.sql", P_NEW)
    assert doc["created"] is True and doc["rehearsal"]["predicted"] is True, doc
    assert doc["rehearsal"]["verified"] is False, doc
    assert body(entry, "p_new") is None
    ok("apply: a new procedure predicted — nothing ran, NOT VERIFIED")
    code, res, why = p.write("p_new.sql", P_NEW)
    assert code == 0 and res["restore_is_drop"] is True, (code, why, res)
    assert "select status" in body(entry, "p_new")
    ok("approved and confirmed: created once; its undo is a DROP")

    newer = P_NEW.replace("select status", "select status, total")
    doc = p.preview("p_new.sql", newer)
    notes = " ".join(doc["rehearsal"]["notes"])
    replaces = "replaces it in one step" if MARIADB else "no CREATE OR REPLACE PROCEDURE"
    assert doc["created"] is False and replaces in notes, doc
    p.approve(doc["token"])
    code, res, why = p.confirm("apply", "p_new.sql", "--confirm", doc["token"])
    assert code == 0, (code, why, res)
    assert "select status, total" in body(entry, "p_new")
    assert body(entry, "p_new__pythia_check") is None
    ok("a CREATE for a procedure that exists replaces it, "
       + ("in one step (MariaDB's CREATE OR REPLACE)" if MARIADB
          else "checked under a scratch name"))

    code, _, why = p.write("bad.sql", P_NEW.replace("select status", "selec status"))
    said = "untouched" if MARIADB else "scratch name"
    assert code == 1 and said in why and "1064" in why, (code, why)
    assert "select status, total" in body(entry, "p_new")
    ok("a replacement the server refuses costs nothing: the procedure is untouched")

    code, res2, why = p.restore(res)
    assert code == 0, (code, why, res2)
    assert "select status from" in body(entry, "p_new")
    ok("journal restore: previewed, approved, written — the old body is back")

    doc = p.preview("f_cents.sql", """create function app_owner.f_order_total(p_id bigint unsigned)
returns decimal(14,2) reads sql data
return (select total * 100 from app_owner.t_order where id = p_id)""")
    notes = " ".join(doc["rehearsal"]["notes"])
    assert f"definer changes from root@% to {AGENT}@%" in notes, notes
    assert "cannot put the old one back" in notes and "v_total call" in notes, notes
    ok("replacing another definer's function says what changes, and what cannot be undone")


def _views(entry, p):
    run_script(entry, "create view app_owner.v_summary_top as select status, total "
                      "from app_owner.v_order_summary;")
    narrower = ("create or replace view app_owner.v_order_summary as\n"
                "select status, count(*) as n from app_owner.t_order group by status")
    doc = p.preview("summary.sql", narrower)
    assert [b[0] for b in doc["rehearsal"]["broken"]] == ["v_summary_top"], doc["rehearsal"]
    notes = " ".join(doc["rehearsal"]["notes"])
    assert f"definer changes from root@% to {AGENT}@%" in notes, notes
    ok("a view replaced: its SELECT run with LIMIT 0, the view on top predicted invalid")
    p.approve(doc["token"])
    code, res, why = p.confirm("apply", "summary.sql", "--confirm", doc["token"])
    assert code == 3 and [b[0] for b in res["broken"]] == ["v_summary_top"], (code, why, res)
    assert res["differs"] == [] and not view_ok(entry, "app_owner", "v_summary_top")
    ok("written as predicted, and broken: exit 3, v_summary_top named")
    eid = res["restore"].split()[-1]
    doc = p.json("journal", "restore", eid)
    p.approve(doc["token"])
    code, _, why = p.confirm("journal", "restore", eid, "--confirm", doc["token"])
    need = "SET USER" if MARIADB else "SET_ANY_DEFINER"
    assert code == 1 and need in why and "nothing was written" in why, (code, why)
    ok("restoring root's view is refused for this account, and nothing was written")
    # MySQL: root is a system account, so setting it as a definer takes
    # SYSTEM_USER too; MariaDB asks for SET USER alone
    may = "set user" if MARIADB else "set_any_definer, system_user"
    run_script(entry, f"grant {may} on *.* to '{AGENT}'@'%';")
    code, res, why = p.confirm("journal", "restore", eid, "--confirm", doc["token"])
    run_script(entry, f"revoke {may} on *.* from '{AGENT}'@'%';")
    assert code == 0 and view_ok(entry, "app_owner", "v_summary_top"), (code, why, res)
    assert scalar(entry, "select definer from information_schema.views where "
                         "table_schema = 'app_owner' and table_name = 'v_order_summary'") == "root@%"
    ok("the approval was unspent: the same command, run again by an account that may, "
       "restores root's view, and v_summary_top opens again")
    code, _, why = p.run("apply", p.file("v_bad.sql", "create or replace view app_owner.v_bad "
                                         "as select nope from app_owner.t_order"))
    assert code == 1 and "1054" in why and "nothing was written" in why.lower(), why
    ok("a view MySQL would refuse has nothing to approve")


def _rows(entry, p):
    audit = scalar(entry, "select count(*) from app_owner.t_order_audit")
    paid = "update app_owner.t_order set total = total + 1 where status = 'DRAFT'"
    doc = p.preview("paid.sql", paid)
    assert doc["row_set"]["count"] == 2 and doc["rehearsal"]["rows"] == 2, doc
    assert doc["rehearsal"]["predicted"] is False, doc
    assert scalar(entry, "select count(*) from app_owner.t_order_audit") == audit
    p.approve(doc["token"])
    run_script(entry, "insert into app_owner.t_order (status, total) values ('DRAFT', 5);")
    code, _, why = p.confirm("apply", "paid.sql", "--confirm", doc["token"])
    assert code == 1 and "2 rows" in why and "3" in why, why
    code, res, why = p.write("paid.sql", paid)
    assert code == 0 and res["rows"] == 3, (code, why, res)
    assert scalar(entry, "select count(*) from app_owner.t_order_audit") == audit + 3
    ok("DML rehearsed and rolled back; rows that moved refused; then written, triggers and all")
    same = "update app_owner.t_order set status = 'PAID' where status = 'PAID'"
    code, res, why = p.write("same.sql", same)
    assert code == 0 and res["rows"] == 1, (code, why, res)
    ok("an UPDATE that changes no value still counts the row it matched")


def _leaks(entry, p):
    run_script(entry, """
create table app_owner.t_line_log (id int not null auto_increment primary key, line_id int) engine=MyISAM;
create trigger app_owner.trg_line_log after update on app_owner.t_order_line for each row
    insert into app_owner.t_line_log (line_id) values (new.id);
insert into app_owner.t_order_line (order_id, qty) values (1, 1);
""")
    code, out, why = p.run("apply", p.file("qty.sql", "update app_owner.t_order_line set qty = 2 "
                                           "where order_id = 1"))
    assert scalar(entry, "select qty from app_owner.t_order_line where order_id = 1") == 1
    if not MARIADB and scalar(entry, "select @@enforce_gtid_consistency") in ("ON", 1, "1"):
        # MySQL refuses a statement writing both kinds of table itself (1785)
        assert code == 1 and "1785" in why and "nothing was written" in why.lower(), (code, why)
        assert scalar(entry, "select count(*) from app_owner.t_line_log") == 0
        ok("a trigger writing to MyISAM: MySQL, enforcing GTID consistency, refuses it whole")
    else:
        assert code == 3 and "WRITTEN?" in out and "MyISAM" in out, (code, out, why)
        assert scalar(entry, "select count(*) from app_owner.t_line_log") == 1
        ok("a trigger writing to MyISAM inside a preview is reported WRITTEN?, exit 3")
    code, _, why = p.run("apply", p.file("log.sql", "delete from app_owner.t_line_log "
                                         "where id = 1"))
    assert code == 1 and "MyISAM table" in why, why
    ok("a write to a MyISAM table is refused before it runs")


def _breakage(entry, p):
    run_script(entry, "alter table app_owner.t_order add column note2 varchar(10);\n"
                      "create view app_owner.v_note2 as select id, note2 from app_owner.t_order;")
    drop = "alter table app_owner.t_order drop column note2"
    doc = p.preview("drop.sql", drop)
    assert [b[0] for b in doc["rehearsal"]["broken"]] == ["v_note2"], doc["rehearsal"]
    assert "column" in doc["destructive"], doc
    p.approve(doc["token"])
    run_script(entry, "create view reporting.v_note3 as select note2 from app_owner.t_order;")
    code, _, why = p.confirm("apply", "drop.sql", "--confirm", doc["token"])
    assert code == 1 and "reporting.v_note3" in why and "moved" in why, why
    assert scalar(entry, "select count(*) from information_schema.columns where "
                         "table_schema = 'app_owner' and table_name = 't_order' and column_name = 'note2'") == 1
    ok("a prediction that moved after approval is refused: nothing ran")
    code, res, why = p.write("drop.sql", drop)
    assert code == 3 and {b[0] for b in res["broken"]} == {"v_note2", "reporting.v_note3"}, \
        (code, why, res)
    assert res["differs"] == [], res
    ok("an approved breakage lands as predicted, and exits 3 with what broke")
    run_script(entry, "create view app_owner.v_unforeseen as select id from app_owner.t_order_audit;")
    code, res, why = p.write("audit.sql", "rename table app_owner.t_order_audit to "
                                          "app_owner.t_order_audit_old")
    assert code == 3 and [b[0] for b in res["broken"]] == ["v_unforeseen"], (code, why, res)
    assert "trg_order_audit" in res["blind_spot"] and "[text]" in res["blind_spot"], res
    ok("a rename predicted to break the view that reads it; the trigger naming it, a lead")


def _comments_and_session(entry, p):
    code, res, why = p.write("comment.sql", "alter table app_owner.t_order comment = "
                                            "'Orders, every one'")
    assert code == 0, (code, why, res)
    assert scalar(entry, "select table_comment from information_schema.tables where "
                         "table_schema = 'app_owner' and table_name = 't_order'") == "Orders, every one"
    code, _, why = p.restore(res)
    assert code == 0, why
    assert scalar(entry, "select table_comment from information_schema.tables where "
                         "table_schema = 'app_owner' and table_name = 't_order'") == "Customer orders, 'all' of them"
    ok("a table comment written, read back and restored")
    code, out, why = p.run("apply", p.file("session.sql", "set @pythia = 1"))
    assert code == 0 and "Session setting applied" in out, (why, out)
    ok("a session setting says it ends with the connection")
    root = Project(dict(entry, database="app_owner"))
    root.policy(data_dml="confirm")
    # t_order's audit trigger writes a table renamed above: the rehearsal says so
    code, _, why = root.run("apply", root.file("t.sql", "update app_owner.t_order set total = "
                                               "total where id = 1"))
    assert code == 1 and "1146" in why and "t_order_audit" in why, why
    doc = root.preview("root.sql", "delete from app_owner.t_order_audit_old where id = 0")
    assert "every privilege" in (doc["warning"] or ""), doc
    ok("an account that can do far more than the change needs is named")


def _release(entry, p):
    """deploy: data rehearsed as one transaction, landed as one, or not at all."""
    count = "select count(*) from app_owner.t_order where total = 7"
    total = "select total from app_owner.t_order where id = 1"
    # the audit trigger's table, renamed above, comes back
    run_script(entry, "rename table app_owner.t_order_audit_old to app_owner.t_order_audit;")
    before, was = scalar(entry, count), scalar(entry, total)
    p.file("rel.sql", RELEASE)
    code, doc, why = p.confirm("deploy", "rel.sql")
    assert code == 0, (why, doc)
    assert [(m["line"], m["group"]) for m in doc["members"]] == [
        (2, "data_dml"), (3, "data_dml"), (5, "data_dml")], doc["members"]
    assert [m["rehearsal"]["rows"] for m in doc["members"]] == [1, 1, 0], doc["members"]
    assert scalar(entry, count) == before and scalar(entry, total) == was
    ok("deploy previews a data release as one transaction, and writes nothing")

    code, _, why = p.run("approve", "--card", doc["members"][1]["token"])
    assert code == 1 and "approved as a whole" in why, why
    p.approve(doc["batch"])
    run_script(entry, "update app_owner.t_order set total = total + 1 where id = 1;")
    code, _, why = p.confirm("deploy", "rel.sql", "--confirm", doc["batch"])
    assert code == 1 and "statement 2" in why and "nothing was written" in why.lower(), why
    assert scalar(entry, count) == before          # statement 1 did not land either
    ok("a release whose rows moved after approval rolls back whole")

    code, doc, why = p.confirm("deploy", "rel.sql")
    p.approve(doc["batch"])
    was = scalar(entry, total)
    code, res, why = p.confirm("deploy", "rel.sql", "--confirm", doc["batch"])
    assert code == 0 and res["applied"], (why, res)
    assert scalar(entry, count) == before + 1 and scalar(entry, total) == was + 100
    ok("an approved release lands whole, in one commit")

    p.file("ddl.sql", "insert into app_owner.t_order (status, total) values ('DRAFT', 8);\n"
                      "alter table app_owner.t_order add column in_release int;\n")
    code, _, why = p.run("deploy", "ddl.sql")
    assert code == 1 and "ddl.sql:2" in why and "apply it on its own" in why.lower(), why
    assert scalar(entry, "select count(*) from app_owner.t_order where total = 8") == 0
    assert scalar(entry, "select count(*) from information_schema.columns where "
                         "table_schema = 'app_owner' and table_name = 't_order' and column_name = 'in_release'") == 0
    ok("DDL in a release is refused, and nothing before it lands")


def _lint(entry, p):
    code, doc, why = p.confirm("apply", p.file("log.sql", (
        "create table app_owner.t_audit_log (\n    id int not null,\n    at datetime\n"
        ") engine=MyISAM")))
    assert code == 0, why
    found = [(f["rule"], f["line"], f["severity"]) for f in doc["lint"]]
    assert ("mysql-non-transactional", 4, "error") in found, found
    assert ("mysql-primary-key", 1, "warn") in found, found
    code, _, why = p.run("lint", "log.sql")
    assert code == 1, why
    ok("lint: a MyISAM table is an error in a real preview, and lint exits 1")


def _lease(entry, p):
    """autopilot: one approved lease lands covered writes, and nothing else."""
    from pythia_core import human
    code, doc, why = p.confirm("autopilot", "request", "--groups", "comments",
                               "--max-writes", "2")
    assert code == 0 and len(doc["token"]) == 8, why
    text = "alter table app_owner.t_order comment = 'orders, under a lease'"
    code, doc2, _ = p.confirm("apply", p.file("c1.sql", text))
    assert code == 0 and doc2["will_apply"] is False         # a request is no lease
    human.FORCE_CONSOLE = True
    try:
        code, _, why = p.run("approve", doc["token"])
        assert code == 0, why
    finally:
        human.FORCE_CONSOLE = False
    code, res, why = p.confirm("apply", "c1.sql")
    assert code == 0 and res["applied"] and res["confirmed_via"] == "autopilot", (why, res)
    assert scalar(entry, "select table_comment from information_schema.tables where "
                         "table_schema = 'app_owner' and table_name = 't_order'") == "orders, under a lease"
    code, doc3, why = p.confirm("apply", p.file("s1.sql", "alter table app_owner.t_order "
                                                          "add column under_lease int"))
    assert code == 0 and doc3["will_apply"] is False, why
    assert "does not cover structural" in doc3["autopilot"]["why"], doc3["autopilot"]
    assert scalar(entry, "select count(*) from information_schema.columns where "
                         "table_schema = 'app_owner' and table_name = 't_order' and column_name = 'under_lease'") == 0
    code, report, _ = p.confirm("autopilot", "report")
    assert [w["verdict"] for w in report["writes"]] == ["ok"], report
    assert p.run("autopilot", "off")[0] == 0
    ok("autopilot: an approved lease lands a covered write — a predicted one — and only that")


def _mariadb(entry, p):
    """What only MariaDB writes: a sequence, its views; a package refused."""
    run_script(entry, "create view app_owner.v_next as "
                      "select nextval(app_owner.s_order) as next_id;")
    doc = p.preview("seq.sql", "create sequence app_owner.s_invoice start with 1")
    assert doc["rehearsal"]["predicted"] is True and doc["rehearsal"]["broken"] == [], doc
    code, res, why = p.write("seq.sql", "create sequence app_owner.s_invoice start with 1")
    assert code == 0, (code, why, res)
    assert scalar(entry, "select count(*) from information_schema.tables where "
                         "table_schema = 'app_owner' and table_name = 's_invoice' and table_type = 'SEQUENCE'") == 1
    ok("a sequence created through the gate, predicted then written")
    doc = p.preview("drop_seq.sql", "drop sequence app_owner.s_order")
    assert [b[0] for b in doc["rehearsal"]["broken"]] == ["v_next"], doc["rehearsal"]
    assert "p_order_number" in doc["rehearsal"]["blind"], doc["rehearsal"]
    p.approve(doc["token"])
    code, res, why = p.confirm("apply", "drop_seq.sql", "--confirm", doc["token"])
    assert code == 3 and [b[0] for b in res["broken"]] == ["v_next"], (code, why, res)
    assert res["differs"] == [] and not view_ok(entry, "app_owner", "v_next"), res
    ok("dropping a sequence breaks the view drawing from it, as predicted: exit 3")
    for name, text, said in (
            ("pkg.sql", "create or replace package app_owner.pkg_order as\n"
                        "    function f_count return int;\nend", "read only"),
            ("ret.sql", "delete from app_owner.t_order_audit where id = 0 returning id",
             "RETURNING")):
        code, _, why = p.run("apply", p.file(name, text))
        assert code == 1 and said in why, (name, code, why)
    ok("a package and a RETURNING are refused before anything runs")


def main():
    if not os.environ.get("PYTHIA_MYSQL_LIVE_HOST"):
        print("SKIP live check: PYTHIA_MYSQL_LIVE_HOST is not set")
        return
    entry = admin_entry()
    which_server(entry)
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
    check_writes(entry)
    print("OK")


if __name__ == "__main__":
    main()
