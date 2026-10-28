# SunJudge API 文档

适用范围：当前 M1–M4 实现及生产配置整理。完整端点、角色、入口参数和返回顶层字段见 [自动路由索引](API_REFERENCE.md)。它由实际代码生成，更新路由后执行 `cd backend && uv run python scripts/generate_api_reference.py`。

## 通用约定

- 基址：`https://judge.example.cn/api`；本地开发通常为 `http://127.0.0.1:5000/api`。
- 鉴权：Flask-Login Session Cookie，不使用 Bearer Token。浏览器请求携带 `credentials: 'include'`；命令行使用 cookie jar。
- JSON 写请求设置 `Content-Type: application/json`。上传为 multipart，浏览器自动生成 boundary，不手动设置 Content-Type。
- **生产 POST/PUT/PATCH/DELETE 必须携带精确匹配 TRUSTED_ORIGINS 的 Origin**，包括登录和注册；缺失、`null`、其他子域名均返回 403。浏览器同源写请求会自动发送；curl/其他客户端需显式设置。该校验无需 CSRF Token。
- 整数路径参数必须为正整数业务 ID。列表目前没有分页。时间输出为 ISO datetime；写入 deadline 建议显式使用 `+08:00` 或 `Z`，无时区输入按 UTC 处理。
- 常见错误体为 `{"message":"原因"}`，部分含 `details`、`missing_keys`、`invalid_students` 等。400 参数错误；401 未登录/凭据错误；403 权限、来源、截止时间等；404 资源不存在或不可管理；409 冲突；413 超限。Nginx 可能返回 HTML 413/429，客户端不能假设所有响应均为 JSON。
- 管理员不创建教学班、不导入或维护名单、不批改。`/admin` 是管理侧路径前缀，不意味着管理员可以执行所有操作。以索引中实际角色为准，教师只管理自己的教学班。

## 账号与班级

`POST /auth/register`：学生传 `role=student`（默认）、`student_name`、`invite_code`（兼容 `student_id`）、`password`；教师传 `role=teacher`、`username`、`password`。密码至少 6 位，教师用户名至少 3 位。成功 201，返回 `{user}`。学生真实姓名须匹配名单，邀请码必须为 `OS202601-06` 格式；加入新班级继续使用原密码。学生无需提交昵称。

`POST /auth/login`：`{username,password}`，成功 200 `{user}`；学生 username 为真实姓名或任一绑定编号。教师审批未通过返回 403；同名同密码账号冲突返回 409。`POST /auth/logout` 返回 `{message}`；`GET /auth/me` 未登录也返回 200 `{user:null}`。

`GET /classes/public` 返回启用邀请码的班级公开信息；`GET /classes/my` 返回学生已加入班级、各班 roster 身份和完成/成绩统计。班级身份必须读 `class.student.student_id/student_no/student_number`，不能拿账号上的首个班级编号代替。

`POST /admin/classes` 示例（201 `{class,roster_count}`）：

```json
{"class":{"alias":"OS202601","name":"操作系统教学班","invite_enabled":true},"course":{"name":"操作系统","code":"OS","semester":"2026秋"},"roster":[]}
```

`PATCH /admin/classes/{class_id}` 接收嵌套 `class.name/invite_enabled`、`course.name/code/semester`，不修改别名。`GET /admin/classes` 返回 `{classes}`；教师仅自己的班级，管理员可查看全部。

`POST /admin/classes/import-excel`：multipart `class_id` + `file`（`.xlsx/.xlsm`）。Excel 必须含 No.、学号、姓名、班级；课程名称/课程号/学期更新课程内部字段，Excel 班级只保存为学生信息。成功 201 `{course_id,class_id,imported_count,updated_count}`。不要将真实名单纳入仓库。

`GET /admin/classes/{class_id}/roster` 返回 `{class,roster}`；POST 同路径新增，接收 `student_name/student_no/student_number/source_class`，返回 201 `{entry}`。PATCH `/admin/roster/{entry_id}` 接收相同字段，DELETE 删除未绑定名单项；已绑定账号时更新/删除返回 409。

