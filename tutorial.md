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
  "grading_criteria": "Evaluate clarity and completeness.",
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

教师可分别为作业说明和评分标准选择：

- `TXT`：按纯文本显示，换行保留。
- `Markdown`：学生详情页渲染标题、列表、加粗、行内代码和段落。

前端当前使用轻量本地渲染函数，并先转义 HTML，再处理有限 Markdown 语法，避免直接渲染未转义 HTML。后续如需要完整 Markdown，可引入成熟 Markdown 渲染库并配合 sanitizer。

### 6.4 学生端交互调整

学生端从“按钮进入”改为“整行点击”：

- 班级列表显示 `pending_assignment_count`，即已发布但当前学生还没有提交的作业数量。
- 班级列表不再显示操作列；点击整行后高亮当前班级并显示详情。
- 作业列表不显示作业代码、作业类型和操作列；点击整行后高亮当前作业。
- 作业详情页显示说明、文件规则、评分标准和提交按钮。

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
- 新建/编辑作业弹窗底部的“预览”：按当前表单内容即时生成预览，即使尚未保存也可以检查展示效果。

预览复用学生详情页的核心渲染逻辑：

- 作业说明按 `description_format` 以 TXT 或 Markdown 渲染。
- 评分标准按 `rubric_format` 以 TXT 或 Markdown 渲染。
- 文件规则显示允许扩展名、大小上限和命名模板。
- 教师额外看到程序评测和 AI 评测模块摘要，包括名称、成绩占比、输入、期望输出、超时、隐藏用例和 AI 评分标准。

这样教师在发布前可以确认学生视角的说明和评分标准是否清晰，同时检查自动评测模块配置是否完整。

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
