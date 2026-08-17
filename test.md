# SunJudge Test Guide

> 本文件只记录测试方法。技术实现、代码逻辑和里程碑说明见 `tutorial.md`。

## 1. 自动化检查

### 1.1 后端 pytest

```bash
cd backend
uv run pytest
```

覆盖重点：

- 学生编号格式校验。
- Excel 中 `序号 / 学号 / 姓名 / 班级` 的解析。
- 学生注册必须匹配 `教学班别名-两位No.`。
- 学生真实姓名和 No. 必须匹配名单。
- 学生可使用真实姓名或任一已绑定学生编号登录。
- 学生注册后按真实姓名和学号自动绑定多个班级。
- 教师申请和管理员审批。
- 管理员查看全部教师和教学班。
- 教师创建教学班。
- Excel 名单导入。
- 名单在线增删改查。

### 1.2 后端语法检查

```bash
cd backend
uv run python -m compileall app tests
```

用途：只检查 Python 文件语法和导入期基础错误，不执行接口流程。

### 1.3 前端构建检查

```bash
cd frontend
npm run build
```

用途：执行 `vue-tsc -b` 和 `vite build`，检查 TypeScript、Vue 模板和构建流程。

## 2. Bruno 接口测试

建议新建 Bruno Collection：

- Base URL：`http://127.0.0.1:5000`
- JSON Header：`Content-Type: application/json`
- Cookie：登录后 Bruno 会保存 Flask-Login Session Cookie。

### 2.1 登录管理员

`POST {{baseUrl}}/api/auth/login`

```json
{
  "username": "admin",
  "password": "admin123"
}
```

管理员可查看教师和教学班，只用于教师审批，不用于创建教学班或维护名单。

### 2.2 注册并审批教师

先退出管理员，或清空 Cookie 后注册教师：

`POST {{baseUrl}}/api/auth/register`

```json
{
  "username": "teacher1",
  "password": "secret123",
  "role": "teacher"
}
```

重新登录管理员后查看教师：

`GET {{baseUrl}}/api/admin/teachers?status=pending`

`GET {{baseUrl}}/api/admin/teachers?status=all`

审批教师：

`PATCH {{baseUrl}}/api/admin/teachers/:teacherId/status`

```json
{
  "status": "approved"
}
```

### 2.3 登录教师并创建教学班

`POST {{baseUrl}}/api/auth/login`

```json
{
  "username": "teacher1",
  "password": "secret123"
}
```

`POST {{baseUrl}}/api/admin/classes`

```json
{
  "class": {
    "alias": "OS202601"
  },
  "roster": []
}
```

预期：

- 返回 `class.id`。
- `class.alias` 为 `OS202601`。
- `class.invite_code` 与别名相同，也是 `OS202601`。
- 课程名称、课程号和学期暂为待导入。

### 2.4 导入 Excel 名单

`POST {{baseUrl}}/api/admin/classes/import-excel`

Body 使用 Multipart Form：

- `class_id`：上一步返回的教学班 ID。
- `file`：根目录的 `students.xlsx`。

预期：

- 返回 `imported_count` 和 `updated_count`。
- Excel 前几行课程信息不会被当作学生行。
- 课程名称、课程号、学期会根据 Excel 更新。
- 学生编号会生成为 `OS202601-两位No.`，不是 `OS202601-长学号`。

### 2.5 查看教学班和名单

`GET {{baseUrl}}/api/admin/classes`

管理员和教师都可以查看教学班列表。管理员界面按教师折叠显示班级；名单明细接口只给教师管理自己班级时使用：

`GET {{baseUrl}}/api/admin/classes/:classId/roster`

重点检查字段：

- `student_no`：短序号 No.，例如 `06`。
- `student_number`：长学号。
- `source_class`：Excel 中的学生自然班级。
- `student_id`：`教学班别名-两位No.`，例如 `OS202601-06`。

### 2.6 在线新增名单项

`POST {{baseUrl}}/api/admin/classes/:classId/roster`

```json
{
  "student_name": "New Student",
  "student_no": "99",
  "student_number": "32999999999",
  "source_class": "信计251"
}
```

预期：返回的 `student_id` 为 `OS202601-99`。

### 2.7 在线修改名单项

`PATCH {{baseUrl}}/api/admin/roster/:entryId`

```json
{
  "student_name": "Updated Student",
  "student_no": "100",
  "student_number": "32100000000",
  "source_class": "信计251"
}
```

预期：未绑定账号的名单项可以修改；已绑定账号的名单项返回冲突错误。

### 2.8 在线删除名单项

