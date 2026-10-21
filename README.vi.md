# pythia-mysql

[English](README.md) · **Tiếng Việt**

pythia cho MySQL: phát triển stored program cho AI agent, xây trên
[pythia-core](https://github.com/thaildhe172591/pythia-core). Nó nhắm làm
được điều mà [pythia](https://github.com/thaildhe172591/pythia) làm trên
Oracle và các engine anh em làm trên PostgreSQL, SQL Server và MongoDB:
agent học từ catalog đang chạy, hỏi một người trước mọi lần ghi, và chỉ ghi
qua một cổng có snapshot, có kiểm chứng và báo cáo trung thực.

**Pre-alpha (Phase 9a).** Nó đọc được mọi thứ mà nhịp Học của pythia cần,
và chưa ghi gì.

| Đã dùng được | Tiếp theo |
|---|---|
| `check`, `ls`, `src`, `cols`, `ddl`, `grep`, `deps`, `impact`, `errors`, `connections` | cổng ghi (9b); harness, deploy, autopilot và lint (9c) |

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

## Kiểm thử

```bash
python tests/test_mysql.py    # no database, no PyMySQL
python tests/live_check.py    # a disposable server only (see its docstring)
```

CI chạy bộ test trên Ubuntu, Windows và macOS, Python 3.9 và 3.13, và live
check với MySQL 8.4, 9.4 và 9.5 trong các service container. Nó test với
nhánh pythia-core cùng tên khi có.

## Giấy phép

MIT
