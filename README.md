# SunJudge

SunJudge 是一个 Flask + Vue 的教学型 Web 项目，用于课程作业、实验报告和 Python 编程题的提交、自动批改、教师复核与成绩导出。

## M1 范围（已完成）

当前里程碑已实现项目脚手架与账号权限闭环：

- Flask 后端，使用 uv 管理依赖。
- SQLAlchemy 数据模型与 Alembic/Flask-Migrate 迁移。
- Flask-Login 服务端 Session 登录态。
- 学生基于班级名单注册、学生多登录名登录、教师申请、管理员审批、登录与退出。
- 教师创建教学班、导入 Excel 名单、在线维护名单。
- 管理员查看教师与教学班层级列表，但不创建教学班。
- Vue 3 + Vite + TypeScript + Element Plus 前端。

## 本地启动

后端：

```shell
cd backend
uv sync
uv run flask --app app:create_app db upgrade
uv run flask --app app:create_app create-admin admin admin123
uv run flask --app app:create_app run --debug
```

前端：

```shell
cd frontend
npm install
npm run dev
```

前端默认通过 Vite 代理访问 `http://127.0.0.1:5000/api`。

## M1 实现说明

账号权限的核心逻辑放在后端统一处理。`routes` 只负责 HTTP 参数和响应，`models` 定义持久化结构，`services/accounts.py` 封装学生编号校验和短编号提取规则。

学生注册不需要教师审批，也不需要昵称，只填写真实姓名、邀请码和密码。教师创建教学班时配置速记别名，例如 `OS202601`；邀请码与别名相同，学生实际注册时使用 `教学班别名-两位No.`，例如 `OS202601-06`。后端会校验真实姓名和 No. 是否匹配教师导入的 `class_rosters` 名单，匹配后创建账号，并继续用真实姓名和学号匹配其他班级名单，自动绑定同一学生的多个班级。学生后续加入新班级时，使用真实姓名、新邀请码和原密码即可绑定到原账号。学生登录时可使用真实姓名或任一已绑定学生编号，不再支持旧版本测试昵称；如果真实姓名匹配多个账号且密码也相同，后端会要求改用学生编号登录。Excel 中的自然班级只作为学生信息字段保存，不作为教学班。

教师注册后会以 `teacher_status=pending` 保存，登录时如果尚未审批会被拒绝。管理员通过审批接口把教师状态改为 `approved` 后，教师才能正常登录。管理员可查看现有教师和教学班，但不能创建教学班或维护名单。管理员账号不开放网页注册，需要通过 `create-admin` CLI 命令创建，避免普通用户自助注册为管理员。

前端 M1 采用简洁工作台布局。右上角只显示当前角色和用户名：管理员为橙色文字、教师为蓝色文字、学生为绿色文字；学生用户名显示真实姓名。教师页面默认只显示教学班列表，学生列表、导入名单、编辑学生和课程信息编辑都通过按钮唤起。

当前限制：

- M1 暂未加入 CSRF 防护，后续部署前需要补齐。
- M1 已完成账号权限、教学班、Excel 名单导入和注册所需的最小名单管理能力，作业提交、批改和导出放在后续里程碑。
- 本地默认 SQLite，云端 MySQL 配置会在部署里程碑补充。