`DELETE {{baseUrl}}/api/admin/roster/:entryId`

预期：未绑定账号的名单项可以删除；已绑定账号的名单项返回冲突错误。

### 2.9 学生注册

`POST {{baseUrl}}/api/auth/register`

```json
{
  "password": "secret123",
  "role": "student",
  "student_name": "student_name_1",
  "student_id": "OS202601-01"
}
```

预期：只有真实姓名和 `OS202601-01` 同时匹配已导入名单时，注册成功。

注册成功后可分别尝试以下登录名：

```json
{
  "username": "student_name_1",
  "password": "secret123"
}
```

```json
{
  "username": "OS202601-01",
  "password": "secret123"
}
```

如果该学生在其他教学班名单中有相同真实姓名和学号，也可用其他已绑定班级的学生编号登录。若真实姓名匹配多个账号且密码相同，预期返回冲突提示，此时应改用学生编号。
旧版本测试中填过的学生昵称（例如 `JaneAI`）不再作为学生登录名使用，预期登录失败；页面右上角应显示学生真实姓名。

建议再验证几个失败分支：

- `OS202601-1`：失败，因为邀请码要求两位数字 No.
- `OS202601-32319500084`：失败，因为注册使用 No.，不是长学号。
- 正确 No. 但真实姓名错误：失败，并提示姓名与名单记录不一致。
- 不存在的 No.：失败，并提示名单中不存在该 No.

## 3. 浏览器手动测试

本节只模拟用户在浏览器中的真实操作。

### 3.1 启动服务

后端：

```bash
cd backend
uv run flask --app app:create_app run --host 127.0.0.1 --port 5000 --debug
```

前端：

```bash
cd frontend
npm run dev
```

访问：

```text
http://127.0.0.1:5173/
```

### 3.2 M1 手测流程

1. 进入“注册 / 申请”，选择“教师”。
2. 注册教师账号 `teacher1 / secret123`，应提示等待审批。
3. 登录管理员：`admin / admin123`。
4. 管理员页面应看到教师列表；展开教师行后应看到该教师创建的教学班。不应看到创建教学班、导入名单或编辑学生入口。
5. 审批 `teacher1` 通过。
6. 退出管理员，登录教师：`teacher1 / secret123`。
7. 在教师工作台点击“添加班级”。
8. 在弹窗中填写班级别名 `OS202601` 并创建。
9. 教学班的邀请码应显示为 `OS202601`，与别名相同。
10. 在该教学班右侧点击“学生列表”。
11. 在学生列表抽屉中点击“导入名单”。
12. 在弹窗中选择根目录 `students.xlsx`。
13. 点击“导入”。
14. 重新打开或刷新学生列表。
15. 名单抽屉应出现：
    - No.
    - 长学号
    - 学生信息班级
    - 学生编号，例如 `OS202601-01`
16. 点击“新增学生”，在弹窗中填写 No.、长学号、姓名和学生信息班级。
17. 点击学生行右侧编辑按钮，在弹窗中编辑刚新增的学生，确认表格更新。
18. 删除刚新增的学生，确认表格删除。
19. 退出教师。
20. 进入“注册 / 申请”，选择“学生”。
21. 输入：
    - 真实姓名：`student_name_1`
    - 密码：`secret123`
    - 邀请码：`OS202601-01`
22. 注册应成功。
23. 学生页面应只显示已绑定班级列表，不应自动展开任何班级详情。
24. 点击班级后，右上角仍只显示绿色“学生”和真实姓名，主界面显示该班级内学生身份和作业区域。
25. 若该班级暂无作业，作业区域只显示“暂无作业”，页面宽度不应持续变宽。
26. 分别使用真实姓名 `student_name_1`、学生编号 `OS202601-01` 登录，均应成功。
27. 重新尝试以下失败分支：
    - 邀请码 `OS202601-1`
    - 邀请码 `OS202601-32319500084`
    - 正确邀请码但真实姓名错误

### 3.3 后续里程碑扩展位

M2 后补充：

- 教师发布作业。
- 学生提交 `.py` / `.md`。
- 文件大小、命名模板和班级成员校验。

M3 后补充：

- Python 自动评测。
- LLM 辅助评分。
- 教师复核。

M4 后补充：

- 成绩发布。
- CSV 导出。
- ScoreManagerCLI 命令导出。

## 4. 常见排查

### 4.1 5173 找不到页面

确认浏览器地址栏是：

```text
http://127.0.0.1:5173/
```

不要带中文逗号或句号。

如果 5173 被占用，当前 Vite 会因 `--strictPort` 直接报错。停止占用进程后再运行。

