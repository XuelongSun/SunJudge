# SunJudge Tutorial

> 本文件记录技术实现细节、代码逻辑和里程碑设计。测试步骤、Bruno 接口测试和浏览器手测见 `test.md`。

## 0. 环境搭建

SunJudge 当前由两个本地开发服务组成：

- 后端：Flask + SQLAlchemy + Alembic/Flask-Migrate + Flask-Login，使用 `uv` 管理依赖。
- 前端：Vue 3 + Vite + TypeScript + Element Plus，使用 `npm` 管理依赖。

推荐基础环境：

- Python 3.11+。
- Node.js 20+。
- uv、npm、git。
- 本地可用 Windows、macOS 或 Linux；云端部署目标优先 Ubuntu。

后端依赖与数据库初始化：

```bash
cd backend
uv sync
uv run flask --app app:create_app db upgrade
uv run flask --app app:create_app create-admin admin admin123
```

前端依赖：

```bash
cd frontend
npm install
```

开发服务：

```bash
cd backend
uv run flask --app app:create_app run --host 127.0.0.1 --port 5000 --debug
```

```bash
cd frontend
npm run dev
```

`frontend/package.json` 已将 Vite 固定在 `127.0.0.1:5173`，并使用 `--strictPort`。如果 5173 被占用，Vite 会直接报错。

## 1. M1：账号权限与名单注册（已完成）

### 1.1 后端入口

`backend/app/__init__.py` 是 Flask app factory：

```text
flask CLI
  -> import app:create_app
  -> create_app()
  -> load Config
  -> init db / migrate / login_manager / CORS
  -> register auth_bp / admin_bp / classes_bp
  -> wait for HTTP requests
```

关键对象：

- `db`：SQLAlchemy ORM 入口。
- `migrate`：Alembic 迁移入口。
- `login_manager`：Flask-Login Session 管理入口。
- `auth_bp`：认证蓝图，挂载 `/api/auth`。
- `admin_bp`：教师名单管理和管理员教师审批入口，挂载 `/api/admin`。
- `classes_bp`：公开班级蓝图，挂载 `/api/classes`。

### 1.2 数据模型

核心模型在 `backend/app/models.py`。

`User`

- 保存账号、密码哈希、角色、学生真实姓名、系统学生编号、短序号 No.、长学号和教师审批状态。
- `username` 是数据库中的唯一账号字段；教师和管理员使用昵称，学生账号由首次注册的邀请码自动生成内部值，但学生界面不展示该字段，登录也不使用昵称。旧测试数据里的学生昵称需要清理或忽略，避免再次开放学生昵称登录。
- `student_id` 是系统注册编号，格式为 `教学班别名-两位No.`，例如 `OS202601-06`。
- `student_no` 是短序号，和线下 ScoreManagerCLI 的短编号一致。
- `student_number` 是 Excel 中的长学号，仅作为学生信息字段。

`Course`

- 保存课程内部识别字段。
- 教师创建教学班时先生成占位课程。
- 导入 Excel 后，课程名称、课程号、学期从 Excel 上方课程信息写入 `name/code/semester`。

`CourseClass`

- 表示教学班，不等同于 Excel 中的自然班级。
- 教师创建时只填写 `alias`，例如 `OS202601`。
- `invite_code` 与 `alias` 相同。
- 学生最终使用 `alias-No.` 注册，例如 `OS202601-06`。

`ClassRoster`

- 表示教师导入或在线维护的学生名单。
- `student_no`：短序号 No.，来自 Excel 的 `序号` 列，内部统一补齐为两位。
- `student_number`：长学号，来自 Excel 的 `学号` 列。
- `student_name`：真实姓名。
- `source_class`：Excel 中的自然班级，只作为学生信息字段。
- `student_id`：系统生成的注册编号，格式为 `教学班别名-两位No.`。

`CourseMember`

- 学生注册成功后写入，表示用户属于某课程和教学班。

### 1.3 Excel 名单解析

解析逻辑在 `backend/app/services/roster_import.py`。

当前依据根目录 `students.xlsx` 的格式：

- 文件前几行是课程信息，不是学生信息。
- 解析器会先扫描真正包含 `序号 / 学号 / 姓名 / 班级` 的表头行。
- 只有表头之后、且 `序号` 是数字的行会被当作学生行。
- 非学生说明行、空行和非数字序号行会跳过。
- 数字序号会统一补齐为两位，例如 `6 -> 06`。
- 课程名称、课程号、学期从表头上方文本提取。

导入时不按 Excel 的 `班级` 创建教学班。教师必须先创建教学班并指定别名，然后把 Excel 导入到该教学班。

### 1.4 学生注册逻辑

注册接口在 `backend/app/routes/auth.py`：

```text
POST /api/auth/register
  -> 校验 username/password/role
  -> 学生只提交真实姓名、邀请码和密码
  -> 邀请码必须是 教学班别名-两位No.，例如 OS202601-06
  -> 按教学班别名查 CourseClass
  -> 按 class_id + student_no 查 ClassRoster
  -> 校验真实姓名与名单记录一致
  -> 名单匹配才创建 User
  -> 使用真实姓名 + 学号查找其他班级名单
  -> 复制 roster 的 student_no/student_number 到 User
  -> 标记相关 roster 为 registered
  -> 为每个匹配班级写入 CourseMember
```

学生不需要教师审批，但必须在教师导入的名单中。失败时服务端会区分提示：邀请码格式错误、教学班别名不存在、名单中不存在该 No.、真实姓名不一致、该学生已绑定账号。

示例：

- 教学班别名：`OS202601`
- Excel 序号：`6`
- Excel 长学号：`32319500084`
- 学生邀请码：`OS202601-06`

### 1.5 教师审批逻辑

教师注册不会立即可登录：

```text
teacher register
  -> role = teacher
  -> teacher_status = pending
```

管理员只负责教师审批：

```text
PATCH /api/admin/teachers/<id>/status
  -> roles_required(admin)
  -> status = approved/rejected
  -> write AuditLog
```

管理员不创建教学班。教师登录时，如果 `teacher_status != approved`，后端返回 403。

管理员可读接口：

- `GET /api/admin/teachers?status=all`：查看全部教师。
- `GET /api/admin/classes`：查看全部教学班。

这些接口只用于概览和审批辅助；创建教学班、导入名单、名单增删改仍只允许已审批教师执行。

学生可读接口：

- `GET /api/classes/my`：查看当前学生已绑定的班级列表。

### 1.6 登录逻辑

登录接口在 `backend/app/routes/auth.py`：

