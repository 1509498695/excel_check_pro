# 交付、部署与工程治理 Spec

## 0. Codex 快速入口

- 先读文件：`README.md`、`docs/STANDARDS.md`、`pyproject.toml`、`.github/workflows/`、`scripts/check-standards.py`、`scripts/release_package.py`、`scripts/check_release_package.py`、`backend/app/db_migrations.py`、`migrations/`。
- 最常改文件：`backend/requirements.in`、`backend/requirements.txt`、`frontend/package-lock.json`、`scripts/*.py`、`.github/workflows/*`。
- 不要改契约：源码包不包含 `.venv`、`node_modules`、`frontend/dist`、runtime、数据库、日志、密钥或本地凭据。
- 新增功能入口：数据库结构变更走 Alembic；检查流程走 `scripts/check-standards.py`；交付包规则走 release 和 check 双脚本。
- 必跑测试：`python -m pytest backend/tests/test_alembic_migrations.py backend/tests/test_devops_scripts.py backend/tests/test_release_package_scripts.py backend/tests/test_config_security.py backend/tests/test_local_deploy.py -q`。
- 常见误区：不要把手工 `ALTER TABLE` 累回 `database.py`；不要让 CI 或源码包依赖已存在的 `node_modules`。

## 1. 模块目标

本模块维护项目可复现安装、测试、构建、数据库迁移、源码交付和生产安全配置能力。

## 2. 用户入口与适用场景

- 新开发者从干净源码安装依赖。
- 本地运行完整检查。
- 生成源码交付包。
- 启动本机共享部署。
- 升级数据库结构。
- GitHub Actions 执行 CI。

## 3. 核心概念

- 干净源码：不包含依赖、构建产物和 runtime。
- 一键检查：后端依赖安装、ruff、pytest、前端 `npm ci`、lint、单元测试和构建。
- Alembic migration：数据库结构变更唯一入口。
- Production 安全检查：生产环境启动前强制检查关键配置。
- Release package：源码 zip，不是可直接运行的部署包。

## 4. 前端边界

- 前端依赖以 `frontend/package-lock.json` 为准，统一 `npm ci`。
- 前端构建输出 `frontend/dist/` 不进入源码包。
- Playwright E2E 是可选冒烟测试，失败时保留报告目录。

## 5. 后端边界

- 后端依赖由 `backend/requirements.in` 维护直接依赖，`backend/requirements.txt` 为锁文件。
- Ruff 配置在 `pyproject.toml`。
- Alembic 配置在 `alembic.ini`、`migrations/` 和 `backend/app/db_migrations.py`。
- 安全配置检查在 `backend/config.py`。

## 6. 数据与持久化边界

- 默认 SQLite 数据库位于 `backend/.runtime/`，属于 runtime。
- 上传目录、SVN 缓存、E2E runtime、日志、数据库和密钥文件不进入交付包。
- 正式升级旧库前必须备份数据库文件。

## 7. 命令契约

| 命令 | 说明 |
|---|---|
| `python backend/run.py` | 启动后端并自动执行 Alembic upgrade。 |
| `cd frontend && npm ci` | 前端干净安装。 |
| `.\scripts\check-standards.ps1` | Windows 一键检查。 |
| `python scripts/check-standards.py` | 跨平台一键检查。 |
| `python scripts/release_package.py` | 生成源码 zip。 |
| `python scripts/check_release_package.py <path>` | 检查源码包或目录。 |
| `.\scripts\start-local-deploy.ps1` | 本机共享部署。 |
| `python -m alembic revision --autogenerate -m "说明"` | 生成 migration。 |
| `python -m alembic upgrade head` | 手动升级数据库。 |

## 8. 关键流程

1. 干净源码先创建 Python venv，再安装后端锁定依赖。
2. 前端进入 `frontend/` 执行 `npm ci`。
3. 完整检查通过后再打包或提交。
4. 数据库结构变更先改 ORM，再生成并审查 migration。
5. Release 脚本生成源码 zip，检查脚本复核敏感路径。
6. production 启动前必须显式配置安全环境变量。

## 9. 权限、安全与错误规则

- `APP_ENV=production` 时必须配置 `JWT_SECRET_KEY`、`DEFAULT_SUPER_ADMIN_PASSWORD`、`CORS_ALLOW_ORIGINS`、`SVN_URL_ALLOWLIST`。
- production 禁止默认管理员密码 `123456` 和 CORS `*`。
- 发布包检查发现敏感路径直接失败。

## 10. 测试覆盖

- 后端：`test_alembic_migrations.py`、`test_devops_scripts.py`、`test_release_package_scripts.py`、`test_config_security.py`、`test_local_deploy.py`。
- 前端：`npm run lint`、`npm run test:unit`、`npm run build`、可选 `npm run e2e`。
- CI：GitHub Actions 覆盖后端 ruff/pytest 和前端 lint/unit/build；手动触发可跑 E2E。

## 11. 已知限制

- 当前不提供 Docker、systemd、Windows 服务、HTTPS、反向代理或容器编排方案。
- 源码包不是已构建部署包，解压后仍需安装依赖并构建。

## 12. 维护检查清单

- 新增依赖时同步锁文件和检查脚本测试。
- 新增 runtime 路径时同步 release 排除和检查规则。
- 修改生产配置时同步 README、测试和错误提示。
- 修改 CI 时确认本地一键检查仍可复现。
