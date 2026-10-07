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

- 教师端成绩统计与成绩簿接口。
- CSV 导出。
- ScoreManagerCLI 命令导出。
- 学生端分班级作业总览。

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
5. 每个 AI 评测模块应可填写名称、指定输入、成绩占比，并可新增多个评分项目；每个评分项目包含内容标准和权重。
6. 程序评测和 AI 评测总占比超过 100 时，后端应拒绝保存。
7. 不添加任何程序评测和 AI 评测时，应能正常保存并发布，表示教师后续手动批改。
8. 作业内容应只保留 Markdown 编辑和实时预览，不再显示 `TXT` 模式或独立评分标准输入。

学生端手测：

1. 班级列表应显示每个班级的待提交作业数量。
2. 班级列表不再显示操作列；点击整行进入班级，并高亮当前行。
3. 进入班级后，作业列表不显示作业代码、作业类型和操作列。
4. 点击作业整行后，应高亮当前作业，并显示作业详情。
5. 作业内容 Markdown 应显示渲染结果，而不是原始 Markdown 文本。
6. 提交按钮位于作业详情页。
7. 学生可提交 `.py`、`.md`、`.zip`、`.jpg`、`.png`，前提是该作业允许对应扩展名且文件名匹配模板。
8. 教师在作业列表中点击“预览”，应看到与学生详情页一致的作业内容和文件规则渲染结果；存在程序评测 / AI 评测时才显示模块摘要。
9. 教师在新建或编辑作业全屏工作区中点击“预览”，应按当前尚未保存的表单内容即时生成预览。

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
      "criteria_items": [
        {
          "content": "Evaluate clarity and completeness.",
          "weight": 100
        }
      ],
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

## 6. M3 自动批改与教师复核测试补充

### 6.1 自动化测试

新增 `backend/tests/test_m3_grading.py`，覆盖：

- `.py` 提交后创建 `judge_runs` 和 `grading_results.auto_score`。
- 教师可保存最终分、反馈、教师评语和复核状态。
- 教师 LLM 配置接口不回显 API Key，只返回 `has_api_key`。

推荐运行：

```bash
cd backend
uv run pytest
```

本轮环境验证记录：

- `python -c "ast.parse(...)"` 静态解析后端 `app/tests` 共 24 个 Python 文件：通过。
- `uv run pytest` / `uv --no-cache run pytest`：当前机器 `.venv\Scripts\python.exe` 无法启动，测试入口被环境阻塞。
- `python -m compileall app tests`：语法阶段未发现语法错误，但写入既有 `__pycache__` 时被权限拒绝。

### 6.2 前端检查

常规运行：

```bash
cd frontend
npm run build
```

本轮环境验证记录：

- 使用 bundled Node 执行 `vue-tsc --noEmit --incremental false`：通过。
- `vite build --configLoader runner`：代码转换阶段通过，最终写入 `dist` 或新建 `build-check` 目录时被当前沙箱权限拒绝。

### 6.3 M3 接口手动测试

前置条件：教师已审批，已创建教学班并导入名单，学生已注册并加入班级。

教师创建包含代码和报告两个提交项的作业：