```text
POST /api/auth/login
  -> 读取登录名和密码
  -> 教师或管理员登录名匹配 User.username
  -> 学生不会按 User.username 登录
  -> 或匹配学生 User.student_id
  -> 或匹配已绑定 ClassRoster.student_id
  -> 或匹配学生 User.student_name
  -> 在候选用户中校验密码
  -> 如果多个候选账号密码都匹配，返回冲突，要求改用学生编号
  -> 教师额外校验 teacher_status == approved
  -> 写入 Flask-Login Session
```

因此登录页不需要选择角色。教师和管理员昵称全局唯一，优先按昵称匹配；学生真实姓名可能重名，后端只在唯一候选匹配时放行，否则要求改用学生编号。管理员和教师仍主要使用昵称登录。

## 2. M1/M2 过渡：教学班和名单管理

### 2.1 创建教学班

接口在 `backend/app/routes/admin.py`：

```text
POST /api/admin/classes
```

当前只允许已审批教师调用。请求体只需要教学班别名：

```json
{
  "class": {
    "alias": "OS202601"
  },
  "roster": []
}
```

后端会创建：

- 占位 `Course`：`name/code/semester` 暂为待导入。
- `CourseClass.alias = OS202601`。
- `CourseClass.invite_code = OS202601`。

### 2.2 导入 Excel 名单

接口：

```text
POST /api/admin/classes/import-excel
```

请求体是 multipart：

- `class_id`：目标教学班 ID。
- `file`：Excel 文件。

导入流程：

```text
校验文件
  -> 定位真实表头行
  -> 解析 Excel 元数据和学生行
  -> 用 Excel 课程名称/课程号/学期更新 Course
  -> 对每个学生生成 student_id = CourseClass.alias + "-" + student_no
  -> 已存在则更新姓名、No.、学号、source_class
  -> 不存在则新增 ClassRoster
```

### 2.3 在线增删改查

接口：

- `GET /api/admin/classes`：教师自己的教学班列表。
- `GET /api/admin/classes/<class_id>/roster`：名单列表。
- `POST /api/admin/classes/<class_id>/roster`：新增名单项。
- `PATCH /api/admin/roster/<entry_id>`：修改名单项。
- `DELETE /api/admin/roster/<entry_id>`：删除名单项。

在线维护名单时可以输入 `student_no=6`，后端会保存为 `06`。已注册绑定账号的名单项暂不允许修改或删除。

## 3. 前端执行逻辑

前端入口：

```text
frontend/index.html
  -> frontend/src/main.ts
  -> frontend/src/App.vue
```

`frontend/src/api.ts`

- 统一封装 `fetch`。
- `credentials: 'include'` 用于携带 Flask-Login Session Cookie。
- JSON 请求自动设置 `Content-Type: application/json`。
- Excel 上传使用 `FormData`，不手动设置 Content-Type，让浏览器生成 multipart boundary。

`frontend/src/App.vue`

- 未登录：显示登录、学生注册、教师申请。
- 学生注册：填写真实姓名、密码、邀请码。
- 右上角账号信息：只显示角色文字和用户名；管理员为橙色、教师为蓝色、学生为绿色，学生用户名显示真实姓名。
- 管理员：显示全部教师；每个教师行可展开查看其教学班。
- 已审批教师：主界面只显示教学班列表、添加班级、班级总数和刷新按钮。
- 教师点击“添加班级”打开新建班级弹窗。
- 教师点击“学生列表”打开名单抽屉，在抽屉中导入名单、新增学生或编辑学生。
- 学生：登录后先只显示已绑定班级列表；点击进入某个班级后，主界面再显示该班级内学生身份和作业列表占位。班级身份来自 `/api/classes/my` 返回的每个教学班 roster 信息，不能复用 `currentUser.student_id` 作为所有班级的编号。
- 主题：`theme` 保存 `light/dark`，写入 `document.documentElement.dataset.theme` 和 `localStorage`。

关键状态：

- `currentUser`：当前登录用户。
- `teachers`：管理员可查看的教师列表。
- `pendingTeachers`：由 `teachers` 计算得到的待审批教师。
- `adminClasses`：管理员可查看或教师可管理的教学班。
- `studentClasses`：当前学生已绑定的班级列表。
- `roster`：当前教学班名单。
- `selectedStudentClassId/currentStudentClass`：学生点击进入后才设置的当前班级；未选择时页面只显示班级列表。
- `classDialogVisible/importDialogVisible/rosterDrawerVisible/studentDialogVisible`：教师界面按需弹出的操作面板。
- `classForm.class_alias`：新建教学班别名。
- `importForm.class_id`：Excel 导入目标教学班。
- `rosterForm.student_no`：名单短序号 No.
- `rosterForm.student_number`：长学号。

## 4. 后续里程碑组织

### M2：课程、班级和作业提交

目标：

- 正式课程管理页面。
- 正式教学班管理页面。
- 作业发布。
- `.py` / `.md` 文件提交。
- 文件格式、大小、命名模板和成员关系校验。

### M3：自动批改

目标：

- Python 评测 MVP。
- DeepSeek LLM 辅助批改 MVP。
- 教师复核分数和评语。

### M4：成绩与导出

目标：

- 学生查看已发布成绩。
- 教师查看全班成绩。
- CSV 导出。
- ScoreManagerCLI 命令导出。

导出时从 `student_id` 提取 `-` 后的 No.，例如：

```text
OS202601-06 -> 06
```

这与线下 ScoreManagerCLI 使用短序号记录成绩的习惯保持一致。

## 5. M2：作业管理与提交闭环（已完成）

M2 在 M1 的课程、教学班、名单和成员关系上继续向前推进，完成“教师发布作业 -> 学生提交文件 -> 系统同步校验 -> 教师查看提交状态”的最小闭环。自动评测、LLM 批改、教师复核评分仍留到 M3。

### 5.1 数据模型

新增模型位于 `backend/app/models.py`：

- `Assignment`
  - 归属 `course_id` 和 `class_id`。
  - 使用 `title/code/type/description/deadline/max_score` 描述作业。
  - `type` 支持 `programming/report/mixed`。
  - `status` 支持 `draft/published`，草稿不对学生可见。
  - `file_rules_json` 保存允许扩展名、大小上限和命名模板。
  - `rubric_json` 保存教师输入的评分说明。
  - 同一教学班内 `code` 唯一。
- `Submission`
  - 归属 `assignment_id` 和 `student_user_id`。
  - 保存原始文件名、服务端存储路径、文件大小、提交状态和校验结果。
  - 允许同一学生多次提交；列表展示时按最新提交显示。