Windows PowerShell：

```powershell
$pid5173 = Get-NetTCPConnection -LocalPort 5173 | Select-Object -First 1 -ExpandProperty OwningProcess
Stop-Process -Id $pid5173
```

Linux / Ubuntu：

```bash
lsof -ti :5173 | xargs -r kill
```

### 4.2 SQLite 数据查看

本地数据库：

```text
backend/instance/sunjudge.sqlite
```

可用 Navicat 选择 SQLite 连接查看。

重点表：

- `users`
- `courses`
- `classes`
- `class_rosters`
- `course_members`
- `audit_logs`

## 5. M2 作业管理测试补充

### 5.1 自动化测试

后端新增 `backend/tests/test_assignments.py`，覆盖以下 M2 闭环：

- 教师可创建作业草稿，并可发布作业。
- 草稿作业对学生不可见，发布后学生可在所属教学班中看到。
- 学生提交文件时必须满足扩展名、大小、命名模板和 UTF-8 文本规则。
- 学生只能提交自己所属教学班的作业，非成员不能提交。
- 教师可按名单查看每名学生的提交状态，区分“已提交 / 未提交”。

运行：

```bash
cd backend
uv run pytest
```

本次 M2 开发验证结果：`28 passed`。

### 5.2 前端检查

常规环境可运行：

```bash
cd frontend
npm run build
```

当前开发环境中 `npm` 未在 PATH 内，已使用本地 Node 直接验证：

```powershell
cd frontend
node .\node_modules\vue-tsc\bin\vue-tsc.js --noEmit --incremental false
node .\node_modules\vite\bin\vite.js build
```

验证结果：类型检查通过，Vite 构建通过。Vite 仅提示生产包 chunk 较大，属于后续优化项。

### 5.3 M2 接口手动测试

前置条件：已有管理员、已审批教师、教师已创建教学班并导入名单，学生已按 `教学班别名-两位No.` 注册并绑定该班级。

教师创建草稿：

`POST {{baseUrl}}/api/admin/classes/:classId/assignments`

```json
{
  "title": "Homework 1",
  "code": "hw1",
  "type": "report",
  "description": "Write a short report.",
  "max_score": 100,
  "status": "draft",
  "file_rules": {
    "allowed_extensions": [".md"],
    "max_size_mb": 1,
    "filename_template": "{student_id}_{assignment_code}{extension}"
  },
  "rubric": {
    "text": "Completeness 60, clarity 40."
  }
}
```

预期：返回 `status=draft`。此时学生调用 `GET /api/classes/:classId/assignments` 不应看到该作业。

教师发布作业：

`POST {{baseUrl}}/api/admin/assignments/:assignmentId/publish`

预期：返回 `status=published`，学生可在班级作业列表看到该作业。

学生提交文件：

`POST {{baseUrl}}/api/assignments/:assignmentId/submissions`

Multipart Form：

- `file`: 例如 `OS202601-06_hw1.md`

预期：

- 正确文件返回 201，`validation_result.ok=true`。
- `.py` 提交到仅允许 `.md` 的作业应返回 400。
- 文件名不是模板渲染结果，例如 `Alice_hw1.md`，应返回 400，并提示期望文件名。
- 非本教学班成员提交应返回 404 或无权限响应。

教师查看提交状态：

`GET {{baseUrl}}/api/admin/assignments/:assignmentId/submissions`

预期：按 roster 名单返回每名学生，未提交显示 `state=missing`，已提交显示 `state=submitted` 和文件名、提交时间、大小。

### 5.4 M2 浏览器手动验收

教师端：

1. 登录已审批教师账号。
2. 在教学班列表中查看“作业”数量，应显示真实 `assignment_count`。
3. 点击“发布作业”，填写标题、代码、类型、截止时间、允许扩展名、大小上限、命名模板和 rubric。
4. 点击“保存草稿”，作业应出现在“作业列表”抽屉中，状态为“草稿”。
5. 点击“发布”，状态应变为“已发布”。
6. 点击“提交状态”，应按名单看到每名学生的提交情况。

学生端：

1. 登录已绑定该教学班的学生账号。
2. 进入对应班级，发布后的作业应出现在作业表格中。
3. 点击“提交”，上传符合命名规则的 `.py` 或 `.md` 文件。
4. 提交成功后，作业状态应从“未提交”变为“已提交”或“已迟交”。
5. 上传错误扩展名、超大文件或错误命名文件时，应看到后端返回的明确错误提示。

### 5.5 M2 细化需求验收

本轮细化后，作业类型只保留：

- `homework`：作业
- `lab_report`：实验报告