```json
{
  "title": "Python + Report",
  "code": "exp1",
  "type": "homework",
  "max_score": 100,
  "status": "published",
  "file_rules": {
    "allowed_extensions": [".py"],
    "max_size_mb": 1,
    "filename_template": "{student_id}_{assignment_code}{extension}"
  },
  "submission_requirements": [
    {
      "key": "code",
      "label": "Python 源代码",
      "allowed_extensions": [".py"],
      "max_size_mb": 1,
      "filename_template": "{student_id}_{assignment_code}_code{extension}",
      "required": true
    },
    {
      "key": "report",
      "label": "实验报告",
      "allowed_extensions": [".md"],
      "max_size_mb": 5,
      "filename_template": "{student_id}_{assignment_code}_report{extension}",
      "required": true
    }
  ],
  "rubric": { "text": "通过测试用例。" },
  "program_evaluations": [
    {
      "name": "sample",
      "input_file_key": "code",
      "cases": [
        {
          "name": "case 1",
          "args": "1 2",
          "expected_output": "3\n",
          "score_percent": 30,
          "timeout_seconds": 2,
          "is_hidden": false
        },
        {
          "name": "case 2",
          "args": "5 8",
          "expected_output": "13\n",
          "score_percent": 30,
          "timeout_seconds": 2,
          "is_hidden": true
        }
      ]
    }
  ],
  "ai_evaluations": [
    {
      "name": "report quality",
      "input_file_key": "report",
      "input": "阅读实验报告。",
      "criteria_items": [
        {
          "content": "评价步骤完整性。",
          "weight": 40
        },
        {
          "content": "评价结果分析和表达清晰度。",
          "weight": 60
        }
      ],
      "score_percent": 40
    }
  ]
}
```

学生提交代码：

`POST /api/assignments/:assignmentId/submissions`

Multipart:

- `item_key`: `code`
- `file`: `OS202601-06_exp1_code.py`

学生提交报告：

`POST /api/assignments/:assignmentId/submissions`

Multipart:

- `item_key`: `report`
- `file`: `OS202601-06_exp1_report.md`

预期：

- 代码提交返回的 `submission.submission_item_key=code`。
- 报告提交返回的 `submission.submission_item_key=report`。
- `GET /api/classes/:classId/assignments` 返回的作业里包含 `submissions` 数组，两个提交项均有最新提交后，该作业才算已提交。
- 教师提交状态接口返回每名学生的 `submissions` 列表和 `assignment_grade`。
- Docker 可用且代码输出正确时，`latest_judge_run.status=accepted`。
- `assignment_grade.status=auto_graded`，`auto_score` 按程序评测模块折算；AI 外部调用未启用时，AI 部分记录为等待人工复核。
- Docker 不可用时，评测状态为 `error`，不会使用宿主机 Python 裸跑。

教师重跑自动批改：

`POST /api/admin/submissions/:submissionId/rerun-grading`

预期：生成新的 `judge_runs`，提交状态里显示最新一次评测结果。

教师复核：

`PATCH /api/admin/submissions/:submissionId/grade`

```json
{
  "final_score": 88,
  "feedback": "整体正确。",
  "teacher_comment": "建议补充解题思路。",
  "reason": "人工复核调整",
  "status": "reviewed"
}
```

预期：

- 返回 `assignment_grade.final_score=88`。
- `teacher_comment` 保存成功。
- `status=reviewed`。
- `audit_logs` 中有 `grade_reviewed` 记录，目标类型为 `assignment_grade`，包含修改前和修改后。

教师 LLM 配置：

`PUT /api/admin/llm-config`

```json
{
  "provider": "deepseek",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "api_key": "sk-xxx",
  "enabled": true
}
```

预期：

- 返回 `has_api_key=true`。
- 响应体不包含 API Key 原文。
- 当前版本不会实际外发学生 Markdown；AI 评测会提示等待外部调用授权并要求教师人工复核。

### 6.4 M3 浏览器手动验收

教师端：

1. 登录教师账号。
2. 点击顶部“LLM 配置”，填写 base URL、模型和 API Key 后保存。
3. 创建或编辑作业，作业内容应只显示 Markdown 编辑器，并在右侧实时预览渲染结果。
4. 在“需提交文件”中点击“添加提交项”，弹窗添加至少两个提交项，例如 `code` 和 `report`；列表中应显示类型、大小、模板和必交状态摘要。
5. 点击“添加程序评测”，在弹窗中选择输入文件 `code`，再点击“增加测试用例”，分别填写输入、输出、分值占比、超时和隐藏设置。
6. 点击“添加 AI 评测”，在弹窗中选择输入文件 `report`，填写指定输入和占比，并新增多个评分项目；每个评分项目应包含内容标准和权重。
7. 学生分别提交代码文件和报告文件后，教师进入“作业列表” -> “提交状态”。
8. 表格应按学生显示所有已提交文件、评测状态、自动分、最终分、批改状态和反馈。
9. 点击“重跑”，应按评测模块绑定的输入文件重新组织批改。
10. 点击“复核”，修改最终分、反馈和教师评语。
11. 保存后表格应显示最终分和“已复核”。