对应迁移文件：

```text
backend/migrations/versions/a3c9d2f6e7b1_add_m2_assignments_submissions.py
```

### 5.2 文件规则校验

文件校验集中在 `backend/app/services/file_validation.py`，路由只负责鉴权、取参数和保存结果。

默认规则：

```json
{
  "allowed_extensions": [".md"],
  "max_size_mb": 5,
  "filename_template": "{student_id}_{assignment_code}{extension}"
}
```

不同作业类型的默认扩展名：

- `programming`: `.py`
- `report`: `.md`
- `mixed`: `.py` 和 `.md`

当前同步校验内容：

- 扩展名必须是 `.py` 或 `.md`，且在作业白名单中。
- 文件不能为空，不能超过作业配置的大小上限。
- 文件名必须等于命名模板渲染结果。
- 命名模板支持 `{student_id}`、`{student_no}`、`{assignment_code}`、`{name}`、`{extension}`。
- 文件内容不能包含空字节，并且 `.py/.md` 必须是 UTF-8 文本。
- 提交前先确认学生是该教学班成员，并用该班级 roster 中的 `student_id/student_no/student_name` 渲染命名模板。

这样可以避免学生在多班级场景下误用 `currentUser.student_id`，必须使用当前教学班 roster 里的编号。

### 5.3 后端路由

新增蓝图：

```text
backend/app/routes/assignments.py
```

已挂载到 `/api`。

教师接口：

- `GET /api/admin/classes/<class_id>/assignments`
  - 查看某教学班全部作业，包括草稿和已发布。
- `POST /api/admin/classes/<class_id>/assignments`
  - 创建作业，可保存草稿或直接发布。
- `PATCH /api/admin/assignments/<assignment_id>`
  - 更新作业。
- `POST /api/admin/assignments/<assignment_id>/publish`
  - 发布草稿。
- `GET /api/admin/assignments/<assignment_id>/submissions`
  - 按 roster 名单查看每名学生的最新提交状态。

学生接口：

- `GET /api/classes/<class_id>/assignments`
  - 只返回当前学生所属教学班内已发布作业。
- `POST /api/assignments/<assignment_id>/submissions`
  - 上传 `.py` 或 `.md` 文件，后端保存前执行成员、时间、扩展名、大小、命名和内容基础校验。

权限原则：

- 教师只能管理自己创建的课程和教学班。
- 学生只能查看和提交自己已加入教学班的已发布作业。
- 草稿作业不会出现在学生接口中。
- 非成员直接访问提交接口不会泄露作业详情。

### 5.4 前端交互

前端主要改动在 `frontend/src/App.vue` 和 `frontend/src/api.ts`。

教师端：

- 教学班列表的“作业”列显示真实 `assignment_count`。
- “发布作业”打开作业表单，可配置标题、代码、类型、截止时间、扩展名、大小、命名模板和 rubric。
- “保存草稿”只保存，不对学生展示。
- “保存并发布”会立即对学生可见。
- “作业列表”抽屉展示作业状态、提交人数、文件规则和操作入口。
- “提交状态”抽屉按名单显示每个 roster 学生是否提交。

学生端：

- 点击班级后加载该班级已发布作业。
- 作业表格展示代码、类型、截止时间和提交状态。
- 点击“提交”时展示允许类型、大小上限和按当前班级 roster 渲染出的命名要求。
- 提交成功后刷新该班级作业列表，状态变为“已提交”或“已迟交”。

### 5.5 当前限制

- M2 只保存提交文件和校验结果，不执行 Python 自动评测。
- M2 不调用 DeepSeek，也不生成 LLM 批改建议。
- M2 不提供教师评分复核和成绩发布。
- 当前文件基础检查只验证 UTF-8 文本和空字节，不做更复杂的 MIME 或恶意代码检测。
- 上传文件保存在本地 `backend/instance/uploads`，生产部署前仍需补充备份与存储策略。

## 6. M2 细化：作业类型与评测模块解耦

本轮细化把“作业是什么”和“如何批改”拆开：

- 作业类型只表达教学材料类别：`homework`（作业）和 `lab_report`（实验报告）。
- 程序评测、AI 评测都是可选模块，由教师在作业表单中按需添加。
- 如果教师不添加程序评测和 AI 评测，该作业就是手动批改作业。

这样避免把每次作业预先固定成“编程 / 文档 / 混合”三种拼法。教师可以给同一个作业添加多个程序评测、多个 AI 评测，也可以完全不添加自动评测。

### 6.1 后端数据结构

`Assignment` 新增字段：

- `description_format`：`text` 或 `markdown`。
- `rubric_format`：`text` 或 `markdown`。
- `program_evaluations_json`：程序评测模块数组。
- `ai_evaluations_json`：AI 评测模块数组。

程序评测模块结构：

```json
{
  "name": "case 1",
  "input": "1 2",
  "expected_output": "3",
  "score_percent": 30,
  "timeout_seconds": 2,
  "is_hidden": false
}
```

AI 评测模块结构：

```json
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
```

后端保存时会校验：

- 作业类型必须是 `homework` 或 `lab_report`。
- 文本格式必须是 `text` 或 `markdown`。
- 每个评测模块必须是对象。
- 每个评测模块的 `score_percent` 必须大于 0。
- 程序评测和 AI 评测的总占比不能超过 100。

为避免旧开发进程或旧代码路径引用 `TYPE_PROGRAMMING/TYPE_REPORT/TYPE_MIXED` 时直接崩溃，`Assignment` 模型保留了这些旧常量作为兼容别名；但新接口校验仍只允许 `homework` 和 `lab_report`，旧三类不会作为新的业务类型开放。

当前 M2 只保存这些配置，不执行评测。M3 实现 Python 评测和 DeepSeek 调用时，会读取这些模块配置生成评测任务。

### 6.2 文件提交类型

提交文件类型扩展为：

- `.py`
- `.md`
- `.zip`
- `.jpg`
- `.png`

`services/file_validation.py` 的策略：

- `.py/.md` 必须是 UTF-8 文本，且不能包含空字节。
- `.zip/.jpg/.png` 允许二进制内容，但会检查基础文件头。
- 文件名仍然按模板渲染，例如 `{student_id}_{assignment_code}{extension}`。
- 默认 Flask 上传体积上限调整为 64 MB；单个作业仍可通过 `max_size_mb` 设置更小限制。

### 6.3 Markdown 渲染

教师端作业内容统一使用 Markdown，不再提供 TXT 模式，也不再提供独立的作业级评分标准输入框。需要给学生看的评分说明应直接写在作业内容中；AI 评分项目在 AI 评测模块中结构化维护。