程序评测和 AI 评测不再通过作业类型决定，而是教师在作业表单中按需添加的评测模块。若两个模块列表都为空，该作业即为手动批改。

教师端手测：

1. 新建作业时，类型下拉框只应看到“作业 / 实验报告”。
2. 点击“添加程序评测”，可新增多个程序评测模块。
3. 每个程序评测模块应可填写名称、输入、期望输出、成绩占比、超时秒数和是否隐藏。
4. 点击“添加 AI 评测”，可新增多个 AI 评测模块。
5. 每个 AI 评测模块应可填写名称、指定输入、评分标准和成绩占比。
6. 程序评测和 AI 评测总占比超过 100 时，后端应拒绝保存。
7. 不添加任何程序评测和 AI 评测时，应能正常保存并发布，表示教师后续手动批改。
8. 作业说明和评分标准都应有 `TXT / Markdown` 编辑方式切换。

学生端手测：

1. 班级列表应显示每个班级的待提交作业数量。
2. 班级列表不再显示操作列；点击整行进入班级，并高亮当前行。
3. 进入班级后，作业列表不显示作业代码、作业类型和操作列。
4. 点击作业整行后，应高亮当前作业，并显示作业详情。
5. 如果作业说明或评分标准使用 Markdown，学生详情页应显示渲染结果，而不是原始 Markdown 文本。
6. 提交按钮位于作业详情页。
7. 学生可提交 `.py`、`.md`、`.zip`、`.jpg`、`.png`，前提是该作业允许对应扩展名且文件名匹配模板。
8. 教师在作业列表中点击“预览”，应看到与学生详情页一致的作业说明、评分标准和文件规则渲染结果，并能看到程序评测 / AI 评测模块摘要。
9. 教师在新建或编辑作业弹窗中点击“预览”，应按当前尚未保存的表单内容即时生成预览。

接口补充：

创建作业时可传入评测模块：

```json
{
  "title": "Homework 1",
  "code": "hw1",
  "type": "homework",
  "description": "# 要求\n完成报告。",
  "description_format": "markdown",
  "rubric": {
    "text": "## 标准\n- 完整性 60\n- 清晰度 40"
  },
  "rubric_format": "markdown",
  "program_evaluations": [
    {
      "name": "case 1",
      "input": "1 2",
      "expected_output": "3",
      "score_percent": 30,
      "timeout_seconds": 2,
      "is_hidden": false
    }
  ],
  "ai_evaluations": [
    {
      "name": "report quality",
      "input": "Read the submitted report.",
      "grading_criteria": "Evaluate clarity and completeness.",
      "score_percent": 20
    }
  ],
  "file_rules": {
    "allowed_extensions": [".py", ".md", ".zip", ".jpg", ".png"],
    "max_size_mb": 5,
    "filename_template": "{student_id}_{assignment_code}{extension}"
  },
  "max_score": 100,
  "allow_late": false,
  "status": "published"
}
```

本次细化验证结果：

- 后端：`29 passed`
- 前端类型检查：通过
- Vite 构建：通过，仅保留 chunk size 警告

教师预览功能补充验证：

- `vue-tsc --noEmit --incremental false`：通过
- `vite build`：通过，仅保留 chunk size 警告

### 5.6 班级信息接口回归检查

如果本地数据库已经创建了第一版 `assignments` 表，但还没有执行后续细化迁移，`/api/admin/classes` 和 `/api/classes/my` 不能因为缺少 `description_format/rubric_format/program_evaluations_json/ai_evaluations_json` 等新列而失败。

回归检查：

```bash
cd backend
uv run pytest
```

也可在不启动服务的情况下直接检查当前 SQLite：

```bash
cd backend
uv run python -c "from app import create_app; from app.models import CourseClass; app=create_app(); app.app_context().push(); print([c.to_admin_dict() for c in CourseClass.query.all()])"
```

预期：班级列表能够正常序列化，`assignment_count/pending_assignment_count` 使用轻量统计，不懒加载完整 `Assignment` 行。

当 SQLAlchemy model 新增字段后，必须先升级本地 SQLite：

```bash
cd backend
uv run flask --app app:create_app db upgrade
```

可检查 `assignments` 表是否包含新增列：

```bash
cd backend
uv run python -c "from app import create_app; from app.extensions import db; app=create_app(); app.app_context().push(); print([row[1] for row in db.session.execute(db.text('PRAGMA table_info(assignments)')).fetchall()])"
```

本次修复后应包含：

- `description_format`
- `rubric_format`
- `program_evaluations_json`
- `ai_evaluations_json`