学生端：

1. 进入已发布作业详情。
2. “需提交文件”表格应显示每个提交项的允许类型、大小、命名模板、状态和最近文件。
3. 对每个提交项点击“提交”，上传匹配该提交项规则的文件。
4. 只提交其中一个必交项时，作业列表仍显示未完成；所有必交项都提交后才显示已提交。

当前限制：

- LLM 外部调用尚未启用；需要明确授权学生提交内容可发送到教师配置的 OpenAI 兼容接口后再接入。
- Docker 未安装或镜像不可用时，程序评测会记录错误状态。

### 6.5 本地 SQLite 迁移检查

本轮已执行：

```bash
cd backend
python migrate_sqlite_m3.py
```

检查结果：

```text
alembic_version = 0b7d4c2a9e11
```

已确认存在：

- `teacher_llm_configs`
- `judge_runs`
- `grading_results`
- `assignment_grades`

已确认列：

- `assignments.submission_requirements_json`
- `submissions.submission_item_key`
- `submissions.submission_item_label`

## 7. M3 样例作业与提交测试数据

目录：

```text
test_cases/grading_m3/
```

用途：提供一组中文合成数据，覆盖多提交项作业、Python Online Judge、Markdown 报告 LLM 辅助批改占位流程和教师最终复核。

### 7.1 初始化班级和学生

方式 A：教师登录并通过审批后，直接创建教学班和名单。

```text
POST /api/admin/classes
```

请求体：

```text
test_cases/grading_m3/setup/class_with_roster.json
```

预期：创建教学班 `OS202603`，名单包含 `OS202603-06` 到 `OS202603-09` 四名合成学生。

方式 B：先创建空教学班 `OS202603`，再按 Excel 导入名单。

```text
POST /api/admin/classes/import-excel
```

Multipart：

```text
class_id = 教学班 ID
file = test_cases/grading_m3/setup/grading_m3_students.xlsx
```

预期：Excel 会被解析出课程名称、课程号、学期和 4 名学生，导入后名单与 `class_with_roster.json` 一致。

随后使用 `test_cases/grading_m3/setup/student_register_payloads.json` 中的每个对象注册学生：

```text
POST /api/auth/register
```

公共测试密码为 `secret123`。

### 7.2 创建两个作业

教师对该教学班分别创建：

- `test_cases/grading_m3/assignments/case_01_one_py_one_md.json`：提交 1 个 `.py` 和 1 个 `.md`。
- `test_cases/grading_m3/assignments/case_02_two_py_one_md.json`：提交 2 个 `.py` 和 1 个 `.md`。

接口：

```text
POST /api/admin/classes/:classId/assignments
```

两个作业的内容要求均独立写在 Markdown 文件中：

- `test_cases/grading_m3/assignment_contents/case_01_one_py_one_md.md`
- `test_cases/grading_m3/assignment_contents/case_02_two_py_one_md.md`

### 7.3 提交与预期结果

学生提交接口：

```text
POST /api/assignments/:assignmentId/submissions
```

Multipart：

```text
item_key = program | report | fcfs | rr
file = 对应提交文件
```

测试用例 1 的提交位于：

```text
test_cases/grading_m3/submissions/case_01/
```

预期：

- `OS202603-06`：程序通过，报告质量高，建议最终分 98。
- `OS202603-07`：程序部分通过，报告较浅，建议最终分 54。

测试用例 2 的提交位于：

```text
test_cases/grading_m3/submissions/case_02/
```