前端当前使用轻量本地渲染函数，并先转义 HTML，再处理标题、列表、加粗、行内代码、fenced code block、基础表格和段落，避免直接渲染未转义 HTML。后续如需要完整 Markdown，可引入成熟 Markdown 渲染库并配合 sanitizer。

### 6.4 学生端交互调整

学生端从“按钮进入”改为“整行点击”：

- 班级列表显示 `pending_assignment_count`，即已发布但当前学生还没有提交的作业数量。
- 班级列表不再显示操作列；点击整行后高亮当前班级并显示详情。
- 作业列表不显示作业代码、作业类型和操作列；点击整行后高亮当前作业。
- 作业详情页显示作业内容、需提交文件规则和提交按钮。

`/api/classes/my` 现在返回：

```json
{
  "pending_assignment_count": 2,
  "published_assignment_count": 5
}
```

这使前端班级列表可以直接显示待提交数量，不需要为每个班级单独请求作业列表。

### 6.5 教师作业预览

教师端提供两种预览入口：

- 作业列表中的“预览”：预览已保存的作业。
- 新建/编辑作业全屏工作区底部的“预览”：按当前表单内容即时生成预览，即使尚未保存也可以检查展示效果。

预览复用学生详情页的核心渲染逻辑：

- 作业内容按 Markdown 渲染。
- 文件规则显示允许扩展名、大小上限和命名模板。
- 教师额外看到程序评测和 AI 评测模块摘要，包括名称、成绩占比、输入、期望输出、超时、隐藏用例和 AI 评分标准。

这样教师在发布前可以确认学生视角的作业内容是否清晰，同时检查自动评测模块配置是否完整。

### 6.6 班级列表的兼容性统计

班级列表接口需要显示作业数量和待提交数量，但不能为了统计而懒加载完整 `Assignment` 对象。原因是开发过程中本地 SQLite 可能已经有第一版 `assignments` 表，但还没有执行后续细化迁移；如果此时 ORM 加载完整作业行，就会查询 `description_format` 等新列并触发缺列错误。

因此班级信息使用轻量统计函数：

- `assignment_count_for_class(class_id)`：只查询 `assignments.id/class_id/status`。
- `published_assignment_ids_for_class(class_id)`：只取已发布作业 ID。
- `table_has_columns(table_name, columns)`：在表或关键列不存在时返回空统计，而不是让班级接口 500。

完整作业详情仍由作业接口负责返回；班级接口只负责班级信息和计数摘要。

### 6.7 Model 变更后的 SQLite 更新

只修改 `models.py` 不会自动改变本地 SQLite 表结构。凡是新增、删除或修改 SQLAlchemy 字段，都必须同步处理三件事：

1. 新增或更新 Alembic migration。
2. 对本地 SQLite 执行：

```bash
cd backend
uv run flask --app app:create_app db upgrade
```

3. 检查迁移版本或关键表结构，例如：

```bash
cd backend
uv run python -c "from app import create_app; from app.extensions import db; app=create_app(); app.app_context().push(); print(db.session.execute(db.text('SELECT version_num FROM alembic_version')).fetchall())"
```

```bash
cd backend
uv run python -c "from app import create_app; from app.extensions import db; app=create_app(); app.app_context().push(); print([row[1] for row in db.session.execute(db.text('PRAGMA table_info(assignments)')).fetchall()])"
```

这次 `Assignment` 新增 `description_format/rubric_format/program_evaluations_json/ai_evaluations_json` 后，如果不执行 `db upgrade`，访问作业详情或触发完整 `Assignment` 查询时就会出现 `sqlite3.OperationalError: no such column: assignments.description_format`。

## 7. M3：自动批改与教师复核（进行中）

M3 在 M2 的提交记录上增加三类能力，并把作业从“单文件提交”调整为“多提交项提交”：

- Python Online Judge：程序评测模块通过 `input_file_key` 指向某个提交项，对该提交项的最新 `.py` 文件生成 `judge_runs`。
- LLM 辅助批改结构：保存教师 OpenAI 兼容接口配置，并为 `.md` 提交预留 `llm_details_json` 记录。
- 教师复核：教师可以覆盖该学生本次作业的最终分、反馈和评语，修改记录写入 `audit_logs`。

### 7.1 数据模型

新增迁移：

```text
backend/migrations/versions/f2a7c9e5d4b3_add_m3_grading_tables.py
```

新增表：

- `teacher_llm_configs`
  - 每个教师一条配置，保存 provider、base URL、model、API Key 占位字段和启用状态。
  - API Key 不通过接口回显，只返回 `has_api_key`。
- `judge_runs`
  - 每次程序评测保存状态、分数和用例详情。
  - 状态包括 `accepted/wrong_answer/runtime_error/time_limit_exceeded/skipped/error`。
- `grading_results`
  - 每次提交最多一条成绩结果。
  - 保存 `auto_score/llm_score/final_score/feedback/teacher_comment/reviewed_by/status/llm_details_json`。
  - 状态包括 `pending/auto_graded/reviewed/published`。
- `assignment_grades`
  - 每个 `assignment_id + student_user_id` 一条聚合成绩。
  - 用于真实业务里的“一次作业多文件提交、多模块评测、最终一个总分”。
  - 教师复核写这个表，`grading_results` 保留为单文件兼容层。

`Submission.to_dict()` 现在会带上：

- `grading_result`：当前提交的成绩结果。
- `latest_judge_run`：最近一次程序评测结果。
- `submission_item_key/submission_item_label`：当前文件属于哪个提交项。

`Assignment.to_dict()` 现在会带上：

- `submission_requirements`：教师要求学生提交的文件列表。
- `submissions`：学生视角下每个提交项的最新提交文件。
- `assignment_grade`：学生本次作业的聚合成绩。

### 7.1.1 提交项列表

`Assignment.submission_requirements_json` 保存提交项数组：

```json
[
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
]
```

学生提交文件时必须传 `item_key`。后端按该提交项的规则校验扩展名、大小和命名模板，并把 `submission_item_key/submission_item_label` 写入 `submissions`。

### 7.2 Python Judge

程序评测入口在：

```text
backend/app/services/judge.py
```

提交任意文件后，`services/grading.py` 会重算该学生本次作业的聚合自动批改：

```text
提交文件
  -> 保存 Submission
  -> 读取 Assignment.program_evaluations_json
  -> 按 input_file_key 找到对应提交项的最新文件
  -> 对匹配到的 .py 文件执行 Docker 沙箱
  -> 对比 stdout 和 expected_output
  -> 按 score_percent 折算到 assignment.max_score
  -> 写入 JudgeRun 和 AssignmentGrade.auto_score
```

