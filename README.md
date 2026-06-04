# Excel Check

文档更新时间：2026-06-03 17:17

> 当前稳定文档入口保留 8 份：本 README、[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)、[docs/MODULES.md](docs/MODULES.md)、[docs/STANDARDS.md](docs/STANDARDS.md)、[docs/FRONTEND_STYLE_GUIDE.md](docs/FRONTEND_STYLE_GUIDE.md)、[frontend/README.md](frontend/README.md)、[CHANGELOG.md](CHANGELOG.md) 与 [PROJECT_RECORD.md](PROJECT_RECORD.md)。历史需求、旧分钟级进度和一次性重构方案见 [docs/archive/](docs/archive/)。

Excel Check 是面向配置表校验的多用户 Web 应用。系统把数据源、变量、规则和结果统一到 `TaskTree`，支持个人临时校验和项目长期规则复用。

## 1. 当前能力

- 认证与权限：JWT 登录、注册、项目切换、三级角色；默认管理员 `admin / 123456`。
- 个人校验 `/`：数据源、变量池、规则编排、结果四步流程，统一走 `POST /api/v1/engine/execute`。
- 项目校验 `/fixed-rules`：项目级规则配置、从个人校验导入、执行、分页结果和 Excel 导出。
- 管理后台 `/admin`：项目、成员、角色、归属和密码管理。
- 个人设置 `/profile`：账号信息、密码、项目切换、AI 模型配置和使用说明入口。
- 使用说明 `/user-guide`：面向业务用户的操作指引页。
- 数据源：本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格；CSV 已下线。
- 规则能力：11 类规则，覆盖单字段、固定值、正则、顺序、跨表映射、多种组合变量校验和 IAP 礼包校验。
- IAP 礼包校验：个人校验 03 规则页签可从飞书 Sheet 预览礼包规划明细，保存 `package_items_compare` 规则，并在执行时与结构化配置变量中的 `STR_Items` 做无序道具比对。
- AI 智能添加规则：在个人校验步骤 03 生成规则草稿，必须经预校验和用户确认后写入配置。
- 飞书接入：项目管理员配置飞书机器人后，个人校验可检测表格权限、发送群授权卡片、通过 OAuth 回调为机器人追加只读协作者，并读取 Sheet 元数据、列预览和执行数据。

## 2. 技术栈与地址

| 层 | 技术 |
|---|---|
| 后端 | FastAPI、SQLAlchemy Async、SQLite、python-jose、bcrypt、pandas |
| 前端 | Vue 3、TypeScript、Vite、Pinia、Element Plus、Tailwind v3 |
| 数据读取 | openpyxl、xlrd、SVN CLI |

默认开发地址：

- 前端：<http://127.0.0.1:5173>
- 后端健康检查：<http://127.0.0.1:8000/health>
- 后端 OpenAPI：<http://127.0.0.1:8000/docs>
- API 前缀：`/api/v1`

## 3. 干净源码首次安装

建议使用 Python 3.12、Node.js 20+ 和 npm 10+。源码包不会包含 `.venv`、`node_modules` 或 `frontend/dist`，解压后必须按 lock 文件重新安装依赖。前端应用依赖以 `frontend/package-lock.json` 为准，统一在 `frontend/` 内执行 `npm ci`；根目录 `node_modules` 不属于源码交付内容，也不作为前端应用启动入口。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

```powershell
cd frontend
npm ci
```

