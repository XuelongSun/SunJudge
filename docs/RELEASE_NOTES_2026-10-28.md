# 2026-10-28 更新说明

本次包含后端、数据库迁移和前端更新，三者需要配套部署。

## 主要变化

- 学生图片库容量上限为30MiB，超额历史图片保留，只限制继续上传。
- CSV导出新增原始成绩、比例因子、最终成绩列；最终成绩保留两位小数，ScoreManagerCLI也使用折算结果，可整批复制或下载命令文本。原数据库成绩不变，重复导入CLI可能重复记分。
- 已发布作业修改后重新发布，可选择保留已有提交或要求学生重交。需要延期、修订说明时选择保留；要求重交会清空批改结果，文件与草稿保留供学生重新确认。
- 教师可在截止后为指定学生允许补交。确认成功后授权消耗，列表和指标按截止日期记提交时间并标注补交，实际提交时间仍保留。
- 主说明仍独立编辑，另有最多4个Python/Markdown附件，可设置文件名、用途，Markdown附件支持在线编辑。
- 师生附件和批改预览共用弹窗，支持亮暗主题、下载及复制原始源码。复制需要浏览器支持并允许剪贴板访问，生产继续使用HTTPS。

## 更新顺序

以下命令沿用仓库部署模板的路径、应用用户和Supervisor服务名；实际部署有调整时使用自己的配置。不要重走初始化流程。

1. 本地保留旧提交号和旧前端包，将本次提交推送到服务器可访问的仓库。前端构建产物`frontend/dist`被Git忽略，需要另行部署，只有Git拉取不会更新网页。
2. 通知师生保存编辑、暂停新提交，等现有程序/AI批改结束。当前批改队列在进程内，重启不会持久保留待运行任务。
3. 管理员停止应用并备份，确认备份完成目录有效；备份脚本应已按现有部署手册安装：

   ```bash
   sudo supervisorctl stop sunjudge
   sudo /usr/local/sbin/sunjudge-backup
   ```

   备份须同时包含MySQL和整个上传目录，包括图片和学生提交；单独备份代码不够。妥善保留原`.env`、`SECRET_KEY`和`LLM_ENCRYPTION_KEY`。

4. 切换应用用户，先检查服务器本地修改，再获取并切换到本次已验证提交。`VERIFIED_COMMIT`替换为实际提交号，不使用强制重置覆盖本地文件。

   ```bash
   sudo -iu sunjudge
   cd /srv/sunjudge
   git status --short
   git fetch origin
   git checkout VERIFIED_COMMIT
   cd backend
   ~/.local/bin/uv sync --locked --no-dev --python 3.11
   GRADING_QUEUE_ENABLED=false ~/.local/bin/uv run --no-sync flask --app app:create_app db upgrade
   GRADING_QUEUE_ENABLED=false ~/.local/bin/uv run --no-sync flask --app app:create_app db current
   GRADING_QUEUE_ENABLED=false ~/.local/bin/uv run --no-sync flask --app app:create_app db check
   exit
   ```

   目标迁移版本为`c9e53f10642d (head)`，`db check`应无结构差异。出现错误时保留日志并停止后续上线，不用`stamp head`跳过迁移。

5. 部署与该提交匹配的前端`dist`，保留旧包。生产无需启动Vite。本次未修改依赖锁文件、Nginx、Supervisor模板或环境变量，不需要新增配置项；继续使用原生产配置。
6. 启动并验收，再恢复提交：

   ```bash
   sudo supervisorctl start sunjudge
   sudo supervisorctl status sunjudge
   curl --fail https://judge.xuelongsun.cn/api/health
   ```

   验收登录、旧说明/图片/草稿、附件上传/编辑/预览/下载/复制、一份模拟学生提交与反馈、保留提交后延期、指定补交及带比例因子的CSV/CLI导出。浏览器强制刷新以清除仍打开的旧版前端。

## 数据与兼容性

- `a7c31d9e420b`：新增指定学生覆盖表，以及提交的补交标记、有效提交时间。
- `b8d42e0f531c`：新增`assignments.code_templates_json`，先回填空数组再设非空，已有作业没有附件时无需手动补数据。
- `c9e53f10642d`：仅整理附件JSON，取消旧主文件标记并补充用途。保留原主说明、草稿、全部附件正文及ID。若曾使用中间版本留下5个附件，仍可查看下载，再次保存附件列表时需整理到4个以内。
- CSV列结构发生变化，依赖固定列号的外部脚本需按新表头调整；因子默认1，导出不修改平台成绩。
- 单附件上限1MiB；附件属于作业配置，随数据库备份，不落到独立上传文件。图片和学生提交继续依赖上传目录。
- 本地SQLite迁移已验证；生产Ubuntu/MySQL实际迁移及浏览器验收仍应在维护窗口完成，不能用本地测试替代。
- 迁移后不要仅切回旧代码或盲目降级；回退应使用匹配版本的代码、数据库、上传目录和密钥。JSON整理迁移不逆向猜测已取消的主文件标记。

使用方法见[用户操作说明](USER_GUIDE.md)。

## 提交前验证

- 后端完整回归：`uv run pytest -q`，186 passed。存在已有Flask-SQLAlchemy迁移接口弃用提示，不影响此次测试通过。
- 前端最近一次完整验证：`npm test`，43 passed；`npm run build`通过类型检查和生产构建，保留既有依赖注释及大包提示。
- 本地SQLite已升级至`c9e53f10642d`，模型结构检查无差异；API路由索引及Git空白检查通过。
- 未启动开发服务，未执行生产部署或远端MySQL迁移。
