# pythia-mysql

[English](README.md) · **Tiếng Việt**

pythia cho MySQL: phát triển stored program cho AI agent, xây trên
[pythia-core](https://github.com/thaildhe172591/pythia-core). Nó nhắm làm
được điều mà [pythia](https://github.com/thaildhe172591/pythia) làm trên
Oracle và các engine anh em làm trên PostgreSQL, SQL Server và MongoDB:
agent học từ catalog đang chạy, hỏi một người trước mọi lần ghi, và chỉ ghi
qua một cổng có snapshot, có kiểm chứng và báo cáo trung thực.

**Alpha (0.1.0).** Nó đọc được mọi thứ mà nhịp Học của pythia cần, ghi qua
một cổng duy nhất — dữ liệu được diễn tập trong transaction, DDL được dự
đoán, ghi một lần rồi đọc lại — và chuẩn bị một project cho agent: guard,
bản tóm tắt đầu phiên, các cánh cửa duyệt và các skill `pythia-mysql-*`.

| Đã dùng được |
|---|
| đọc: `check`, `ls`, `src`, `cols`, `ddl`, `grep`, `deps`, `impact`, `errors`, `connections` |
| ghi: `apply`, `deploy`, `approve`, `journal`, `history`, `policy`, `autopilot`, `lint` |
| harness: `install`, `doctor`, `hook`, `mcp`, `skill lint` |

MySQL 8.4 LTS là phiên bản tối thiểu: CI chạy toàn bộ live check trên 8.4,
9.4 và 9.5, và thấp hơn 8.4 — hoặc trên MariaDB — thì `check` nói rõ (không
gì bị từ chối).

## Cài đặt

```bash
pip install pythia-mysql
```

Lệnh này kéo theo pythia-core, và [PyMySQL](https://pypi.org/project/PyMySQL/),
viết thuần Python: không cần cài thư viện client nào, trên Windows, macOS
hay Linux. Bản đang phát triển là nhánh main của cả hai:

```bash
pip install "git+https://github.com/thaildhe172591/pythia-core" \
            "git+https://github.com/thaildhe172591/pythia-mysql"
```

## Chuẩn bị một project cho agent

```bash
cd your-project
pythia-mysql install     # once; a second run changes nothing
pythia-mysql doctor      # is everything wired? exit 1 names what is not
```

`install` ghi những thứ sau, và giữ nguyên mọi thứ khác:

- `.pythia/mysql/connections.json`, mode 600, tạo một lần từ template — dev
  tự điền mật khẩu; agent không bao giờ mở file này;
- các dòng `.gitignore` cho file đó, cho các lần duyệt của máy này
  (`.pythia/mysql/grants/`) và cho `.claude/settings.local.json`;
- `.claude/settings.local.json`: các hook (guard, bản tóm tắt đầu phiên,
  câu trả lời AskUserQuestion), ghi bằng đường dẫn tuyệt đối của interpreter
  này để chúng chạy được dù virtual environment có được kích hoạt hay không,
  và các deny rule cho file của engine;
- MCP approver `pythia_mysql` (tool `pythia_mysql_approve`), chỉ trong file
  riêng của máy này: local scope của Claude Code cho project
  (`~/.claude.json`) và `~/.codex/config.toml` của Codex, mỗi cái khi client
  đó đã từng chạy ở đây;
- một khối `pythia-mysql` trong CLAUDE.md và AGENTS.md (khối của các công cụ
  khác, và chữ của chính dev, được giữ nguyên);
- các skill, trong `.claude/skills` và `.agents/skills`:
  `using-pythia-mysql` (bộ định tuyến), `pythia-mysql-explore`,
  `pythia-mysql-impact`, `pythia-mysql-apply`, `pythia-mysql-deploy`,
  `pythia-mysql-autopilot`, `pythia-mysql-verify`.

Sau khi cài, khởi động lại phiên của agent để hook được nạp. Từ đó mỗi phiên
bắt đầu bằng các luật và một dòng `STATE` (connection, write policy). Trước
mỗi lần gọi tool, guard quyết định:

| Agent chạy | Guard |
|---|---|
| `mysql`, `mysqlsh` hay `mariadb` được đưa SQL ghi (DDL, DML, `CALL`, `DO`, `PREPARE`/`EXECUTE`, `LOAD DATA`, `SET GLOBAL`, `SELECT ... INTO OUTFILE`, `LOCK TABLES`, `source file.sql`), một script (`< file`, một pipe vào client, `mysqlsh -f`), `util.load*` của MySQL Shell; `mysqlimport`; `mysqladmin` create, drop, flush, kill, password hay shutdown — kể cả sau `docker exec`, `ssh`, `sudo` hay `bash -c` | chặn: mọi lần ghi đi qua `pythia-mysql apply` |
| một MCP SQL tool được đưa SQL ghi | chặn |
| đọc `connections.json`; sửa `policy.json`, journal hay một grant; đặt `PYTHIA_MYSQL_CI`; gọi `grants.mint` từ một one-liner | chặn |
| một lệnh đọc của `pythia-mysql`, một preview, `approve --card` | cho qua, không hỏi |
| `apply --confirm <token>` mà dev đã duyệt trên connection này | cho qua; apply kiểm lại |
| `mysql` chỉ đọc, `mysqldump`, `approve`, `--yes`, `policy set`, mọi lệnh ghép | đứng ngoài: client tự hỏi |

Guard đọc một lệnh theo những gì nó gọi tên, không theo ý nghĩa của nó: nó
có thể chặn một lệnh vô hại (một `SELECT` có chữ `drop` trong nội dung) và
bỏ lọt một lần ghi được viết theo cách nó không liệt kê. Nó thấy các lệnh mà
Claude Code đưa cho các tool, không thấy Workbench hay một driver bên trong
ứng dụng. Cổng phía sau vẫn giữ được trong cả hai trường hợp (SECURITY.md
của pythia-core).

pythia-postgres, pythia-mssql và pythia-mongo cài cạnh nó trong cùng một
project, và pythia cho Oracle cũng vậy: mỗi bên giữ nguyên hook và khối
hướng dẫn của các bên khác, và guard cùng hook duyệt của mỗi bên chỉ hành
động cho chính công cụ của nó (CI của pythia-core kiểm tra điều này khi cả
năm cùng được cài).

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
pythia-mysql approve 3fa9c1                     # the developer approves (or from chat, below)
pythia-mysql apply change.sql --confirm 3fa9c1  # writes it — only as approved
pythia-mysql journal restore <entry>            # undo is a write too: preview, approve, confirm
pythia-mysql policy                             # which groups may be written, and is rollback real?
```

Dev duyệt qua cánh cửa đầu tiên dùng được:

1. **Trong chat của Claude Code.** Agent hỏi bằng AskUserQuestion, nội dung
   đúng nguyên văn output của `pythia-mysql approve --card <token>`, hai lựa
   chọn Approve / Reject. Hook nhận câu trả lời chỉ ghi nhận lần duyệt khi
   câu hỏi mang đúng thẻ đó và chính dev chọn Approve — không phải câu trả
   lời do agent viết, không phải một hộp thoại tự đóng khi không có ai.
2. **Qua MCP approver** (`pythia_mysql_approve`; Codex bắt đầu từ đây):
   client hiện thẻ, và chỉ một lần Approve rõ ràng mới được tính.
3. **Ở console của dev:** `pythia-mysql approve <token>`.

`pythia-mysql doctor` cảnh báo những thiết lập có thể tự trả lời cánh cửa
chat thay cho dev (chế độ `dontAsk`, một allow rule cho AskUserQuestion, một
hook khớp mọi tool).

### Một release: `deploy`, một transaction

```bash
pythia-mysql deploy 01_fix.sql 02_backfill.sql                     # preview the release as one transaction
pythia-mysql deploy 01_fix.sql 02_backfill.sql --confirm 9c41e0b2aa  # all of it, as approved, or none
```

Một release là dữ liệu: một hay nhiều script gồm `INSERT`, `REPLACE`,
`UPDATE` và `DELETE`, được cắt ở mỗi `;` (và ở các dòng `DELIMITER`, như
mysql client cắt). Nó được rehearse trong một transaction: từng câu lệnh
theo thứ tự, số dòng lấy tại đúng thời điểm của nó, rồi tất cả được
rollback. Một thẻ hiện mọi câu lệnh, và một lần duyệt (token 10 chữ số, qua
cùng các cánh cửa) phủ cả release; token của một câu lệnh lẻ không được
duyệt riêng. Lúc confirm, nó kiểm từng câu lệnh giống hệt từng byte với bản
đã duyệt trước khi chạy gì, chạy lại release trong một transaction, và chỉ
commit nếu mọi câu lệnh vẫn khớp. Một câu lệnh lỗi, hoặc các dòng đã thay
đổi, sẽ rollback cả release.

MySQL commit DDL ngay khi chạy nó, nên một release không thể chứa DDL: một
table, một cột, một index, một view, một routine, một trigger, một event,
một comment hay một grant đều bị từ chối, không có gì được ghi — hãy apply
từng cái riêng, trước hoặc sau phần dữ liệu. Một `SET` trong release cũng bị
từ chối, cùng mọi thứ `apply` từ chối. Các dòng do chính release insert
nhận một giá trị `AUTO_INCREMENT`, `CURRENT_TIMESTAMP` hay `UUID()` mới mỗi
lần chạy, nên một UPDATE hay DELETE nhắm vào chúng ở sau trong cùng release
không bao giờ khớp với lần duyệt: hãy cho chúng giá trị cuối cùng ngay
trong INSERT.

### Lint: trước mọi lần apply

```bash
pythia-mysql lint 01_table.sql 02_view.sql   # a change's files in one run
pythia-mysql lint --rules                    # every rule and its effective severity
```

Các rule đọc những gì MySQL chấp nhận mà một người review thì không:

| Rule | Mặc định | Vì sao |
|---|---|---|
| `mysql-non-transactional` | error | một table MyISAM, MEMORY hay engine khác không có transaction thì không rehearse được, có thể mất dòng khi crash, và bỏ qua foreign key |
| `mysql-utf8mb3` | warn | `utf8` là `utf8mb3`: không có emoji và các ký tự CJK hiếm — dùng `utf8mb4` |
| `mysql-select-star` | warn | MySQL khai triển `*` khi tạo view và giữ nguyên danh sách đó; kết quả của một procedure đổi hình dạng; `EXISTS (SELECT * ...)` thì không sao |
| `mysql-not-in-subquery` | warn | `NOT IN (SELECT ...)` không bao giờ đúng khi subquery trả về một NULL |
| `mysql-primary-key` | warn | thiếu nó, InnoDB tự tạo một khóa ẩn mà replication và các công cụ theo dòng không dùng được |
| `mysql-table-comment` | warn | một table mới có `COMMENT` của nó trong cùng thay đổi (một `ALTER TABLE ... COMMENT` trong cùng lần chạy cũng được tính) |
| `mysql-function-characteristic` | warn | một function không khai báo `DETERMINISTIC`, `NO SQL` hay `READS SQL DATA` bị từ chối khi binary logging đang bật (1418) |
| `mysql-definer` | warn | một `DEFINER` nêu tên một tài khoản cần `SET_ANY_DEFINER`, và hỏng ở nơi tài khoản đó không tồn tại |
| `mysql-zero-date` | warn | `'0000-00-00'` bị từ chối dưới `NO_ZERO_DATE` mặc định của MySQL |
| `mysql-limit-order` | info | `LIMIT` không có `ORDER BY` trong stored code lấy những dòng nào tới trước |

Những gì MySQL tự từ chối được để cho rehearsal hoặc dự đoán. Team đặt
severity và quy ước đặt tên trong `.pythia/mysql/lint.json`:

```json
{"severity": {"mysql-select-star": "error", "naming": "error"},
 "naming": {"PROCEDURE": "^p_[a-z0-9_]+$", "VIEW": "^v_[a-z0-9_]+$"}}
```

Mọi preview đều hiện các phát hiện, lỗi của một câu lệnh nằm trên thẻ của
nó, và autopilot không bao giờ ghi một thay đổi còn lỗi lint.

### Autopilot: một lease thay cho từng lần duyệt

```bash
pythia-mysql autopilot request --groups source,comments --hours 2 --max-writes 30
pythia-mysql autopilot report      # every write under the lease, with its restore
pythia-mysql autopilot off         # anyone may revoke
```

Khi dev muốn agent làm việc mà không phải duyệt từng lần ghi, agent xin một
lease. Thẻ của nó nêu connection, các group, thời gian, số lần ghi và có gồm
câu lệnh phá hủy hay không, và chưa có gì được ủy quyền cho tới khi dev duyệt
nó qua một cánh cửa (hoặc tự chạy `pythia-mysql autopilot on` ở console).
Trong thời gian lease còn hiệu lực, `apply` và `deploy` ghi những gì nó phủ
mà không cần `--confirm` — vẫn có snapshot, rehearse hoặc dự đoán, đọc lại
và ghi journal. Lease không bao giờ phủ một connection khác, một connection
đánh dấu `"protected": true` (hoặc có `"env"` là prod / production / prd /
live), một group hay câu lệnh phá hủy mà thẻ không nêu, hoặc quá 1000 dòng;
một lần ghi làm gãy thứ gì đó, ghi ra khác với dự đoán hoặc là `WRITTEN?`,
hoặc năm lần thất bại liên tiếp, sẽ tạm dừng nó.

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
  lần trong một bản diễn tập; preview có nói rõ. Một server bật kiểm tra
  GTID consistency tự từ chối câu lệnh như vậy (lỗi 1785), trước khi ghi bất
  cứ gì.
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
check — mọi đường đọc, mọi đường ghi, một release, một phát hiện lint trong
một preview thật và một lần ghi dưới lease — với MySQL 8.4, 9.4 và 9.5 trong
các service container. Nó test với nhánh pythia-core cùng tên khi có.

## Giấy phép

MIT