程序评测模块结构现在包含：

```json
{
  "name": "sample",
  "input_file_key": "code",
  "score_percent": 60,
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
```

`score_percent` 由后端按 `cases` 内所有测试用例的分值占比求和得到。程序测试用例使用 `args` 表示命令行参数，不再支持通过 stdin 提供输入。旧版单用例字段 `expected_output/score_percent/timeout_seconds/is_hidden` 仍会被归一化为一个 `cases` 项。

安全取舍：

- 不再使用宿主机 Python 直接运行学生代码。
- 当前实现通过 Docker CLI 启动 `python:3.11-slim`，并设置 `--network none`、`--read-only`、`--memory 128m`、`--pids-limit 64`、`--cap-drop ALL` 和 `no-new-privileges`。
- 本机没有 Docker 或镜像不可用时，评测结果保存为 `error`，不回退到宿主机裸跑。
- 这仍只是教学 MVP 沙箱；云端部署前应继续评估专用 runner、镜像预拉取、CPU 限额、临时目录隔离和日志脱敏。

### 7.3 LLM 辅助批改

教师端新增：

- `GET /api/admin/llm-config`
- `PUT /api/admin/llm-config`

当前已完成配置保存、API Key 不回显、AI 评测结果字段和前端配置入口。AI 模块也通过 `input_file_key` 指向一个提交项：

```json
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
```

实际向教师配置的 OpenAI 兼容地址发送学生 Markdown、作业说明和 rubric，涉及外部数据发送，需要明确部署授权后再接入网络调用；在此之前，自动批改会把对应 AI 评测记录为 `external_call_not_enabled`，并提示教师人工复核。

后续启用外部调用时，应保持以下原则：

- 只在教师显式配置并启用后调用。
- 请求目标只使用教师保存的 base URL。
- 保存模型名、prompt 版本、状态和原始响应摘要。
- JSON 解析失败时保留摘要并标记需要教师人工处理。

### 7.4 教师复核

新增接口：

- `POST /api/admin/submissions/<submission_id>/rerun-grading`
  - 教师以该提交所属的学生和作业为范围，重跑整次作业的自动批改。
- `PATCH /api/admin/submissions/<submission_id>/grade`
  - 教师保存该学生本次作业的最终分、反馈、教师评语和状态。

复核时服务端校验：

- 当前教师必须拥有该提交所属课程。
- `final_score` 必须在 `0..assignment.max_score` 内。
- 状态只能是 `reviewed` 或 `published`。
- 每次复核都写入 `audit_logs`，payload 包含修改前和修改后，目标类型为 `assignment_grade`。

### 7.5 前端交互

教师端新增：

- 顶部“LLM 配置”按钮。
- 作业编辑全屏工作区中，作业内容固定使用 Markdown，右侧提供实时渲染预览，不再提供 TXT 模式和独立评分标准输入。
- “需提交文件”区域改为摘要表格；新增或编辑提交项时打开弹窗，可配置 key、名称、类型、大小、命名模板和是否必交。
- “程序评测”区域改为摘要表格；新增或编辑模块时打开弹窗，选择输入文件，并在模块内继续增加多个测试用例，每个用例有输入、输出、分值占比、超时和隐藏设置。
- “AI 评测”区域改为摘要表格；新增或编辑模块时打开弹窗，选择输入文件、填写指定输入，并维护多个包含内容标准和权重的评分项目。
- 提交状态抽屉展示每个学生的全部提交项文件、评测状态、自动分、最终分、批改状态和反馈。
- 每条已提交记录可“重跑”自动批改或打开“复核”弹窗。

复核弹窗支持：

- 查看自动分和当前批改状态。
- 修改最终分。
- 修改反馈和教师评语。
- 标记为“已复核”或“发布”。

### 7.6 当前限制

- 未被任何程序或 AI 评测模块引用的提交项默认为教师手动评阅。
- LLM 外部调用尚未启用，需要明确授权学生提交内容可发送到教师配置的 OpenAI 兼容接口。
- Docker CLI、镜像和容器运行环境需要由部署机器提供；没有 Docker 时不会执行程序评测。
- M4 仍需补充学生端正式成绩查询、班级成绩统计、CSV 和 ScoreManagerCLI 导出。

### 7.7 本地 SQLite 迁移修复

本轮确认本地 SQLite 仍停在 `d4f0a9b8c2e1`，因此教师点击“LLM 配置”时会因为缺少 `teacher_llm_configs` 表而请求失败。已新增并执行本地修复脚本：

```bash
cd backend
python migrate_sqlite_m3.py
```

执行后本地 `backend/instance/sunjudge.sqlite` 的 `alembic_version` 已更新为：

```text
0b7d4c2a9e11
```

关键表已包含：

- `teacher_llm_configs`
- `judge_runs`
- `grading_results`
- `assignment_grades`

关键列已包含：

- `assignments.submission_requirements_json`
- `submissions.submission_item_key`
- `submissions.submission_item_label`

正常环境仍应优先使用 Alembic：

```bash
cd backend
uv run flask --app app:create_app db upgrade
```

## 8. M3 样例作业与提交数据

目录：

```text
test_cases/grading_m3/
```

该目录不参与应用运行，只作为 Bruno、浏览器手测和后续自动化测试的样例数据源。当前版本已把样例改成中文，并围绕多提交项作业设计。

### 8.1 数据组织

- `setup/class_with_roster.json`：创建教学班 `OS202603`，并一次性写入四名合成学生名单。
- `setup/grading_m3_students.xlsx`：按根目录 `students.xlsx` 的格式生成的名单 Excel，可用于 `import-excel` 接口。
- `setup/student_register_payloads.json`：四名学生注册请求体，全部符合 `教学班别名-两位No.` 规则。
- `setup/llm_config.example.json`：DeepSeek/OpenAI 兼容配置示例，只放占位 API Key。
- `assignment_contents/*.md`：两个作业的中文 Markdown 内容要求。
- `assignments/*.json`：两个可提交到作业创建接口的元数据请求体。
- `submissions/case_01`：测试用例 1 的 1 个 `.py` + 1 个 `.md` 提交样例。
- `submissions/case_02`：测试用例 2 的 2 个 `.py` + 1 个 `.md` 提交样例。
- `expected_scores.json`：人工可读的预期 OJ 状态、建议报告分和建议最终分。

### 8.2 作业元数据设计