预期：

- `OS202603-08`：两个程序均通过，报告质量高，建议最终分 97。
- `OS202603-09`：FCFS 错误、RR 超时、报告较弱，建议最终分 20。

详细建议分数见：

```text
test_cases/grading_m3/expected_scores.json
```

当前 LLM 外部调用仍未启用；Markdown 报告会记录 `external_call_not_enabled`，最终分数由教师复核或发布。

## 8. M3 UI 与复核验收补充

### 8.1 自动化检查

本轮建议执行：

```bash
python -c "import ast, pathlib; files=[p for p in pathlib.Path('backend/app').rglob('*.py')]+[p for p in pathlib.Path('backend/tests').rglob('*.py')]; [ast.parse(p.read_text(encoding='utf-8'), filename=str(p)) for p in files]; print(f'parsed {len(files)} python files')"
cd frontend
node ./node_modules/vue-tsc/bin/vue-tsc.js --noEmit --incremental false
```

新增后端测试覆盖：

- 学生提交隐藏用例后，学生响应中隐藏输入、期望输出和 diff。
- 教师提交列表中可看到完整隐藏用例报告。
- 教师可通过 `/api/admin/submissions/:submission_id/download` 下载学生提交文件。

### 8.2 手动验收

教师端作业编辑：

- 点击新建或编辑作业，确认进入全屏编辑工作区。
- 作业内容只保留 Markdown 编辑与实时预览，不再显示作业级“评分标准 Markdown”输入。
- 在内容中输入 fenced code block、Markdown 表格和 `` `inline code` ``，确认预览正确渲染。
- 不添加程序评测或 AI 评测时，页面只显示添加按钮，不显示空表格或“0 个模块”。
- 添加程序评测，确认每个模块可以新增多个测试用例，并填写输入、期望输出、分数占比、超时和隐藏用例。
- 添加 AI 评测，确认可以新增多个评分项目，每项包含内容标准和权重。

教师端预览与复核：

- 草稿作业预览页应显示发布按钮，点击后作业状态变为已发布。
- 作业预览在没有程序/AI 评测时不显示空评测区域。
- 提交状态表格的操作列应为紧凑图标按钮，窄屏下不明显遮挡主信息列。
- 打开复核成绩，确认能看到该学生所有最新提交文件，并可以点击下载。
- 对 wrong answer 的程序评测，展开用例详情后应能看到输入、期望输出、学生输出、stderr 和首个差异行。
- 对 AI 评测，确认复核弹窗能展示模块状态、输入文件、分值占比、评分项目和权重。

学生端：

- 作业详情阅读区域应比旧版本更宽，长 Markdown、代码块和表格应在内容区内滚动或换行，不拉坏整体表单。
- 未提交的提交项按钮显示“提交”；已提交过的提交项按钮显示“重新提交”。
- 重新提交后，提交状态仍按该提交项最新文件展示，教师端复核能看到最新提交文件。

## 9. M3 批改状态与反馈发布验收

### 9.1 数据库迁移

本轮新增阅读状态表：

```text
backend/migrations/versions/7c91a2b4e8d0_add_assignment_reads.py
```

正常环境执行：

```bash
cd backend
uv run flask --app app:create_app db upgrade
```

当前本机 `.venv` 损坏时，可用已更新的临时修复脚本补齐本地 SQLite：

```bash
python backend/migrate_sqlite_m3.py
```

预期：

```text
alembic_version = 7c91a2b4e8d0
assignment_reads = id, assignment_id, student_user_id, read_at
```

### 9.2 教师端手动验收