`GET /admin/teachers?status=pending` 返回 `{teachers}`；PATCH `/admin/teachers/{teacher_id}/status` 接收 `{"status":"approved"}` 或 `rejected`，返回 `{teacher}`，仅管理员。

## 作业创建与发布

### 作业资料（独立主说明与附件）

- 主说明始终使用Assignment的`description/description_format`和既有Markdown说明草稿接口，附件不替代主说明。
- `POST /teacher/code-templates/validate`：仅已审批教师，multipart `file`，返回200 `{template:{id,filename,file_size,content,purpose:""}}`，只校验不保存。支持UTF-8（允许BOM）`.py/.md`，单个1MiB，禁止路径、无效文件名、空白和二进制控制字符，不会编译或运行。
- 创建/更新作业传`code_templates:[{filename,content,purpose?}]`，最多4个附件，主说明不计数。用途为可选单行文字，最多120字，服务端去除首尾空白；文件名大小写不敏感且不得重复。`is_main:true`不再接受，禁止附件充当主说明。服务端重算SHA256派生ID及大小，重命名会改变ID。创建省略为空，更新省略保留，传[]移除全部；修改已发布作业仍通过require_resubmission选择是否重交。
- 作业列表仅返回`code_templates:[{id,filename,file_size,purpose,url,preview_url}]`；`GET /admin/assignments/{id}/code-templates`仅所属已审批教师，返回`{templates}`完整正文供编辑，接口保留原code-templates名称。
- `GET /assignments/{id}/code-templates/{template_id}/preview`返回`{template:{id,filename,file_size,content,purpose}}`；`/download`返回UTF-8附件（.md为text/markdown、.py为text/x-python）。二者均仅所属教师或已发布作业的本班学生可读，private/no-store、nosniff；下载另设置attachment。学生草稿/越权/非法或移除ID为404，未审批教师403。
- Markdown附件配图须使用本人教师图片库，保存时校验归属，读取/删除引用保护包括所有Markdown附件；不自动上传本地图片或运行原始HTML。
- 数据迁移`c9e53f10642d`仅取消旧is_main标记并补充purpose，保留原description、说明草稿及全部附件ID/正文，不用自动选中的Markdown覆盖原说明。历史5附件全部保留，再次编辑保存须整理到4个以内。无数据库结构变化，不改学生提交或成绩。AI上下文只使用独立description。

GET/POST `/admin/classes/{class_id}/assignments`；PATCH/DELETE `/admin/assignments/{assignment_id}`；POST `/admin/assignments/{assignment_id}/publish`。创建返回 201 `{assignment}`，更新/发布返回 200 `{assignment,...}`。当前 type 为 `homework` 或 `lab_report`，状态为 `draft`/`published`，描述/rubric 格式仅 `markdown`。

创建示例：

```json
{
  "title":"第一次 Python 作业","code":"hw1","type":"homework",
  "status":"draft","description":"程序输出 hello","max_score":100,
  "deadline":"2026-11-01T23:59:59+08:00","allow_late":false,
  "file_rules":{"allowed_extensions":[".py"],"max_size_mb":5,"filename_template":"{student_id}_{assignment_code}{extension}"},
  "submission_requirements":[{"key":"main","label":"Python 源码","required":true,"allowed_extensions":[".py"],"max_size_mb":5,"filename_template":"{student_id}_{assignment_code}{extension}"}],
  "program_evaluations":[{"name":"输出检查","input_file_key":"main","cases":[{"name":"hello","args":"","expected_output":"hello","score_percent":100,"timeout_seconds":2,"is_hidden":true}]}],
  "ai_evaluations":[],"rubric":{"text":"按测试点评分"}
}
```