两个 JSON 都只使用 Markdown 文本格式：

```json
{
  "description_format": "markdown",
  "rubric_format": "markdown"
}
```

多文件要求通过 `submission_requirements` 表达。每个提交项包含：

- `key`：学生提交时传入的 `item_key`。
- `label`：教师和学生界面展示名称。
- `allowed_extensions`：该提交项允许的扩展名。
- `max_size_mb`：该提交项的大小限制。
- `filename_template`：该提交项的命名模板。
- `required`：是否必交。

程序评测和 AI 评测通过 `input_file_key` 绑定提交项：

- 测试用例 1：`program` 绑定 OJ，`report` 绑定 AI 评测。
- 测试用例 2：`fcfs` 和 `rr` 分别绑定 OJ，`report` 绑定 AI 评测。

AI 评测不再把 `grading_criteria` 写成长字符串，而是使用结构化评分项目：

- `criteria_items`：评分项目数组。
- 每个评分项目包含 `content` 和 `weight` 两个核心字段。
- 后续发给 LLM 时可以直接转为 JSON rubric，提高评分稳定性。

### 8.3 覆盖的批改路径

测试用例 1 `case-01`：

- 要求提交 `OS202603-xx_case-01.py` 和 `OS202603-xx_case-01.md`。
- 张明的程序可通过全部测试点，报告完整，建议最终分 98。
- 李华的程序只处理单行小写输入，报告较浅，建议最终分 54。

测试用例 2 `case-02`：

- 要求提交 `OS202603-xx_case-02_fcfs.py`、`OS202603-xx_case-02_rr.py` 和 `OS202603-xx_case-02.md`。
- 王芳的两个程序均符合样例输出，报告能解释调度差异，建议最终分 97。
- 赵强的 FCFS 输出逻辑错误、RR 死循环、报告缺少指标分析，建议最终分 20。

### 8.4 当前限制

- 样例数据不会自动导入数据库，需通过现有 API 或前端页面逐步创建和提交。
- OJ 的 `accepted/wrong_answer/runtime_error/time_limit_exceeded` 结果依赖 Docker 可用；没有 Docker 时会得到 `error`，这是当前安全策略的预期行为。
- LLM 外部调用尚未启用，Markdown 报告只会记录 `external_call_not_enabled` 并等待教师复核。

## 9. M3 UI 与复核体验补强

本轮把作业编辑从窄弹窗改为全屏编辑工作区：教师只维护作业内容 Markdown，右侧实时预览同步渲染。作业级“评分标准 Markdown”已经从前端移除；评分标准应写入作业内容，AI 评测的结构化评分则继续放在 AI 评测模块的 `criteria_items` 中。

Markdown 预览由前端 `renderContent` 统一处理，支持标题、段落、列表、行内代码、fenced code block 和基础表格。渲染前会转义用户输入，再把受支持的 Markdown 结构转换为 HTML，避免直接执行用户写入的 HTML。

教师端表格操作列改为紧凑图标按钮，并通过按钮 `title` 保留操作含义，减少窄屏下操作列挤压课程、作业和学生信息列的问题。程序评测和 AI 评测没有配置模块时，编辑页只保留新增按钮，预览页不显示空评测区域。

教师作业预览支持直接发布草稿。学生端提交项会根据最新提交状态显示“提交”或“重新提交”，重复提交会继续创建新的提交记录，业务侧按提交项读取最新一次提交参与展示和批改。

教师复核成绩时可以看到该学生本次作业所有最新提交文件，并通过 `GET /api/admin/submissions/:submission_id/download` 下载。下载接口会校验教师/管理员权限，并把目标文件限制在上传目录内。

程序评测报告现在保存完整用例细节，包括输入、期望输出、学生 stdout、stderr、返回码和错误答案的首个差异行。学生视角仍会隐藏隐藏用例的输入、期望输出、stdout、stderr 和 diff；教师提交列表使用 `include_private=True` 返回完整报告，便于复核。

AI 评测在本地任务中仍不执行外部 LLM 调用，但 `llm_details.modules` 会记录模块名称、输入文件、分值占比、评分项目、权重合计、指定输入和当前状态，前端复核弹窗可展开查看。

## 10. M3 批改状态与反馈发布

本轮新增 `assignment_reads` 表，用于记录学生是否打开过某个已发布作业。学生在作业列表点击作业详情时，前端调用 `POST /api/assignments/:assignment_id/read` 写入阅读记录；教师提交详情列表据此区分学生端状态：

- `未阅读`：学生尚未打开作业详情。
- `未提交`：学生已打开作业，但未完成必交提交项。
- `已提交`：学生已提交全部必交项。

教师端作业列表现在只保留“作业 / 代码 / 类型 / 截止时间 / 状态 / 操作”。状态标签格式为：

```text
草稿/已发布 n1/N n2/n1
```

其中 `N` 是教学班名单人数，`n1` 是已完成全部必交提交项的学生数，`n2` 是教师已发布反馈的学生数。

教师提交详情列表只显示序号、姓名、提交日期、状态。状态列同时展示：

- 学生端：未阅读 / 未提交 / 已提交。
- 教师端：待批改 / 待复核 / 已复核 / 已反馈。

点击已提交学生行后进入批改/复核弹窗。弹窗按学生上传文件时间顺序列出本次作业的最新提交文件，每个文件都提供：

- 在线预览：`GET /api/admin/submissions/:submission_id/preview`，M3 内联预览 `.py` 和 `.md`。
- 下载文件：`GET /api/admin/submissions/:submission_id/download`。
- 文件评分和文件评语。

文件会被标识为三类：

- `教师手动批改`：该提交项没有被程序评测或 AI 评测模块引用。
- `程序评测后复核`：该提交项绑定了程序评测，教师可查看用例、stdout/stderr 和差异行后复核。
- `AI 建议后复核`：该提交项绑定了 AI 评测，教师可查看结构化评分项目和当前 LLM 状态后复核。

总分由逐文件评分自动汇总并限制在作业总分内。教师可以“保存”批改草稿，也可以“预览反馈”生成 Markdown 报告，最后“发布反馈”。发布后 `assignment_grades.status=published`，学生端才会看到最终分和 Markdown 反馈报告；一旦反馈已发布，学生端重新提交会被后端拒绝。

Markdown 渲染已从轻量手写解析改为 `markdown-it`，代码块通过 `highlight.js` 按 fence 语言名高亮，例如 `python`、`c`、`cpp`；数学公式通过 `katex` 渲染，支持 `$...$` 行内公式和 `$$...$$` 块级公式。Markdown 的 HTML 输入仍不直接渲染。