1. 进入教师作业列表，确认列为：作业 / 代码 / 类型 / 截止时间 / 状态 / 操作。
2. 状态标签应显示 `草稿/已发布 n1/N n2/n1`，其中 `n1` 是完成全部必交项的人数，`n2` 是已发布反馈人数。
3. 进入提交详情，确认表格只显示序号、姓名、提交日期、状态。
4. 状态列应同时显示学生端状态和教师端状态。
5. 学生未打开作业前显示“学生端：未阅读”；学生打开详情但未提交时显示“学生端：未提交”；完成必交项后显示“学生端：已提交”。
6. 教师端状态应按流程显示：待批改 / 待复核 / 已复核 / 已反馈。
7. 点击已提交学生行进入批改弹窗。
8. 批改弹窗应按学生上传文件时间顺序列出文件，并提供“在线预览”和“下载文件”。
9. `.md` 在线预览应渲染 Markdown、数学公式、表格和代码块；`.py` 在线预览应显示 Python 语法高亮。
10. 未绑定程序/AI 评测的提交文件应标识为“教师手动批改”，并要求教师输入文件评分和评语。
11. 绑定程序评测的文件应标识为“程序评测后复核”，并能查看用例状态、期望输出、学生输出、stderr 和差异行。
12. 绑定 AI 评测的文件应标识为“AI 建议后复核”，并能查看评分项目和权重。
13. 修改逐文件评分后，总分应自动汇总。
14. 点击“预览反馈”，应生成 Markdown 批改报告。
15. 点击“保存”，教师端状态变为“已复核”，学生端仍不能看到最终反馈。
16. 点击“发布反馈”，教师端状态变为“已反馈”，作业列表 `n2` 计数增加。

### 9.3 学生端手动验收

1. 学生打开已发布作业列表，应看到提交状态和批改状态。
2. 教师未发布反馈时，学生不应看到最终分和反馈报告。
3. 教师发布反馈后，学生作业详情应显示最终分和 Markdown 反馈报告。
4. 反馈发布后，该作业的提交按钮应禁用并显示“已反馈”。
5. 反馈发布后直接调用提交接口，应返回 403，不允许重新提交。

### 1.4 本次 M3 复核记录

2026-08-24 已验证：

- `python -m py_compile backend/app/services/judge.py backend/app/routes/assignments.py backend/app/config.py` 通过。
- `frontend` 下执行 `vue-tsc --noEmit --incremental false` 通过。
- `frontend` 下执行 `vite build` 通过，产物成功写入 `frontend/dist/index.html`。

本地 `uv/pytest` 环境如未安装 `pytest`，先执行 `uv sync` 后再运行 `uv run pytest`。

### 1.5 Docker Python OJ 验收

前置条件：

- Docker Desktop 已启动，命令行执行 `docker info` 成功。
- 首次使用前可以手动执行 `docker pull python:3.11-slim`，也可以让后端首次评测时自动拉取。

建议手动验收：

- 冷启动或镜像不存在时提交一个正确 `.py` 作业；预期镜像准备时间不计入单个测试用例超时，评测记录可能等待镜像拉取完成后才进入用例执行。
- 提交无限循环程序，测试用例超时设置为 1-2 秒；预期用例状态为超时，且用例耗时按容器内 `timeout` 控制。
- 停止 Docker Desktop 后重新评测；预期评测返回运行器错误，不把 Docker 启动失败误判为学生程序超时。

### 1.6 教师复核页验收

进入教师端某次学生提交详情：

- 顶部应固定显示序号、学生姓名、总分和作业状态，滚动文件批改内容时仍保持可见。
- 页面下方按学生提交文件顺序展示，每个文件都有在线预览、下载、评测结果、文件评分和评语。
- 程序评测文件只展示测试用例结果、输出差异和标准输出/错误输出，不再展示额外分析报告。
- AI 或程序评测文件显示“重测”按钮；点击后刷新该学生提交的自动评测结果。
- 文件评分输入旁应显示满分和权重；保存或发布前权重合计必须为 100%。
- 页面底部不再显示旧的自动汇总分、评测状态和修改原因。

### 1.7 Python OJ argv-only 验收

程序测试用例现在只支持命令行参数输入：