- code 为 1–40 位字母/数字/下划线/连字符，首位字母或数字，同教学班唯一。max_score > 0。
- 提交项 key 同样为 1–40 位，同作业唯一；文件模板支持 `{student_id}`、`{student_no}`、`{name}`、`{assignment_code}`、`{extension}`；单项大小 0 < max_size_mb ≤ 64。
- 当前代码支持 `.py/.md/.zip/.jpg/.png`；首期 PRD 只要求 `.py/.md`，生产作业请显式收窄白名单。ZIP/图片仅存储、预览或人工批改，Python 评测只跑 `.py`。
- program_evaluations 指定提交项及 cases，每 case 传 args（shell 风格分词，但不经过 shell 执行）、expected_output、score_percent、timeout_seconds、is_hidden。当前没有 stdin 输入接口。
- ai_evaluations 模块指定 name/input_file_key/score_percent/input/criteria_items，criteria_items 为 `[{"content":"论述完整","weight":100}]`；权重均须为正。必交提交项权重合计100%，程序/AI模块按文件引用的占比必须匹配对应提交项权重，服务端校验并控制文件满分；不再按旧版“自动占比不足即随意留下人工余分”规则理解。
- late_policy 保存说明文本，不能认为已实现自动迟交扣分。
- 更新已发布过的作业时传布尔 `require_resubmission`：`false` 保留提交、文件、成绩及原发布时间，即使修改提交项也保留此前已完成状态；`true` 清空批改并将文件置为待确认，保留文件和在线草稿供学生重新确认，不立即重跑。前端保存草稿使用false，重新发布时让教师选择；`POST /publish` 同样支持此字段。旧客户端未传新字段时保留原409确认和 `reset_grading:true` 重评兼容行为。删除作业仍删除提交、文件和批改记录。

## 学生上传与确认

GET `/classes/{class_id}/assignments` 返回该班已发布作业和个人提交信息；POST `/assignments/{assignment_id}/read` 记录已读，返回 `{read,assignment}`。

POST `/assignments/{assignment_id}/submissions`：multipart `file` + `item_key`（兼容 submission_item_key），成功 201 `{submission,assignment_grade}`。无 item_key 的兼容行为不适用于多提交项，请始终显式传。服务端校验班级成员、roster 编号、文件类型/内容、命名与截止时间。

**上传后还必须 POST `/assignments/{assignment_id}/confirm-submission`**，无请求体。必交文件齐全且再次验证通过才确认并排入批改队列，返回 `{assignment,assignment_grade,queue_status}`。queue_status 是 `queued` 或测试内联 `inline`，不代表最终成绩已发布。已发布反馈阻止学生再次提交；教师可退回后重新提交。

```bash
BASE=https://judge.example.cn
# 以下仅演示字段；避免将真实密码写入脚本或 shell 历史。
curl -c cookies.txt -H "Origin: $BASE" -H 'Content-Type: application/json' \
  --data @login.json "$BASE/api/auth/login"
curl -b cookies.txt -H "Origin: $BASE" -F 'item_key=main' \
  -F 'file=@OS202601-06_hw1.py' "$BASE/api/assignments/1/submissions"
curl -b cookies.txt -H "Origin: $BASE" -X POST "$BASE/api/assignments/1/confirm-submission"
```

## 教师批改与成绩

- GET `/admin/assignments/{assignment_id}/submissions`：`{assignment,analysis,submissions}`，按 roster 展示已读/上传/提交状态、各项提交和作业级成绩。
- GET `/admin/submissions/{submission_id}/preview`：`{submission,previewable,content}` 或不可预览说明；GET `/download` 为鉴权后的文件附件，不是公开上传目录。
- POST `/admin/submissions/{submission_id}/rerun-grading`：重新排入自动批改，必须已确认提交，返回 `{submission,assignment_grade,queue_status}`。
- POST `/admin/submissions/{submission_id}/return`：退回重交，返回 `{message,assignment,cleanup}`，会清理该学生作业记录/文件和成绩；不是保留所有旧版本的无损操作。
- PATCH `/admin/submissions/{submission_id}/grade`：`{final_score,status,teacher_comment,feedback,reason,file_reviews}`，final_score 在 0..max_score，status 为 `reviewed`（默认）或 `published`。返回 `{submission,assignment_grade,grading_result}`；成绩实际上归属整份作业+学生，不是单文件独立成绩。file_reviews 的详细规范由 `_normalize_file_reviews` 校验；简单人工批改可仅传 final_score/status/teacher_comment。
- AI/程序分数均是辅助数据。只有 status=published 时学生能看到最终成绩与反馈；导出则允许 reviewed 和 published。