## M3 更新：Docker OJ 超时与教师逐文件复核

### Docker Python OJ 超时语义

Python 程序评测仍由 `backend/app/services/judge.py` 负责。为了避免 Docker 镜像拉取、镜像检查或容器启动抖动占用学生程序的测试用例时间，评测流程调整为：

```text
run_python_judge
  -> docker image inspect JUDGE_DOCKER_IMAGE
  -> 镜像不存在时 docker pull，受 JUDGE_DOCKER_PREPARE_TIMEOUT 控制
  -> 逐个测试用例 docker run
  -> 容器内部使用 timeout --signal=KILL Ns python -I source.py
  -> 宿主机 subprocess timeout 只作为 Docker runner watchdog
```

这样，单个用例的超时由容器内部 `timeout` 控制；如果 Docker daemon 卡住或容器无法返回，宿主机 watchdog 会返回运行器错误，而不是误判为学生程序超时。

可配置项在 `backend/app/config.py`：

- `JUDGE_DOCKER_IMAGE`：默认 `python:3.11-slim`。
- `JUDGE_DOCKER_PREPARE_TIMEOUT`：默认 300 秒，用于镜像准备阶段。
- `JUDGE_DOCKER_HOST_TIMEOUT_BUFFER`：默认 30 秒，用例超时之外留给 Docker runner 的缓冲。

当前限制：首期仍只评测 Python 文件；Docker 镜像内依赖默认只有标准库。如果后续课程需要第三方包，应制作课程专用镜像并通过 `JUDGE_DOCKER_IMAGE` 指定。

### 教师逐文件复核

教师复核页在 `frontend/src/App.vue` 中改为以文件为中心组织：

- 顶部固定信息条展示学生序号、姓名、总分和教师端作业状态，滚动时保持可见。
- 每个提交文件独立展示在线预览、下载、评测结果、文件评分和评语。
- 程序评测文件显示用例表、学生输出、期望输出、标准错误和差异行，不再混入 AI 分析报告。
- AI 评测文件按输入文件匹配 AI 模块，并展示评分项目和权重。
- 未配置程序或 AI 模块的文件默认进入教师手动批改。
- 自动评测文件提供“重测”按钮，沿用现有提交级重跑接口刷新该学生作业的评测结果。

文件得分会附带满分与权重提示。前端保存前会校验文件权重合计为 100%；后端 `backend/app/routes/assignments.py` 的 `_normalize_file_reviews` 也会校验 `weight_percent`、`max_score` 和 `score`，避免绕过前端提交不一致成绩。

反馈报告生成逻辑保留 Markdown 输出，但表格增加了文件权重和文件满分列语义，便于学生查看每个文件的评分依据。旧的底部自动汇总分、评测状态和修改原因字段已从复核操作流中移除。

### Python OJ 命令行参数输入

程序测试用例只支持命令行参数输入：

- `args`：命令行运行参数，后端用 `shlex.split` 拆分后追加到 Docker 命令末尾，实际形态为 `python -I source.py <args...>`，供 `sys.argv` 使用。
- OJ 不再通过 stdin 向学生程序写入数据；学生代码应读取 `sys.argv[1:]`，而不是使用 `input()` 或 `sys.stdin.read()`。

`backend/app/routes/assignments.py` 会在保存作业时校验 `args`：最多 64 个参数，单个参数最多 200 字符，字符串总长度最多 1000 字符；引号不闭合等格式错误会直接拒绝保存。旧字段 `argv/arguments` 会兼容归一化到 `args`。

`backend/app/services/judge.py` 执行单个用例时只追加 argv，不传 `subprocess.run(input=...)`。隐藏用例序列化给学生时会遮蔽 `args/expected_output/stdout/stderr/diff`，教师端仍可在复核页查看完整测试结果。

### M3 更新：作业删除、退回重交与重发布重置

教师端新增两个管理动作：

- 删除作业：`DELETE /api/admin/assignments/<assignment_id>`。后端会先清理该作业相关的 `assignment_reads`、`assignment_grades`、`grading_results`、`judge_runs`、`submissions`，并尽量删除上传目录中的提交文件，最后删除 `assignments` 记录。
- 退回重交：`POST /api/admin/submissions/<submission_id>/return`。后端按该提交所属的 `assignment_id + student_user_id` 清理该学生本作业的提交、自动评测和教师批改结果。因为没有新增退回状态字段，学生端表现为该作业重新回到未提交/可提交状态。

已发布作业的修改采用显式重置机制：

```text
PATCH /api/admin/assignments/<assignment_id>
  -> 如果作业已发布且已有批改/评测记录，但请求未带 reset_grading=true，返回 409
  -> 教师确认后前端带 reset_grading=true 重新提交
  -> 后端清空该作业全部 AssignmentGrade / GradingResult / JudgeRun
  -> 保留学生提交文件
  -> 按新程序/AI评测模块重新运行自动批改
  -> 教师端进入待复核，学生端旧反馈不可见
```

AI 评测是教师辅助工具，不向学生暴露：学生端 `Assignment.to_dict(student_user_id=...)` 会把 `ai_evaluations` 置空；`AssignmentGrade.to_public_dict()` 和 `GradingResult.to_public_dict()` 会始终隐藏 `llm_score` 与 `llm_details`。教师端仍使用完整序列化查看 AI 模块、评分项目和辅助状态。

前端同步调整：

- 作业状态拆成三个标签：草稿/已发布、已提交人数 `n1/N`、已反馈人数 `n2/n1`。
- 教师按名单查看作业情况新增“总分”列，仅在已有最终分时显示。
- 批改弹窗新增“退回重交”按钮。
- 已发布作业保存时弹出重置提醒，教师确认后才提交 `reset_grading=true`。
- 日期展示统一走 `formatDate`，显示为 `YYYY-MM-DD`。

当前限制：退回重交会删除该学生本作业的提交记录和上传文件；如果后续需要保留退回历史，应新增提交状态或退回记录表，而不是继续用物理删除表达。
### M3 修复：教师复核页程序评测结果匹配

教师复核页的文件批改类型现在以作业中的评测模块配置为准：提交项 key 出现在 `program_evaluations.input_file_key` 中就显示“程序评测后复核”，出现在 `ai_evaluations.input_file_key` 中就显示“AI 建议后复核”，两者都没有配置时才进入教师手动批改。