- `运行命令参数`：追加到 `python -I source.py` 后，传给学生程序的 `sys.argv[1:]`。
- OJ 不再向程序 stdin 写入内容；学生代码中使用 `input()` 或 `sys.stdin.read()` 会读到空输入或 EOF。

建议验收：

- 学生程序读取 `sys.argv[1:]`，测试用例填写 `运行命令参数 = 1 2`，预期程序收到两个参数并输出正确结果。
- 学生程序读取 `sys.argv[1:]`，测试用例填写 `运行命令参数 = --limit 3 "two words"`，预期程序收到三个参数：`--limit`、`3`、`two words`。
- 隐藏测试用例在学生端不应显示 argv、期望输出和输出差异；教师端复核页应能看到完整信息。

### 1.8 作业删除、退回重交和发布后修改重置验收

2026-08-27 已验证新增业务：

- 教师端作业列表和作业预览均提供删除入口；删除后教师端列表和学生端已发布作业列表都不再显示该作业。
- 教师在学生作业批改弹窗中点击“退回重交”，会清空该学生本作业的提交文件、程序评测、AI 辅助详情和教师批改结果；学生端回到可提交状态。
- 修改已发布作业时，前端必须弹窗提醒：重新发布会清空所有已反馈、已保存和自动批改结果，并重新执行程序/AI评测。教师确认后才提交 `reset_grading=true`。
- 后端若发现已发布作业存在批改/评测记录而请求未带 `reset_grading=true`，返回 409 和 `requires_reset_grading=true`。
- 重置后保留学生已提交文件，清空旧反馈和人工最终分，并按新作业配置重新执行自动评测；学生端不再看到旧成绩或旧反馈。
- 学生端作业详情和提交返回中不暴露 `ai_evaluations`、`llm_score` 和 `llm_details`；教师端仍可查看 AI 评测模块和辅助结果。
- 教师端作业状态显示为三个标签：草稿/已发布、`n1/N`、`n2/n1`。
- 教师端按名单查看作业情况新增“总分”列，未批改时为空。
- 所有通过 `formatDate` 展示的日期统一为 `YYYY-MM-DD`。
### 1.9 教师复核页程序评测结果显示回归

自动化测试：

```shell
cd backend
uv run pytest tests/test_m3_grading.py::test_teacher_submission_overview_returns_program_case_details_for_bound_file
```

验收要点：

- 创建包含 `code` 和 `report` 两个提交项的作业，并把程序评测模块的输入文件设置为 `code`。
- 学生分别提交 `.py` 和 `.md` 文件后，教师端提交详情接口应在 `code` 文件上返回 `latest_judge_run.details.cases`。
- 教师复核弹窗中，`code` 文件应显示“程序评测后复核”、评测模块、运行状态、自动得分和每个用例的运行参数/期望输出/学生输出/错误输出/diff。
- 若 Docker 或测试配置导致暂时没有用例结果，页面仍应显示这是已配置程序评测的文件，并提示重测或检查环境，不应显示“未配置程序或 AI 评测”。
- 未绑定程序/AI 的 `report` 文件仍显示教师手动批改。
### 1.10 分文件批改保存、确认状态和学生反馈入口回归

自动化测试：

```shell
cd backend
uv run pytest tests/test_m3_grading.py::test_student_read_status_and_published_feedback_lock_resubmission
```

验收要点：

- 教师在复核弹窗中修改每个文件的评分和评语，点击“保存”后关闭弹窗，再次打开同一学生作业，应能看到分文件评分、评语和确认状态仍然存在。
- 点击“发布反馈”时也必须保存分文件评分和评语，不能只保存教师总评。
- 程序/AI/手动是评分来源标签，文件级确认状态应单独显示；程序和 AI 文件提供“确认复核”，手动文件提供“确认批改”。
- 教师反馈报告应按文件列表展示，不应再出现 `| 文件 | 类型 | 权重 | 得分 | 评语 |` 这种 Markdown 表格。
- 学生端作业详情页的需提交文件列表只显示提交项、状态和操作；允许类型、大小上限、命名要求在提交弹窗中显示。
- 学生端已反馈作业应通过“查看批改反馈”入口打开独立弹窗，不应把教师反馈紧贴在作业预览内容后面。
### M3 验收：确认提交、队列评测与 AI 评测