GET `/admin/assignments/{assignment_id}/grades` 返回 `{assignment,class,analysis,rows}`；analysis 包含完成人数、平均分、发布后/截止前平均提交天数等，rows 包含 roster、student_state、submitted_at、assignment_grade、exportable。

GET `/admin/assignments/{assignment_id}/grades.csv?score_factor=1` 返回 UTF-8 BOM CSV 附件，独立列出原始成绩、比例因子、最终成绩。GET `/scoremanager-commands?field=homework&command_type=regular&group_same_score=true&score_factor=1` 返回 `{assignment,export}`：export 含score_factor、commands（文本）、lines（列表）、exported_count、skipped。比例因子默认1，必须为0到1000之间的有限数字，非法400；使用Decimal乘法和ROUND_HALF_UP，折算结果固定两位小数，仅导出已复核/已发布成绩，不写回原始分数或影响统计。command_type为regular/lab（兼容type），普通默认homework，实验默认作业code；合并同分时分别使用brd/lab brd，按折算后成绩分组。非法学生编号阻止导出（400），无最终成绩名单列于skipped。前端支持复制全部命令，下载的TXT追加`exit -s`供手动批量导入并保存退出；平台不调用CLI，重复导入可能重复记分。

## 指定学生补交

`PATCH /admin/assignments/{assignment_id}/students/{roster_id}/makeup`，JSON `{"allowed":true}` 开放、false撤销，仅所属教师可操作。只允许已截止且已发布的作业，名单项须已绑定并加入本班；未截止、无截止或未注册400，他班/他教师404，已完成或已有已发布反馈409（需先退回）。返回`{makeup_allowed}`。

学生收到权限后可上传文件、在线编辑/插图及确认；一次成功确认后权限消耗，仍受班级、文件及已发布成绩校验约束。Submission保留实际submitted_at，新增is_makeup及effective_submitted_at：补交时后者冻结为确认时作业截止日期。教师列表行新增submitted_at（完成时间/补交有效时间）、is_makeup、makeup_allowed；学生Assignment新增makeup_allowed、submission_complete和submission_preserved。指标和CSV使用有效时间并标注补交；旧提交有效时间回退submitted_at。补交授权期间未完成的学生计入待提交，00仍不参与班级统计与导出。

## 教师 DeepSeek 配置

GET/PUT `/admin/llm-config`，仅教师自身。PUT 为 `{base_url,model,api_key,enabled,provider}`，base_url/model 必填，首次必须传 api_key，后续省略或空值保留旧 key。当前 provider 默认 deepseek，调用走兼容 chat/completions 协议，不因 provider 字段自动切换 SDK。

响应 `{config}` 仅展示 `has_api_key`，不返回明文/密文。生产配置有 LLM_ENCRYPTION_KEY 时使用 Fernet 加密保存；旧明文需执行 `encrypt-llm-keys`。API 异常/JSON 解析失败留待人工处理。base_url 由教师配置，尚未对目标主机实施严格网络白名单，只应审批可信教师。

## 在线Markdown及私有图片（当前版本）

