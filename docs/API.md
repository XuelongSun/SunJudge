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
- ai_evaluations 模块指定 name/input_file_key/score_percent/input/criteria_items，criteria_items 为 `[{"content":"论述完整","weight":100}]`；权重均须为正，程序+AI评分占比总和不能超过 100，剩余分数由教师判断。
- late_policy 保存说明文本，不能认为已实现自动迟交扣分。
- 已发布作业有批改数据时，修改返回 409 `requires_reset_grading=true`；显式传 `reset_grading:true` 会清除既有批改并重排任务。删除作业会同时删除学生提交、对应文件与相关批改记录。调用前务必理解这些业务副作用。

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

GET `/admin/assignments/{assignment_id}/grades.csv` 返回 UTF-8 BOM CSV 附件。GET `/scoremanager-commands?field=homework&command_type=regular&group_same_score=true` 返回 `{assignment,export}`：export 含 commands（文本）、lines（列表）、exported_count、skipped。command_type 为 regular/lab（兼容 type），普通默认 homework，实验默认作业 code；普通同分默认 brd，实验逐条 lab rd。非法学生编号阻止导出（400），无已复核/已发布最终分的名单列于 skipped。只生成文本，从不调用 CLI。

## 教师 DeepSeek 配置

GET/PUT `/admin/llm-config`，仅教师自身。PUT 为 `{base_url,model,api_key,enabled,provider}`，base_url/model 必填，首次必须传 api_key，后续省略或空值保留旧 key。当前 provider 默认 deepseek，调用走兼容 chat/completions 协议，不因 provider 字段自动切换 SDK。

响应 `{config}` 仅展示 `has_api_key`，不返回明文/密文。生产配置有 LLM_ENCRYPTION_KEY 时使用 Fernet 加密保存；旧明文需执行 `encrypt-llm-keys`。API 异常/JSON 解析失败留待人工处理。base_url 由教师配置，尚未对目标主机实施严格网络白名单，只应审批可信教师。