此前前端会用 `latest_judge_run` 是否存在来推断文件类型，当程序评测运行失败、暂无用例结果或接口数据尚未刷新时，可能出现标签是“程序评测后复核”，正文却显示“未配置程序或 AI 评测”的错位。现在程序评测分支会始终展示评测模块、运行状态、自动得分和后端错误/跳过信息；只有存在 `details.cases` 时才展示用例表。用例展开区继续展示运行参数、期望输出、学生 stdout、stderr 和 diff。

新增回归测试覆盖多提交项作业：`code` 提交项绑定程序评测、`report` 提交项不绑定程序评测时，教师提交详情接口必须在 `code` 文件上返回完整 `latest_judge_run.details.cases`，且 `report` 文件不会附带程序评测结果。
### M3 修复：分文件批改保存与学生反馈入口

教师复核保存接口现在会复制 `AssignmentGrade.llm_details_json` 后再写入 `file_reviews`，避免 SQLAlchemy JSON 字段原地修改时未稳定标记 dirty，导致页面提示保存成功但重新打开丢失分文件评分和评语。保存后还会同步当前提交的 `GradingResult` 兼容记录，避免旧单文件兼容层和新的作业级成绩记录出现分叉。

分文件批改记录新增 `review_status`：`pending` 表示待确认，`confirmed` 表示教师已经确认该文件批改或复核。教师复核弹窗中，“程序评测后复核 / AI 建议后复核 / 教师手动批改”只表示评分来源，旁边单独显示“待确认批改 / 已确认批改 / 待确认复核 / 已确认复核”。每个文件提供确认按钮；点击总体“保存”或“发布反馈”时，会把当前文件评分和评语作为已确认结果保存。

教师反馈报告不再使用 Markdown 表格，而是按文件生成列表式章节：每个文件独立显示文件名、类型、权重、得分和长评语，避免长评语撑宽反馈页面。学生端作业详情页也不再直接贴出教师反馈，而是在作业标题区域提供“查看批改反馈”入口；点击后打开独立弹窗，学生可以更清楚地区分作业内容和批改结果。

学生端作业详情页的“需提交文件”表格简化为提交项、状态和操作。允许类型、大小上限、命名要求继续保留在点击提交文件后的上传弹窗里展示。
## M3 更新：确认提交、异步评测队列与 DeepSeek AI 评测

### 上传与确认提交的边界

学生端现在把上传文件和确认提交作业拆成两个动作：

- POST /api/assignments/<assignment_id>/submissions 只校验文件名模板并保存某个提交项的最新文件，状态写为 uploaded，不会启动 Python OJ 或 AI 评测。
- POST /api/assignments/<assignment_id>/confirm-submission 会检查必交提交项是否都已上传，并在确认时执行扩展名、大小和内容基本校验，通过后才把这些最新文件统一标记为 submitted 或 late。
- 确认提交后，后端清空该学生本作业旧的自动评测和教师批改结果，然后把自动评测任务放入队列。
- 学生端只有所有必交项都已上传时才显示可用的确认提交作业按钮；已发布反馈后，上传和确认提交都会被后端拒绝。

submissions.status 新增 uploaded。作业列表中的已提交人数只统计 submitted/late，因此单纯上传文件不会让教师端误以为学生已完成提交。

### 异步自动评测队列

自动评测入口位于 backend/app/services/grading_queue.py：

- init_grading_queue(app) 在 Flask app 创建时启动一个守护线程 worker。
- enqueue_auto_grading(app, assignment_id, student_user_id, reason) 只负责入队，生产和开发环境默认返回 queued。
- worker 在应用上下文中读取作业并调用 run_auto_grading_for_student，成功后提交事务，失败时回滚并写入应用日志。
- 测试环境通过 GRADING_QUEUE_INLINE=True 以内联方式执行，便于 pytest 立即断言评测结果。

当前队列是进程内队列，适合 M3 阶段验证业务闭环。上线如果使用多 Gunicorn worker，每个 worker 都会有自己的内存队列；后续要做可靠重试、跨进程调度或任务监控时，应替换为 Redis + RQ 或 Celery 这类持久化任务队列。

### DeepSeek / OpenAI 兼容 AI 评测

AI 评测已从占位状态升级为真实 OpenAI 兼容接口调用，核心文件为 backend/app/services/llm_grading.py。

- 教师在 TeacherLLMConfig 中配置 base_url、model、api_key 并启用后，AI 模块会请求 <base_url>/chat/completions。
- 首期按 DeepSeek 兼容 OpenAI Chat Completions 的形式发送 model、messages、temperature、response_format。
- 评分标准使用教师配置的 criteria_items，每项包含 content 和 weight，会作为 JSON rubric 放入 prompt。
- 模型必须返回 JSON：score、summary、criteria_results、feedback。
- AI 分数只作为教师辅助，教师端可见 llm_score 和 llm_details，学生端序列化会隐藏 AI 模块配置和 AI 细节。

可配置项在 backend/app/config.py：

- LLM_GRADING_TIMEOUT：默认 60 秒。
- GRADING_QUEUE_INLINE：默认 false；测试配置为 true。

### 教师复核状态

分文件复核仍保存在 AssignmentGrade.llm_details_json.file_reviews。每个文件有 review_status：

- pending：教师还未确认该文件批改或复核。
- confirmed：教师已确认该文件批改或复核。

前端展示时不再额外堆一个已复核标签，而是把原来的来源状态直接改为结果状态：程序文件从程序评测后待复核变为已复核，AI 文件从 AI 建议后待复核变为已复核，手动文件从手动待批改变为已批改。

### Markdown 模板修改位置

如果要自行修改作业和反馈的 Markdown 模板，主要看这些位置：

- 作业内容编辑与预览：frontend/src/App.vue 中的作业编辑页模板，以及 renderContent()。这里控制教师写作业说明时的实时预览效果。
- 新建作业表单默认内容：frontend/src/App.vue 中 assignmentForm、resetAssignmentForm()、openAssignmentEditor() 附近。可以在这里放入你常用的作业说明 Markdown 初始模板。
- 教师端反馈预览模板：frontend/src/App.vue 中 generatedFeedbackReport()。教师点击预览反馈时主要使用这里生成 Markdown。
- 后端兜底反馈模板：backend/app/routes/assignments.py 中 _build_feedback_report()。如果前端没有传 feedback，后端会用这里生成一份列表式 Markdown 反馈。
- 学生端反馈显示入口：frontend/src/App.vue 中 studentFeedbackDialogVisible 对应的批改反馈弹窗。

修改建议：优先同时保持前端 generatedFeedbackReport() 和后端 _build_feedback_report() 的结构一致；如果新增字段，需要同步更新 FileReview 类型、reviewFilePayloads() 和后端 _normalize_file_reviews()。
