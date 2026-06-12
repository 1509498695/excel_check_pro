# Excel Check 模块速查

> 本文档只用于快速定位代码边界。架构和接口契约见 [ARCHITECTURE.md](ARCHITECTURE.md)，启动和联调见 [../README.md](../README.md)。

## 1. 产品路由

| 路由 | 视图 | 作用 |
|---|---|---|
| `/` | `frontend/src/views/MainBoard.vue` | 个人校验四步工作流。 |
| `/fixed-rules` | `frontend/src/views/FixedRulesBoard.vue` | 项目校验配置、执行、导入和结果。 |
| `/rule-configs` | `frontend/src/views/RuleConfigsView.vue` | 规则配置工作区首页。 |
| `/rule-configs/config_lookup/:ruleId` | `frontend/src/views/RuleConfigLookupView.vue` | 配置表查询规则编辑、发布、历史和试运行。 |
| `/admin` | `frontend/src/views/AdminView.vue` | 项目、成员、角色、密码、飞书机器人和项目级 AI 管理。 |
| `/profile` | `frontend/src/views/ProfileView.vue` | 账号、密码和项目切换。 |
| `/user-guide` | `frontend/src/views/UserGuideView.vue` | 登录后使用说明。 |
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
| `backend/app/loaders/` | 本地 Excel、SVN、飞书电子表格读取。 |
| `backend/app/integrations/` | 飞书客户端、飞书机器人、长连接和文件下载集成。 |
| `backend/app/services/` | 跨模块业务服务，例如飞书表格授权记录。 |
| `backend/app/rules/` | 规则引擎、领域工具、handler 注册与执行。 |
| `backend/app/fixed_rules/` | 项目校验配置、迁移、导入、执行整合。 |
| `backend/app/ai/` | 项目级 AI 凭据读取、供应商协议、错误脱敏和基础调用能力。 |
| `backend/tests/` | 后端接口、引擎、AI 和导入回归测试。 |

## 4. 重点业务切片

开发前先读对应 Spec，再按前端、后端和测试入口定位代码。

| 切片 | Spec | 前端 | 后端 |
|---|---|---|---|
| 身份、项目与后台管理 | [specs/admin-auth-projects.md](specs/admin-auth-projects.md) | `views/AdminView.vue`、`views/LoginView.vue`、`views/ProfileView.vue`、`store/auth.ts` | `auth/`、`admin/router.py` |
| 个人校验 | [specs/workbench-personal-check.md](specs/workbench-personal-check.md) | `views/MainBoard.vue`、`store/workbench*`、`components/workbench/` | `api/workbench_api.py`、`api/execute_api.py`、`rules/` |
| 项目校验 | [specs/fixed-rules-project-check.md](specs/fixed-rules-project-check.md) | `views/FixedRulesBoard.vue`、`store/fixedRules.ts`、`features/fixed-rules-import/` | `api/fixed_rules_api.py`、`fixed_rules/` |
| 规则引擎与规则模型 | [specs/rule-engine.md](specs/rule-engine.md) | `rules/`、`features/rule-orchestration/`、`utils/taskTree.ts` | `rules/` |
| 数据源 | [specs/data-sources.md](specs/data-sources.md) | `components/workbench/DataSourcePanel.vue`、`api/workbench.ts`、`api/svn.ts` | `api/source_api.py`、`loaders/` |
| 飞书集成 | [specs/feishu-integration.md](specs/feishu-integration.md) | `components/admin/FeishuBotConfigCard.vue`、`components/workbench/DataSourcePanel.vue`、`api/admin.ts` | `admin/router.py`、`api/feishu_api.py`、`integrations/feishu_*`、`loaders/feishu_reader.py` |
| 规则配置工作区 / 配置表查询 | [specs/rule-configs-config-lookup.md](specs/rule-configs-config-lookup.md) | `views/RuleConfigsView.vue`、`views/RuleConfigLookupView.vue`、`api/ruleConfigs.ts`、`features/rule-configs/` | `api/rule_configs_api.py`、`rule_configs/`、`config_lookup/` |
| 项目级 AI 能力 | [specs/ai-project-credentials.md](specs/ai-project-credentials.md) | `features/ai/providerPresets.ts`、`features/admin/projectAiConfigForm.ts`、`api/projectAiConfig.ts` | `admin/router.py`、`ai/`、`services/*ai*`、`config_lookup/ai_matcher.py` |
| 执行任务与结果 | [specs/execution-runs-results.md](specs/execution-runs-results.md) | 个人和项目结果区、`api/fixedRules.ts`、`api/workbench.ts` | `api/execute_api.py`、`api/execute_runs_api.py`、`execution_*`、`result_*` |
| 交付、部署与工程治理 | [specs/delivery-devops.md](specs/delivery-devops.md) | `frontend/package-lock.json`、E2E 配置 | `scripts/`、`migrations/`、`.github/workflows/`、`backend/app/db_migrations.py` |

## 5. 文档入口

| 文档 | 作用 |
|---|---|
| [../README.md](../README.md) | 项目入口、启动、部署、联调。 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 稳定架构、核心契约、API 边界。 |
| [MODULES.md](MODULES.md) | 本文档：路由、代码位置和 Spec 定位。 |
| [STANDARDS.md](STANDARDS.md) | 开发与文档维护规范。 |
| [specs/](specs/) | Codex 开发前阅读的业务能力 Spec。 |
| [adr/](adr/) | 当前架构决策记录。 |
| [../frontend/README.md](../frontend/README.md) | 前端子项目说明。 |
| [../CHANGELOG.md](../CHANGELOG.md) | 版本级变化。 |
| [../PROJECT_RECORD.md](../PROJECT_RECORD.md) | 当前执行进度记录。 |
| [archive/](archive/) | 历史快照，不作为当前说明入口。 |
