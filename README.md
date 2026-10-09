# SunJudge

Flask + Vue 的教学作业平台，当前已完成 M1–M4：账号与审批、教学班/名单、作业多文件提交与确认、Docker Python 评测、DeepSeek 辅助评分、教师复核/发布、成绩统计及 CSV/ScoreManagerCLI 命令导出。正在进行 M5 稳定化和生产准备。

## 文档入口

- [生产部署步骤](docs/DEPLOYMENT.md)：Ubuntu、MySQL、Nginx、Gunicorn、Supervisor、HTTPS、备份/恢复/更新。
- [API 调用文档](docs/API.md)及[全部路由索引](docs/API_REFERENCE.md)。
- [腾讯云选型及现有域名配置](docs/CLOUD_AND_DOMAIN.md)。
- [收束记录与生产验收清单](docs/RELEASE_CHECKLIST.md)。
- [测试记录](test.md)、[实现教程与限制](tutorial.md)、PRD.md、AGENTS.md。

## 本地开发

```bash
cd backend
uv sync --locked
uv run flask --app app:create_app db upgrade
uv run flask --app app:create_app create-admin admin
uv run flask --app app:create_app run --debug
```

create-admin 会隐藏输入密码。按需复制 backend/.env.example 为 backend/.env，使用绝对SQLite路径更容易确认实际数据库位置；不要提交配置和数据库。本地默认SQLite，生产使用MySQL。

```bash
cd frontend
npm ci
npm run dev
```

前端通过 Vite 代理 /api 到 127.0.0.1:5000。生产构建用 npm run build，由 Nginx 提供 dist，不运行 Vite dev server。

## 验证

```bash
cd backend
uv run pytest -q
uv run python scripts/generate_api_reference.py --check
cd ../frontend
npm run build
```

修改接口后先重新生成索引，再使用 --check。测试使用内存SQLite和内联批改，不能替代Ubuntu/MySQL/Docker真实部署验收。

## 实现边界

routes 负责HTTP和权限入口；models 定义数据与序列化；services 封装名单、文件校验、评测、LLM与导出。学生用真实姓名及 教学班别名-两位No. 邀请码匹配名单，按姓名/长学号自动绑定多个班级；学生登录使用真实姓名或绑定编号。教师需审批，管理员不维护名单。

当前自动批改使用进程内串行队列；生产仅配置一个Gunicorn worker，重启任务恢复和公开评测安全限制见部署指南。教师分数只有发布后学生可见，AI分数只是建议。CLI导出严格校验编号后提取短编号，只生成文本。

首期规范要求.py/.md；现有代码还保留ZIP/图片提交能力，生产作业显式限定文件白名单。生产环境要求HTTPS、强Session密钥、可信Origin和LLM加密key；旧教师明文key需转换。未进行实际云端部署或100并发压测。
