# pythia-mysql

[English](README.md) · **Tiếng Việt**

pythia cho MySQL: phát triển stored program cho AI agent, xây trên
[pythia-core](https://github.com/thaildhe172591/pythia-core). Nó nhắm làm
được điều mà [pythia](https://github.com/thaildhe172591/pythia) làm trên
Oracle và các engine anh em làm trên PostgreSQL, SQL Server và MongoDB:
agent học từ catalog đang chạy, hỏi một người trước mọi lần ghi, và chỉ ghi
qua một cổng có snapshot, có kiểm chứng và báo cáo trung thực.

**Pre-alpha (Phase 9b).** Nó đọc được mọi thứ mà nhịp Học của pythia cần,
và ghi qua một cổng duy nhất: dữ liệu được diễn tập trong transaction, DDL
được dự đoán, ghi một lần rồi đọc lại.

| Đã dùng được | Tiếp theo |
|---|---|
| `check`, `ls`, `src`, `cols`, `ddl`, `grep`, `deps`, `impact`, `errors`, `connections`; `apply`, `approve`, `journal`, `policy` | harness — guard, `install`, `doctor`, các cánh cửa duyệt trong chat và skill — cùng `deploy`, autopilot và lint (9c) |

MySQL 8.4 LTS là phiên bản tối thiểu: CI chạy toàn bộ live check trên 8.4,
9.4 và 9.5, và thấp hơn 8.4 — hoặc trên MariaDB — thì `check` nói rõ (không
gì bị từ chối).

## Cài đặt (từ git khi còn pre-alpha)

```bash
pip install "git+https://github.com/thaildhe172591/pythia-core" \
            "git+https://github.com/thaildhe172591/pythia-mysql"
```

Lệnh này kéo theo [PyMySQL](https://pypi.org/project/PyMySQL/), viết thuần
Python: không cần cài thư viện client nào, trên Windows, macOS hay Linux.

## Kết nối

`.pythia/mysql/connections.json` ở thư mục gốc của project, chỉ chủ sở hữu
được đọc (`chmod 600`), và nằm ngoài git. Mẫu:
[examples/connections.example.json](examples/connections.example.json).

```json
{
  "default": "dev",
  "dev": { "host": "db-dev", "port": 3306, "database": "app_owner",
           "user": "app_agent", "password": "...", "tls": "request" }
}
```

- `host`, `database`, `user` là bắt buộc. Trong MySQL, một schema chính là
  một database: `database` là nơi một tên không kèm schema rơi vào, và là
  cái pythia đọc, trừ khi `schema` chỉ tới một cái khác (khi đó `check` cảnh
  báo).
- `tls` là `off`, `request` (mặc định: dùng TLS mỗi khi server có), `require`
  (mã hoá hoặc từ chối, không kiểm chứng chỉ) hoặc `verify` (kiểm chứng chỉ
  và tên host, theo `tls_ca` nếu có, không thì theo các CA của máy này).
- Một tài khoản dùng `caching_sha2_password` — mặc định của MySQL — cần TLS,
  hoặc gói `cryptography`, để gửi mật khẩu; khi không có cả hai,
  pythia-mysql nói rõ thay vì hỏng một cách khó hiểu.
- Entry được chọn theo `--conn NAME`, rồi `PYTHIA_MYSQL_CONNECTION`, rồi entry
  duy nhất, rồi thư mục ngay dưới gốc project, rồi `"default"`.
  `PYTHIA_MYSQL_CONFIG` trỏ tới một file khác.

pythia cho Oracle giữ `.pythia/connections.json`, còn các engine khác giữ
`.pythia/postgres/`, `.pythia/mssql/` và `.pythia/mongo/`; pythia-mysql
không đọc cái nào trong số đó.

## Các lệnh

```bash
pythia-mysql check                 # server, database, where unqualified names land
pythia-mysql ls "t_order%"         # tables, views, routines, triggers, events by LIKE
pythia-mysql src f_order_total     # a routine, view, trigger or event, rebuilt
pythia-mysql cols t_order          # columns, types, defaults, generated columns
pythia-mysql ddl t_order           # CREATE TABLE and its triggers, rebuilt
pythia-mysql grep "t_order where"  # every line of code holding a text
pythia-mysql deps p_order_paid     # what it uses
pythia-mysql impact t_order        # what uses it: run before changing it
pythia-mysql errors [NAME]         # views MySQL has marked broken; what it cannot check
```

`--json` cho một envelope cho mỗi lệnh; `--limit`, `--max-lines` và
`--offset` chia cửa sổ cho đầu ra dài, và mọi chỗ bị cắt đều nói cách lấy
phần còn lại.

### Những gì catalog không thấy, và pythia-mysql nói ra thế nào

- **`impact` hỏi catalog, rồi tìm trong thân code.** information_schema ghi
  lại các bảng, view và hàm mà một view đọc, các trigger trên một bảng và
  các khoá ngoại trỏ vào nó — và không ghi gì về những thứ mà thân một
  procedure, function, trigger hay event dùng. Các thân đó, ở mọi schema,
  được tìm theo tên như một từ trọn vẹn (có tiền tố thì tiền tố là schema,
  không có thì là schema của chính thân đó), và các dòng đó được đánh dấu
  `[text]`. Mỗi điểm mù đều được in ra mỗi lần.
- **MySQL giấu những gì một tài khoản không được thấy.** Một routine cần
  `SHOW_ROUTINE` (hoặc `SELECT` toàn cục) để được thấy kèm thân, một
  trigger cần quyền `TRIGGER`, một event cần `EVENT`. pythia-mysql đọc
  `SHOW GRANTS` và nói tài khoản này không thấy được những gì trong số đó,
  mỗi lần điều đó có thể ảnh hưởng.
- **`errors` đọc những gì MySQL đã đánh dấu là hỏng.** Xoá hoặc sửa mất
  thứ mà một view đọc sẽ làm view bị đánh dấu không hợp lệ, và pythia-mysql
  liệt kê lỗi mà view sẽ báo. MySQL chỉ phân giải các tên bên trong một
  procedure, function, trigger hay event khi nó chạy: `errors` gọi tên
  chúng là chưa được kiểm, và không bao giờ coi đó là sạch.
- **`src` và `ddl` được dựng lại, không phải dump.** information_schema
  không giữ câu lệnh CREATE và MySQL không giữ số dòng: phần đầu được dựng
  lại ở dòng 1, và phần thân theo sau đúng như lúc viết (SELECT của một view
  thì chỉ như MySQL đã viết lại). `ddl` bọc code trong `DELIMITER //`, như
  mysql client và Flyway đọc, và ghi chú `sql_mode` lúc tạo. Live check chạy
  mọi `ddl` vào một bản sao rồi so với bản gốc.
- **Lệnh đọc không thể ghi.** Phiên của mọi lệnh đọc là `READ ONLY`, và
  MySQL từ chối cả DML lẫn DDL trong đó (lỗi 1792). Một tài khoản chỉ đọc là
  lớp bảo vệ đầu tiên.

### Ghi: cổng

```bash
pythia-mysql apply change.sql                   # preview: nothing written
pythia-mysql approve 3fa9c1                     # the developer approves, at their own console
pythia-mysql apply change.sql --confirm 3fa9c1  # writes it — only as approved
pythia-mysql journal restore <entry>            # undo is a write too: preview, approve, confirm
pythia-mysql policy                             # which groups may be written, and is rollback real?
```

Cho tới khi có harness (9c), developer duyệt ngay trong terminal của chính
họ: chưa có hook nào đọc câu trả lời trong chat và chưa có MCP approver, nên
preview không nêu cánh cửa nào khác.

### Một câu lệnh: `apply`

Mỗi file một câu lệnh. Một stored program (`CREATE PROCEDURE`, `FUNCTION`,
`TRIGGER`, `EVENT`) chiếm cả file, kể cả các dấu `;` trong thân của nó, và
không được có gì sau thân; các dòng `DELIMITER` được đọc như mysql client
đọc, nên đầu ra của `ddl` apply được nguyên như vậy. Mọi thứ khác kết thúc ở
dấu `;` của nó. `apply` xếp câu lệnh vào một nhóm, và policy quyết định:
`source` (view, procedure, function, trigger, event) và `comments` (`ALTER
TABLE ... COMMENT = '...'`, đứng riêng) cần developer duyệt; `data_dml`,
`structural` (DDL) và `grants` (`GRANT` và `REVOKE` trên một schema hoặc một
đối tượng trong đó) bị từ chối cho tới khi developer chạy `pythia-mysql
policy set <group> confirm` ở một console. `session` (`SET`) được phép.

MySQL commit DDL ngay khi chạy, nên đường ghi tách làm hai:

- **Dữ liệu được diễn tập.** Một INSERT, REPLACE, UPDATE hay DELETE chạy
  trong transaction rồi được rollback; lần confirm chạy lại nó và chỉ commit
  nếu kết quả vẫn khớp. Một UPDATE hay DELETE được duyệt theo các dòng của
  nó: số dòng, một mẫu và một fingerprint trên mọi cột (một tổng không phụ
  thuộc thứ tự của `md5(json_array(...))`); nếu có dòng nào vào thêm, ra
  khỏi hay thay đổi trước lần confirm, lần confirm bị từ chối. Một UPDATE
  đếm các dòng nó khớp, đúng như phép kiểm, chứ không chỉ các dòng có giá
  trị thay đổi.
- **Một bản diễn tập không thể ghi vào nơi MySQL không rollback được.** Câu
  lệnh mà bảng của chính nó là MyISAM, MEMORY hay engine khác không có
  transaction bị từ chối trước khi chạy. Một trigger hay function ghi vào
  bảng như vậy sẽ biến preview thành một lần ghi, nên mọi thay đổi dữ liệu
  chạy trước trong một savepoint: khi rollback savepoint đó khiến MySQL báo
  cảnh báo 1196, preview được báo là **`WRITTEN?`** với exit 3 — các dòng
  đó đã được ghi — và không bao giờ là chưa ghi gì. Vì thế câu lệnh chạy hai
  lần trong một bản diễn tập; preview có nói rõ.
- **DDL được dự đoán — không gì chạy trước khi được duyệt.** SELECT của một
  view chạy với `LIMIT 0`, nên các tên trong đó phải phân giải được. Các
  view mà MySQL sẽ đánh dấu không hợp lệ được đọc từ information_schema: mọi
  view đọc một bảng, view, function hay cột mà câu lệnh xoá hoặc đổi tên, và
  mọi view nằm trên những view đó, ở bất kỳ schema nào. Một routine, trigger
  hay event là `NOT VERIFIED` — MySQL chỉ kiểm các tên bên trong nó khi nó
  chạy — và các routine nhắc tới thứ mà câu lệnh xoá được liệt kê như các
  manh mối `[text]`. Sau khi được duyệt, câu lệnh chạy một lần; các view mà
  MySQL đã đánh dấu không hợp lệ được đọc lại, và bất cứ gì khác với dự đoán
  đều thoát với exit 3, như một chỗ hỏng. Một dự đoán đã thay đổi kể từ lúc
  được duyệt sẽ khiến lần ghi bị từ chối.
- **Một CREATE cho routine đã tồn tại sẽ thay thế nó.** MySQL không có
  `CREATE OR REPLACE` cho procedure, function, trigger hay event. Một
  procedure hay function được tạo thử trước dưới một tên nháp, để phán quyết
  của MySQL về đoạn text mới không tốn gì; rồi bản cũ bị drop và bản mới
  được tạo, và nếu MySQL từ chối bản mới thì bản cũ được đặt lại từ snapshot
  (nếu cả việc đó cũng thất bại, nó là **`WRITTEN?`**, exit 3, kèm lệnh
  restore). Một trigger hay event được drop rồi tạo lại; các dòng được ghi ở
  giữa không kích hoạt trigger nào. Một view được thay bằng `CREATE OR
  REPLACE VIEW`, việc MySQL làm trong một bước.
- **Definer được nói rõ.** Một lần thay thế không có mệnh đề `DEFINER` sẽ do
  chính tài khoản này định nghĩa; preview nói rõ khi điều đó làm definer
  thay đổi. Đặt lại routine hay view của một tài khoản khác cần
  `SET_ANY_DEFINER` (và `SYSTEM_USER` khi tài khoản đó là tài khoản hệ
  thống): khi tài khoản này không có quyền đó, preview nói rằng nó sẽ không
  đặt lại được bản cũ, và một lần restore nó thử sẽ bị từ chối mà không ghi
  gì.
- **Bị từ chối, kèm lý do:** `CALL`, `DO`, `PREPARE` và `EXECUTE`; các câu
  lệnh phức hợp ngoài stored program; `SELECT`, `SHOW`, `WITH`; `USE`; điều
  khiển transaction và `LOCK TABLES`; `LOAD DATA`; bảng tạm; tài khoản,
  role, database và các câu lệnh cấp server khác (`SET GLOBAL`, `FLUSH`,
  `GRANT ... ON *.*`); bảo trì bảng (`OPTIMIZE`, `ANALYZE`); `IF NOT EXISTS`
  trên một stored program; executable comment (`/*! ... */`); nhiều câu lệnh
  trong một file; một UPDATE hay DELETE mà các dòng của nó không đọc được
  trước (`IGNORE`, `ORDER BY ... LIMIT`, nhiều bảng, một join, một subquery,
  mệnh đề `PARTITION`, ngoặc không cân); và một routine mà tài khoản này
  không đọc được thân (không có gì để snapshot).

pythia-mysql không bao giờ bật `MULTI_STATEMENTS` hay `LOCAL INFILE`: chính
MySQL từ chối mọi text nằm sau câu lệnh duy nhất được gửi đi. Một lần ghi
chờ khoá tối đa 5 giây (`innodb_lock_wait_timeout`, `lock_wait_timeout`).
Một bản diễn tập vẫn kích hoạt trigger và lấy giá trị `AUTO_INCREMENT`, và
preview của một thay đổi dữ liệu có nói rõ. Exit code theo pythia: `0` sạch,
`1` bị từ chối, `3` đã ghi nhưng hỏng, hoặc đã ghi khác với dự đoán (kèm
lệnh restore).

### Quyền tối thiểu

Các lệnh đọc cần `SELECT` và `SHOW VIEW` trên các schema, và `SHOW_ROUTINE`
để đọc thân routine:

```sql
CREATE USER 'app_agent'@'%' IDENTIFIED BY '...';
GRANT SELECT, SHOW VIEW ON app_owner.* TO 'app_agent'@'%';
GRANT SHOW_ROUTINE ON *.* TO 'app_agent'@'%';
```

MySQL chỉ cho thấy trigger với tài khoản có `TRIGGER`, và event với tài
khoản có `EVENT` — cả hai đều cho phép sửa chúng. Không có chúng,
pythia-mysql nói rằng trigger và event bị giấu; live check chạy mọi lệnh đọc
theo cả hai cách.

Một lần ghi cần đúng những gì thay đổi đó cần, chỉ trên schema của nó — ví
dụ `INSERT, UPDATE, DELETE` cho dữ liệu, `CREATE, ALTER, DROP, INDEX, CREATE
VIEW, CREATE ROUTINE, ALTER ROUTINE, TRIGGER, EVENT` cho DDL. Một tài khoản
có mọi quyền trên server, `SUPER`, `SYSTEM_USER`, `SET_ANY_DEFINER` hay
`SET_USER_ID` được nêu tên trong preview: nhiều hơn hẳn những gì một thay
đổi cần. Live check chạy mọi đường ghi bằng một tài khoản mà quyền ghi chỉ
dừng ở schema của nó.

## Kiểm thử

```bash
python tests/test_mysql.py    # no database, no PyMySQL
python tests/live_check.py    # a disposable server only (see its docstring)
```

CI chạy bộ test trên Ubuntu, Windows và macOS, Python 3.9 và 3.13, và live
check — mọi đường đọc và mọi đường ghi — với MySQL 8.4, 9.4 và 9.5 trong các
service container. Nó test với
nhánh pythia-core cùng tên khi có.

## Giấy phép

MIT