- POST `/markdown-documents`：JSON `{class_id,assignment_id,kind,item_key}`，kind为description或submission，返回`{document}`；教师新说明可以尚无assignment_id。
- GET `/markdown-documents/{id}`读取本人草稿；PUT同路径传`{content,revision}`自动保存，版本冲突409，正文至多1MiB并受学生提交项限制。保存草稿不等于确认提交。
- POST `/markdown-documents/{id}/images`：multipart file，仅PNG/JPEG，成功201 `{asset:{id,url,filename}}`。每图5MiB、1000万像素；每文档50张/50MiB。
- GET `/assets/{id}/content`：登录且满足文档/快照访问权限后返回图片，Cache-Control为private,no-store。不能公开代理、跨账号缓存或直接暴露上传目录。
- 学生确认整份提交会生成不可变.md快照及图片引用；教师只能读取已确认快照引用的报告图片。教师说明图需已保存并发布，且属于该班学生才可读取；管理员不自动绕过图片权限。
- 程序评测仍只运行.py；AI以Pydantic验证逐rubric结构并重算汇总，只读文本，不识别图片。数据库与所有图片必须共同备份，导出的.md本身不包含图片二进制。


## 作业复用与教师图片库（2026-10-11）

- `POST /admin/assignments/{id}/copy`：教师传 `{ "class_id": 目标班ID, "code": "hw1" }`，code可省略沿用来源。仅允许同一教师的两个不同教学班，返回201 `{assignment}`（草稿）。代码冲突409；目标越权404。只复制设置，图片复用原URL，学生数据不复制。
- `GET /teacher/images`：已审批教师返回 `{assets:[{id,url,filename,file_size}]}`，仅自己的图片。
- `POST /teacher/images`：multipart `file`，返回201 `{asset}`。PNG/JPEG、5MB/张、1000万像素；教师库上限1000张/500MB。原文档上传接口的说明图片也自动进入库。
- `DELETE /teacher/images/{id}`：只能删除自己的未引用图片；仍有说明/草稿/历史提交引用返回409，越权404。
- `GET /assets/{id}/content`：教师库图片供本人或引用它的已发布作业所在班级的学生读取，其他人404。学生报告图片仍沿用文档及已提交快照权限。
- `POST /admin/classes/import-excel` 新增表单字段 `preview=true`：只解析返回200 `{student_count}`，不修改名单/课程；正式导入传 `mode=append`（默认，只新增）或 `replace`（更新未绑定项并删除文件中不存在的未绑定项）。返回新增 `removed_count`、`preserved_registered_count`；已绑定项不会覆盖或删除，姓名/学号冲突409。
- 教师作业计数、成绩分析、CSV与ScoreManagerCLI导出排除当前教学班编号00；名单查询仍返回00。`GET /admin/assignments/{id}/submissions` 的 `submissions` 仅含普通学生，新增 `test_submissions` 单独返回00名单项（未提交时也返回），结构相同并支持现有预览、批改、重测和退回接口；没有00时为 `[]`。
- `deadline` 中带时区的输入在写库前统一转UTC，前端固定使用北京时间+08:00；无时区API输入仍按UTC兼容旧调用方。


## 学生图片库（2026-10-11）

`GET /student/images`、`POST /student/images`（multipart file）及`DELETE /student/images/{id}`与教师图片库响应结构一致，仅学生本人可管理；教师端路径仍只允许教师使用，不能用切换路径跨角色访问。新字段markdown_assets.student_user_id通过迁移f5b20c8d316a回填既有报告图片所有者。GET图片内容允许学生本人，教师只有在自己的已确认作业快照中实际引用该图片时可读；其他学生及不相关教师404。图片可跨自己的报告复用，删除引用中的图片409。独立库上传不受某次作业截止限制；作业草稿编辑、图片上传与确认仍执行截止/补交权限/成绩发布限制。学生个人库1000张/30MB（教师仍500MB），报告引用50张/50MB；旧库超额不删图，禁止新增直到释放容量。两种上传路径共用配额检查。

直接上传.md而未打开在线编辑器时，确认提交也会解析库图片引用并记录快照引用ID，执行相同所有权及配额检查；不接受本地或外部图片引用。旧的个人图片自动归库后不再被未引用图片定时清理删除。
