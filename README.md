# Excel Check

文档更新时间：2026-05-21 17:48

> 当前稳定文档入口只保留 6 份：本 README、[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)、[docs/MODULES.md](docs/MODULES.md)、[docs/STANDARDS.md](docs/STANDARDS.md)、[frontend/README.md](frontend/README.md) 与 [CHANGELOG.md](CHANGELOG.md)。历史需求、分钟级进度和一次性重构方案见 [docs/archive/](docs/archive/)。

Excel Check 是面向配置表校验的多用户 Web 应用。系统把数据源、变量、规则和结果统一到 `TaskTree`，支持个人临时校验和项目长期规则复用。

## 1. 当前能力

- 认证与权限：JWT 登录、注册、项目切换、三级角色；默认管理员 `admin / 123456`。
- 个人校验 `/`：数据源、变量池、规则编排、结果四步流程，统一走 `POST /api/v1/engine/execute`。
- 项目校验 `/fixed-rules`：项目级规则配置、从个人校验导入、执行、分页结果和 Excel 导出。
- 管理后台 `/admin`：项目、成员、角色、归属和密码管理。
- 个人设置 `/profile`：账号信息、密码、项目切换和 AI 模型配置。
- 数据源：本地 Excel、浏览器上传 Excel、SVN Excel；CSV 已下线，飞书仍为占位。
- 规则能力：10 类规则，覆盖单字段、固定值、正则、顺序、跨表映射和多种组合变量校验。
- AI 智能添加规则：在个人校验步骤 03 生成规则草稿，必须经预校验和用户确认后写入配置。

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

## 3. 快速开始

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

```powershell
cd frontend
npm install
```

启动后端：

```powershell
python backend/run.py
```

启动前端：

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

后端启动时会自动初始化 SQLite、默认项目和默认管理员。

## 4. 本机共享部署

用于服务运行在本机、同网段用户通过浏览器访问的场景：

```powershell
.\scripts\start-local-deploy.ps1
```

脚本会构建 `frontend/dist/` 并由 FastAPI 单服务托管，默认监听 `0.0.0.0:8000`。远程用户添加 Excel 数据源时应使用“上传文件”；服务器选择和手动路径只适合服务所在机器或共享盘路径。

建议首次共享前设置：

```powershell
$env:JWT_SECRET_KEY="替换为一段固定随机字符串"
$env:DEFAULT_SUPER_ADMIN_PASSWORD="替换默认管理员密码"
```

常用环境变量：`APP_HOST`、`APP_PORT`、`FRONTEND_DIST_DIR`、`CORS_ALLOW_ORIGINS`、`MAX_UPLOAD_MB`、`DB_URL`、`JWT_SECRET_KEY`、`DEFAULT_SUPER_ADMIN_PASSWORD`。

## 5. 测试与构建

```powershell
python -m pytest backend/tests -q
```

```powershell
cd frontend
npm run lint
npm run build
```

一键检查：

```powershell
.\scripts\check-standards.ps1
```

## 6. 最短联调

1. 启动后端和前端。
2. 打开 <http://127.0.0.1:5173/login>，使用 `admin / 123456` 登录。
3. 进入个人校验 `/`，添加 Excel 数据源、变量和规则。
4. 点击执行校验，确认结果区展示统计、异常明细和导出入口。
5. 可选：在 `/profile` 配置 AI 模型后，到步骤 03 生成并确认规则草稿。

## 7. API 速览

| 模块 | 常用入口 |
|---|---|
| 健康检查 | `GET /health` |
| 认证 | `POST /api/v1/auth/login`、`GET /api/v1/auth/me`、`POST /api/v1/auth/switch-project/{project_id}` |
| 数据源 | `GET /api/v1/sources/capabilities`、`POST /api/v1/sources/upload`、`POST /api/v1/sources/metadata` |
| 个人校验 | `GET/PUT /api/v1/workbench/config`、`POST /api/v1/workbench/svn-update`、`POST /api/v1/engine/execute` |
| AI 规则助手 | `GET/PUT/DELETE /api/v1/ai/providers/me`、`POST /api/v1/ai/agents/rule-draft`、`POST /api/v1/ai/agents/rule-prompt-optimize` |
| 项目校验 | `GET/PUT /api/v1/fixed-rules/config`、`GET/POST /api/v1/fixed-rules/import/workbench/{draft,preview,commit}`、`POST /api/v1/fixed-rules/execute` |
| 管理后台 | `/api/v1/admin/projects*`、`/api/v1/admin/projects/{id}/members*`、`POST /api/v1/admin/users/{id}/reset-password` |

完整协议见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 8. 文档入口

- 架构与协议：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- 模块速查：[docs/MODULES.md](docs/MODULES.md)
- 开发规范：[docs/STANDARDS.md](docs/STANDARDS.md)
- 前端说明：[frontend/README.md](frontend/README.md)
- 版本日志：[CHANGELOG.md](CHANGELOG.md)
- 历史归档：[docs/archive/](docs/archive/)
