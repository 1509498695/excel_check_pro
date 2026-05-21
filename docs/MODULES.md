# Excel Check 模块速查

> 本文档只用于快速定位代码边界。架构和接口契约见 [ARCHITECTURE.md](ARCHITECTURE.md)，启动和联调见 [../README.md](../README.md)。

## 1. 产品路由

| 路由 | 视图 | 作用 |
|---|---|---|
| `/` | `frontend/src/views/MainBoard.vue` | 个人校验四步工作流。 |
| `/fixed-rules` | `frontend/src/views/FixedRulesBoard.vue` | 项目校验配置、执行、导入和结果。 |
| `/admin` | `frontend/src/views/AdminView.vue` | 项目、成员、角色和密码管理。 |
| `/profile` | `frontend/src/views/ProfileView.vue` | 账号、密码、项目切换和 AI 配置。 |
| `/login` `/register` | `LoginView.vue` `RegisterView.vue` | 登录与注册。 |

## 2. 前端目录

| 路径 | 职责 |
|---|---|
| `frontend/src/api/` | HTTP 客户端。 |
| `frontend/src/types/` | API 与业务类型。 |
| `frontend/src/store/` | Pinia 状态。 |
| `frontend/src/router/` | 路由表、认证守卫和路由预加载。 |
| `frontend/src/views/` | 页面入口。 |
| `frontend/src/components/shell/` | 共享页面头、卡片、按钮、状态、表格和空态。 |
| `frontend/src/components/workbench/` | 个人校验业务组件。 |
| `frontend/src/features/` | 跨页面功能切片，例如个人规则导入项目校验。 |
| `frontend/src/rules/` | 规则前端模型、校验、摘要和工厂。 |
| `frontend/src/styles/` | 全局 token、Element Plus 校准和页面域样式。 |
| `frontend/src/utils/` | `TaskTree`、规则模型、下载、API fetch 等工具。 |

## 3. 后端目录

| 路径 | 职责 |
|---|---|
| `backend/run.py` | FastAPI 启动和生产静态托管兜底。 |
| `backend/config.py` | 应用配置、环境变量、SVN 可执行路径。 |
| `backend/app/database.py` | 异步 SQLAlchemy、建表、默认项目和管理员播种。 |
| `backend/app/auth/` | JWT、密码、当前用户/项目依赖、认证路由。 |
| `backend/app/admin/` | 项目、成员、角色和密码管理。 |
| `backend/app/api/` | `/api/v1` 聚合路由和业务 API。 |
| `backend/app/loaders/` | 本地 Excel、SVN、飞书占位读取。 |
| `backend/app/rules/` | 规则引擎、领域工具、handler 注册与执行。 |
| `backend/app/fixed_rules/` | 项目校验配置、迁移、导入、执行整合。 |
| `backend/app/ai/` | AI 规则助手、凭据、上下文、编译和草稿历史。 |
| `backend/tests/` | 后端接口、引擎、AI 和导入回归测试。 |

## 4. 重点业务切片

| 切片 | 前端 | 后端 |
|---|---|---|
| 个人校验 | `views/MainBoard.vue`、`store/workbench*`、`components/workbench/` | `api/workbench_api.py`、`api/execute_api.py`、`rules/` |
| 项目校验 | `views/FixedRulesBoard.vue`、`store/fixedRules.ts` | `api/fixed_rules_api.py`、`fixed_rules/` |
| 个人规则导入项目 | `features/fixed-rules-import/` | `fixed_rules/importer/` |
| AI 规则助手 | `components/workbench/ai/`、`api/ai.ts`、`store/ai.ts` | `api/ai_api.py`、`ai/` |
| 数据源 | `api/workbench.ts`、数据源面板组件 | `api/source_api.py`、`loaders/` |

## 5. 文档入口

| 文档 | 作用 |
|---|---|
| [../README.md](../README.md) | 项目入口、启动、部署、联调。 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 稳定架构、核心契约、API 边界。 |
| [MODULES.md](MODULES.md) | 本文档：路由和代码位置。 |
| [STANDARDS.md](STANDARDS.md) | 开发与文档维护规范。 |
| [../frontend/README.md](../frontend/README.md) | 前端子项目说明。 |
| [../CHANGELOG.md](../CHANGELOG.md) | 版本级变化。 |
| [archive/](archive/) | 历史快照，不作为当前说明入口。 |