macOS / Linux / 通用 shell：

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
```

```bash
cd frontend
npm ci
```

后端依赖由 `backend/requirements.in` 维护直接依赖，`backend/requirements.txt` 是 `pip-compile` 生成的锁文件。需要升级后端依赖时，先修改 `requirements.in`，再执行：

```powershell
python -m pip install pip-tools
pip-compile --output-file backend/requirements.txt backend/requirements.in
```

## 4. 快速启动

启动后端：

```powershell
python backend/run.py
```

启动前端：

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

后端启动时会自动执行 Alembic 数据库迁移，并初始化默认项目和默认管理员。

## 5. 本机共享部署

用于服务运行在本机、同网段用户通过浏览器访问的场景：

```powershell
.\scripts\start-local-deploy.ps1
```

脚本会构建 `frontend/dist/` 并由 FastAPI 单服务托管，默认监听 `0.0.0.0:8000`。远程用户添加 Excel 数据源时应使用“上传文件”；服务器选择和手动路径只适合服务所在机器或共享盘路径。

默认 `APP_ENV=development`，用于本地快速启动。此模式会保留默认管理员 `admin / 123456`、开发期随机 JWT 密钥、CORS `*` 和默认 SVN host，仅限本地开发或受控联调。即使是本机共享，也建议首次共享前设置：

```powershell
$env:JWT_SECRET_KEY="替换为一段固定随机字符串"
$env:DEFAULT_SUPER_ADMIN_PASSWORD="替换默认管理员密码"
```

生产或对外可访问部署必须显式启用 production 并配置安全项：

```powershell
$env:APP_ENV="production"
$env:JWT_SECRET_KEY="替换为一段固定随机字符串"
$env:DEFAULT_SUPER_ADMIN_PASSWORD="替换为非 123456 的强密码"
$env:CORS_ALLOW_ORIGINS="https://excel-check.example.com"
$env:SVN_URL_ALLOWLIST="samosvn,svn.example.com"
```

`APP_ENV` 仅支持 `development` 和 `production`。当 `APP_ENV=production` 时，缺少 `JWT_SECRET_KEY`、`DEFAULT_SUPER_ADMIN_PASSWORD`、`CORS_ALLOW_ORIGINS`、`SVN_URL_ALLOWLIST` 任一配置，继续使用默认管理员密码 `123456`，或将 `CORS_ALLOW_ORIGINS` 设置为 `*`，后端都会启动失败并输出明确错误。

常用环境变量：`APP_ENV`、`APP_HOST`、`APP_PORT`、`FRONTEND_DIST_DIR`、`CORS_ALLOW_ORIGINS`、`MAX_UPLOAD_MB`、`DB_URL`、`JWT_SECRET_KEY`、`DEFAULT_SUPER_ADMIN_PASSWORD`、`SVN_URL_ALLOWLIST`、`LOCAL_FILE_ROOT_ALLOWLIST`、`ENABLE_LOCAL_PICKER`、`FEISHU_OAUTH_CALLBACK_URL`。

本地路径读取默认只允许浏览器上传目录和 SVN 缓存目录。若必须让服务端读取共享盘或固定目录内的 Excel，可设置 `LOCAL_FILE_ROOT_ALLOWLIST`，多个目录用英文逗号或分号分隔。`ENABLE_LOCAL_PICKER` 默认 `false`，共享或生产部署不建议开启；开启后仍只能选择 allowlist 内的 Excel。

## 6. 数据库初始化与迁移

数据库默认使用 SQLite，路径由 `DB_URL` 控制，默认运行库位于 `backend/.runtime/excel_check.db`。FastAPI 启动时会自动执行：

```powershell
python -m alembic upgrade head
```

全新数据库会由 Alembic 创建所有表；已有旧库会升级到当前版本，然后继续执行默认项目和默认管理员播种。正式升级旧库前，先停止服务并备份数据库文件：

```powershell
Copy-Item backend\.runtime\excel_check.db backend\.runtime\excel_check.db.bak
```

也可以手动执行或查看当前迁移版本：

```powershell
python -m alembic upgrade head
python -m alembic current
```

后续修改 `backend/app/models.py` 的表结构时，先生成并检查 migration，再运行测试：

```powershell
python -m alembic revision --autogenerate -m "说明"
python -m alembic upgrade head
python -m pytest backend/tests/test_alembic_migrations.py -q
```

不要再把新的 `ALTER TABLE` 自修复逻辑累积到 `backend/app/database.py`；结构变更应进入 `migrations/versions/`。

## 7. 执行方式：同步与任务

现有同步执行接口继续保留，适合小文件和前端当前流程：

- 个人校验：`POST /api/v1/engine/execute`
- 项目校验：`POST /api/v1/fixed-rules/execute`

大 Excel、SVN 或飞书校验可使用第一阶段任务接口，HTTP 请求只负责创建任务，实际执行由 FastAPI 进程内 `BackgroundTasks` 完成：

```powershell
POST /api/v1/execute-runs
GET  /api/v1/execute-runs/{run_id}
GET  /api/v1/execute-runs/{run_id}/items?page=1&size=20
```

创建个人校验任务时传 `scope_type="workbench"` 和 `task_tree`；创建项目校验任务时传 `scope_type="fixed_rules"`，可选 `selected_rule_ids`。任务状态包括 `pending`、`running`、`success`、`failed`、`cancelled`，状态接口会返回错误信息、开始时间、结束时间、耗时、扫描行数和异常总数。

第一阶段任务队列是进程内能力，不支持跨进程调度、失败重试、进度百分比或取消 API。服务重启时，遗留的 `pending/running` 任务会被标记为 `failed`，错误信息为“服务重启，任务未完成”。

## 8. 测试与构建

推荐使用一键检查脚本。脚本会创建或复用 `.venv`，安装锁定的后端依赖，执行 ruff 和 pytest，然后进入 `frontend` 使用 `npm ci` 重建依赖并完成 lint、单元测试和生产构建。

Windows PowerShell：

```powershell
.\scripts\check-standards.ps1
```

通用命令：

```bash
python scripts/check-standards.py
```

手动拆分执行时使用：

```powershell
python -m pip install -r backend\requirements.txt
python -m ruff check backend
python -m pytest backend/tests -q
cd frontend
npm ci
npm run lint
npm run test:unit
npm run build
```

检查脚本支持 dry-run 查看命令顺序：

```powershell
.\scripts\check-standards.ps1 -DryRun
python scripts/check-standards.py --dry-run
```

可选运行端到端冒烟测试。该测试会启动隔离后端、隔离 Vite 前端和独立 `.e2e-runtime/` SQLite/runtime，不依赖 SVN 或飞书：

```powershell
cd frontend
npm ci
npx playwright install chromium
npm run e2e
```

E2E 失败时会在 `frontend/test-results/` 和 `frontend/playwright-report/` 保留截图、trace 和视频。CI 可在常规 lint、单元测试和构建之外单独执行 `cd frontend && npm run e2e`。

GitHub Actions 已提供基础 CI：push、pull request 和手动触发会分别执行后端依赖安装、`ruff`、`pytest`、前端 `npm ci`、lint、单元测试和构建；手动触发 `workflow_dispatch` 时还会额外运行 Playwright E2E 冒烟测试。CI 不依赖任何已存在的 `node_modules`。

## 9. 源码交付包

正式交付源码时使用 release 脚本生成干净 zip：

```powershell
python scripts/release_package.py
```

默认输出到项目同级目录 `release-packages/`，文件名形如 `excel_check_pro-source-YYYYMMDD-HHMMSS.zip`。也可以显式指定输出目录：

```powershell
python scripts/release_package.py --output-dir D:\path\to\release
```

交付包只包含源码、配置示例、文档、lock 文件和测试资源，不包含运行时数据、依赖目录、构建产物、数据库、日志、密钥或凭据。脚本会排除 `.git/`、`.venv/`、`node_modules/`、`frontend/node_modules/`、`frontend/dist/`、`backend/.runtime/`、`.runtime_uploads/`、`.e2e-runtime/`、`__pycache__/`、SVN 缓存目录、`*.db`、`*.sqlite`、`*.log`、`*.key`、`*secret*` 本地数据文件和 `svn-credentials.json`。

如果从源码 zip 解压后构建失败，不要尝试修复压缩包中的 `node_modules` 权限或原生依赖；正确做法是确认包内没有 `node_modules`，然后按“干净源码首次安装”重新执行 `npm ci`。

交付前可单独检查目录或 zip：

```powershell
python scripts/check_release_package.py D:\path\to\package.zip
python scripts/check_release_package.py D:\path\to\extracted-package
```

检查脚本发现敏感路径会直接失败并输出违规路径；已有本地 runtime 文件不会被删除。

## 10. 最短联调

1. 启动后端和前端。
2. 打开 <http://127.0.0.1:5173/login>，使用 `admin / 123456` 登录。
3. 进入个人校验 `/`，添加 Excel 数据源、变量和规则。
4. 点击执行校验，确认结果区展示统计、异常明细和导出入口。
5. 可选：在 `/profile` 配置 AI 模型后，到步骤 03 生成并确认规则草稿。

## 11. API 速览

| 模块 | 常用入口 |
|---|---|
| 健康检查 | `GET /health` |
| 认证 | `POST /api/v1/auth/login`、`GET /api/v1/auth/me`、`POST /api/v1/auth/switch-project/{project_id}` |
| 数据源 | `GET /api/v1/sources/capabilities`、`POST /api/v1/sources/upload`、`POST /api/v1/sources/metadata`、`POST /api/v1/sources/column-preview`、`POST /api/v1/sources/composite-preview` |
| 飞书数据源 | `POST /api/v1/feishu/sources/check-permission`、`POST /api/v1/feishu/sources/send-authorization-card`、`GET /api/v1/feishu/sources/oauth/callback` |
| 个人校验 | `GET/PUT /api/v1/workbench/config`、`POST /api/v1/workbench/svn-update`、`POST /api/v1/workbench/package-items/preview`、`POST /api/v1/engine/execute` |
| 执行任务 | `POST /api/v1/execute-runs`、`GET /api/v1/execute-runs/{run_id}`、`GET /api/v1/execute-runs/{run_id}/items` |
| AI 规则助手 | `GET/PUT/DELETE /api/v1/ai/providers/me`、`POST /api/v1/ai/agents/rule-draft`、`POST /api/v1/ai/agents/rule-prompt-optimize`、`GET/DELETE /api/v1/ai/drafts`、`POST /api/v1/ai/drafts/{draft_id}/apply` |
| 项目校验 | `GET/PUT /api/v1/fixed-rules/config`、`GET/POST /api/v1/fixed-rules/import/workbench/{draft,preview,commit}`、`POST /api/v1/fixed-rules/execute` |
| 管理后台 | `/api/v1/admin/projects*`、`/api/v1/admin/projects/{id}/members*`、`POST /api/v1/admin/users/{id}/reset-password`、`/api/v1/admin/projects/{id}/feishu-bot*` |

完整协议见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 12. 文档入口

- 架构与协议：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- 模块速查：[docs/MODULES.md](docs/MODULES.md)
- 开发规范：[docs/STANDARDS.md](docs/STANDARDS.md)
- 前端样式规范：[docs/FRONTEND_STYLE_GUIDE.md](docs/FRONTEND_STYLE_GUIDE.md)
- 前端说明：[frontend/README.md](frontend/README.md)
- 版本日志：[CHANGELOG.md](CHANGELOG.md)
- 项目进度：[PROJECT_RECORD.md](PROJECT_RECORD.md)
- 历史归档：[docs/archive/](docs/archive/)
