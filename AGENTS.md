# AGENTS

## 项目定位

SunJudge 是一个 Flask + Vue 的教学型 Web 项目，用于课程作业、实验报告和 Python 编程题的提交、自动批改、教师复核与成绩导出。

开发时以 `PRD.md` 为准。每次实现重要功能时，除了写代码，还要用简洁语言说明实现逻辑、关键代码原理和当前限制。

## 核心约束

- 后端：Python、Flask、uv、SQLAlchemy、Alembic、pytest。
- 前端：Vue 3、Vite、TypeScript，优先使用 Element Plus。
- 本地数据库：SQLite。
- 云端数据库：MySQL。
- 云端部署：Ubuntu + Nginx + Gunicorn + Supervisor。
- 首期评测：只支持 Python。
- 首期文件：只处理 `.py` 和 `.md`。
- LLM：首期只封装 DeepSeek API，教师自己配置 API Key、base URL 和模型。
- ScoreManagerCLI：只导出可复制命令文本，不自动调用 CLI。

## 开发原则

1. 先读 `PRD.md` 和现有代码，再修改。
2. 优先完成教学流程闭环：教师建课建班、导入名单、学生提交、自动批改、教师复核、成绩导出。
3. 后端必须做权限、文件格式、命名规范和班级成员校验。
4. 不提交 `.env`、API Key、真实学生名单、成绩数据、上传文件和本地数据库。
5. 保持实现简单清晰，避免提前做复杂架构。
6. 改动后尽量运行相关测试或本地验证，并说明验证结果。

## 关键业务规则

- M1 已完成，后续开发不得破坏账号、教学班、名单导入和学生注册闭环。
- 教师账号需要管理员审批。
- 管理员只审批教师并查看教师/教学班层级列表，不创建教学班、不导入名单、不维护学生名单。
- 教师创建教学班时使用速记别名，例如 `OS202601`；邀请码与别名相同。
- Excel 中的课程名称、课程号、学期作为课程内部字段；Excel 中的学生班级只作为学生信息字段，不创建教学班。
- 教师创建教学班后导入学生名单，名单必须包含 No.、学号、姓名和学生信息班级；导入后允许教师在线增删改查未绑定账号的名单项。
- 学生注册不需要教师审批，也不填写昵称，只提交真实姓名、邀请码和密码。
- 学生注册邀请码格式为 `教学班别名-两位No.`，例如 `OS202601-06`；服务端必须校验真实姓名和 No. 与该教学班名单记录一致。
- 学生账号可按真实姓名和长学号自动绑定多个教学班；学生后续加入新班级时使用真实姓名、新邀请码和原密码。
- 学生登录只允许真实姓名或任一已绑定学生编号，不允许使用旧版本测试昵称登录。
- 右上角账号信息只显示角色文字和用户名：管理员橙色、教师蓝色、学生绿色；学生用户名显示真实姓名。
- 学生编号格式为 `教学班别名-两位No.`，例如 `OS202601-06`。
- 导出 ScoreManagerCLI 命令时只保留 `-` 后的短编号，例如 `32`。
- 学生只能提交自己所属班级的作业。
- LLM 评分只是建议，最终成绩必须由教师复核或发布。

学生短编号提取前必须先校验格式：

```python
def short_student_no(student_id: str) -> str:
    return student_id.rsplit("-", 1)[1]
```

ScoreManagerCLI 示例：

```shell
rd 32 homework 4
lab rd 32 exp1 88
brd 1,2,3 h 56
```

## 模块边界

- `routes`：处理 HTTP 请求、鉴权入口和参数校验。
- `models`：定义数据库模型。
- `services/file_validation.py`：文件类型、大小、命名和学生编号校验。
- `services/judge.py`：Python 评测逻辑。
- `services/llm_grading.py`：DeepSeek API 调用、prompt 和结构化结果解析。
- `services/score_export.py`：CSV 和 ScoreManagerCLI 命令导出。
- `tasks`：异步评测和 LLM 批改任务。

## 测试重点

- 教师审批与角色权限。
- 邀请码加入班级和学生名单匹配。
- 学生不能用昵称注册或登录。
- 学生多班级场景中，每个班级列表项和详情必须显示该班级 roster 的 `student_id/student_no/student_number`。
- 学生编号格式校验和短编号提取。
- `.py` / `.md` 文件规则和命名模板校验。
- Python 评测的通过、错误答案、运行错误和超时。
- LLM JSON 解析失败时的降级处理。
- ScoreManagerCLI 命令导出。

## Skill 使用

需要使用 Codex Skill 时，先阅读对应 `SKILL.md`：

- 构建或部署 Web 站点：`sites:sites-building`。
- 生成流程图、可视化说明或交互演示：`visualize`。
- 处理表格导入导出：`spreadsheets`。

本项目首期不处理 PDF/Word 作业解析，除非后续需求变更。

## 协作约定（重要）

- 每次完成阶段性代码开发或重要功能后，必须同步更新 `test.md` 和 `tutorial.md`：`test.md` 记录自动化测试、接口测试和手动验收步骤；`tutorial.md` 记录实现逻辑、关键代码原理和当前限制。
- 默认不主动启动本地开发服务。除非用户明确要求，否则不要运行 Flask/Vite 等长期驻留服务；如果为了验证临时启动了服务，结束前必须关闭并告知用户端口已释放。
- 修改 SQLAlchemy 模型且涉及数据库结构变化时，必须同时新增/更新 Alembic 迁移，并对本地 SQLite 执行 `uv run flask --app app:create_app db upgrade`；完成后检查关键表结构或迁移版本，避免 model 与 SQLite 不一致。