自动化验证：

    cd backend
    python -m py_compile app/routes/assignments.py app/services/grading.py app/services/grading_queue.py app/services/llm_grading.py app/models.py app/services/file_validation.py app/__init__.py app/config.py
    uv run pytest tests/test_m3_grading.py tests/test_assignments.py

    cd ../frontend
    npm run build

本次已验证结果：

- Python 语法检查通过。
- uv run pytest tests/test_m3_grading.py tests/test_assignments.py：17 passed。
- uv run pytest：41 passed。
- npm run build：通过，Vite 成功写入 frontend/dist/index.html。

手动验收步骤：

1. 学生打开一个已发布作业，逐个提交项上传文件；上传阶段只校验文件名模板。上传成功后提交项状态应显示为已上传或待确认，但教师端已提交人数不应增加，且不应出现程序评测结果。
2. 必交文件都上传后，点击确认提交作业；确认阶段会校验扩展名、大小和内容基本规则。按钮成功后提示自动评测已加入队列，学生端状态变为已提交或已迟交。
3. 教师端进入提交详情，确认该学生状态进入待批改或待复核，程序评测结果随后出现；测试环境中会立即出现，因为 GRADING_QUEUE_INLINE=True。
4. 教师复核某个程序评测文件，点击确认复核并保存；再次打开时，该文件标签应显示已复核，分文件评分和评语仍然存在。
5. 教师 xsun 确认 LLM 配置启用后，创建包含 .md 提交项和 AI 评测模块的作业，评分项目至少填写一项 content/weight；学生确认提交后，教师端应看到 AI 模块的 completed 或 error 状态、建议分、评分项目结果和原始辅助信息。
6. 学生端在教师发布反馈前不能看到 AI 评分、AI 细节或最终反馈；教师发布反馈后只能通过查看批改反馈入口查看最终分和 Markdown 反馈报告。

注意：当前生产和开发环境的评测队列是进程内后台线程。若使用多进程 Gunicorn，高峰期建议先配置单独评测进程或尽快切换 Redis + RQ/Celery，避免任务分散在多个 Web worker 内存队列中。

### M4 验收：成绩导出、班级分析与学生总览

自动化验证：

```shell
cd backend
python -m py_compile app/routes/assignments.py app/routes/classes.py app/services/score_export.py tests/test_m4_exports.py
uv run pytest tests/test_m4_exports.py

cd ../frontend
npm run build
```

本次已验证结果：

- Python 语法检查通过。
- uv run pytest tests/test_m4_exports.py：2 passed。
- npm run build：通过，Vite 成功写入 frontend/dist/index.html；仅有现有依赖注释和 chunk size 提示。

手动验收步骤：

1. 教师进入某个已发布作业的提交状态抽屉，应能看到完成情况、平均分、发布后提交、截止前提交、已反馈等统计卡。
2. 点击 CSV，应下载包含 No.、姓名、学号、学生编号、提交状态、提交时间、最终分、自动分、AI 建议分和教师评语的单作业成绩表。
3. 点击 ScoreManagerCLI，默认普通作业字段为 homework、实验报告字段为作业 code；已复核或已发布且有最终分的学生应生成 rd/brd 或 lab rd 命令。
4. 如果名单中的 student_id 不符合 教学班别名-两位No. 格式，ScoreManagerCLI 导出应返回错误，不得跳过校验直接截取短编号。
5. 学生进入“我的班级”，每个班级行应显示已发布、已完成、已反馈、平均分和待提交数量；切换班级后，详情表中成绩列只在教师发布反馈后显示。