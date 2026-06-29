# 身份、项目与后台管理 Spec

## 0. Codex 快速入口

- 先读文件：`backend/app/auth/router.py`、`backend/app/auth/dependencies.py`、`backend/app/auth/service.py`、`backend/app/admin/router.py`、`backend/app/models.py`、`frontend/src/store/auth.ts`、`frontend/src/views/AdminView.vue`。
- 最常改文件：`frontend/src/api/auth.ts`、`frontend/src/api/admin.ts`、`frontend/src/types/auth.ts`、`frontend/src/types/admin.ts`、`backend/app/admin/schemas.py`。
- 不要改契约：JWT 携带用户和当前项目；普通 API 的登录态失效使用 HTTP 401；项目成员校验不得静默放行跨项目访问。
- 新增功能入口：认证能力从 `/api/v1/auth/*` 接入；项目后台能力从 `/api/v1/admin/*` 接入。
- 必跑测试：`python -m pytest backend/tests/test_auth_bootstrap.py backend/tests/test_admin_projects.py backend/tests/test_admin_reset_password.py backend/tests/test_project_ai_config_api.py -q`；涉及前端表单时补跑相关 `frontend/tests/unit/*admin*.test.ts`。
- 常见误区：不要把项目级 AI、飞书机器人或 SVN 凭据写成个人配置；个人设置页只承担账号、密码和项目切换。

## 1. 模块目标

本模块负责多用户登录、项目上下文、角色权限和后台管理。它为个人校验、项目校验、规则配置、飞书机器人和项目级 AI 提供统一的身份与项目边界。

## 2. 用户入口与适用场景

| 路由 | 说明 |
|---|---|
| `/login` | 用户登录。 |
| `/register` | 注册用户并加入项目。 |
| `/admin` | 项目、成员、角色、密码、飞书机器人和项目级 AI 管理。 |
| `/profile` | 当前账号信息、修改密码、切换当前项目。 |

## 3. 核心概念

- `User`：系统用户。
- `Project`：配置、规则、飞书机器人和 AI 凭据的协作边界。
- `UserProjectRole`：用户在项目内的角色和权限。
- 当前项目：JWT 与前端 auth store 中的工作项目，影响所有项目级 API。
- 超级管理员：可管理全部项目；项目管理员只管理授权项目。
- 项目审计数据保留策略：用于保留不含原文和视觉内容的审计元数据；V2 不提供独立项目配置页，只有超级管理员可配置全局默认值，项目管理员只能查看。
- Source Evidence Cleanup Audit Summary：项目管理员可查看本项目的清理记录摘要，字段限定为 run id、来源标识、资源文件名、状态、创建时间、清理时间和操作人；不能查看已清理内容、视觉证据包或 observation 明细。
- 普通项目成员不能查看项目级清理记录列表；仅当自己当前页面引用的证据过期时看到“证据已清理/需重新读取来源”的状态提示。

## 4. 前端边界

- 路由守卫位于 `frontend/src/router/index.ts`，未登录访问受保护路由会跳转登录页。
- 登录态由 `frontend/src/store/auth.ts` 维护，API 请求走 `frontend/src/utils/apiFetch.ts` 注入 token。
- 管理后台页面位于 `frontend/src/views/AdminView.vue`，表单辅助逻辑分布在 `frontend/src/features/admin/`。
- 项目级 AI 表单使用 `frontend/src/api/projectAiConfig.ts` 和 `frontend/src/features/admin/projectAiConfigForm.ts`。

## 5. 后端边界

- 认证路由在 `backend/app/auth/router.py`，业务逻辑在 `backend/app/auth/service.py`。
- 当前用户、当前项目和严格项目成员校验在 `backend/app/auth/dependencies.py`。
- 后台路由在 `backend/app/admin/router.py`，请求/响应模型在 `backend/app/admin/schemas.py`。
- 默认项目和默认管理员播种在数据库初始化链路内完成。

## 6. 数据与持久化边界

- 用户、项目和角色关系由 `backend/app/models.py` 中的 ORM 模型维护。
- 默认管理员 `admin / 123456` 只适合 development；production 由配置安全检查阻断默认密码。
- 项目相关配置一律按 `project_id` 隔离；个人校验配置按 `project_id + user_id` 隔离。

## 7. API 契约

| API | 说明 |
|---|---|
| `POST /api/v1/auth/register` | 注册。 |
| `POST /api/v1/auth/login` | 登录并返回 token。 |
| `GET /api/v1/auth/me` | 获取当前用户、项目和角色信息。 |
| `POST /api/v1/auth/switch-project/{project_id}` | 切换当前项目。 |
| `POST /api/v1/auth/change-password` | 修改当前用户密码。 |
| `/api/v1/admin/projects*` | 项目 CRUD 与公开项目列表。 |
| `/api/v1/admin/projects/{project_id}/members*` | 项目成员与角色管理。 |
| `POST /api/v1/admin/users/{user_id}/reset-password` | 管理员重置密码。 |

## 8. 关键流程

1. 用户登录后，后端返回携带当前项目上下文的 token。
2. 前端调用 `/auth/me` 初始化用户、项目和角色状态。
3. 受保护页面通过路由守卫校验登录态，后台页面额外校验项目管理员权限。
4. 项目切换后，前端重置当前项目相关状态并重新进入对应页面。

## 9. 权限、安全与错误规则

- 认证失效使用 HTTP 401。
- 项目成员校验失败不得回退到默认项目。
- 项目审计数据保留策略的全局默认值仅超级管理员可配置；项目管理员可查看但不可按项目覆盖。
- 项目管理员查看清理记录时只返回本项目 `Source Evidence Cleanup Audit Summary` 字段白名单，不返回原文、图片/附件文件、视觉包、observation 明细、prompt 或生成结果历史。
- 普通项目成员不得调用项目级清理记录列表 API；过期提示只能绑定当前页面/当前 run 的可见状态，不提供跨 run 审计浏览。
- 生产环境必须配置固定 JWT 密钥、非默认管理员密码、CORS 来源和 SVN host 白名单。
- 密码、API Key、App Secret、SVN 密码不得在响应或日志中明文暴露。

## 10. 测试覆盖

- 后端：`test_auth_bootstrap.py`、`test_admin_projects.py`、`test_admin_reset_password.py`、`test_project_ai_config_api.py`、`test_admin_feishu_bot.py`。
- 前端：`projectAiConfigApi.test.ts`、`projectAiConfigForm.test.ts`、`adminFeishuBotApi.test.ts`、`FeishuBotConfigCardSvnTest.test.ts`。

## 11. 已知限制

- 当前不做 SaaS 化租户体系；项目是协作边界，不是完整租户隔离平台。
- 默认管理员仅用于本地开发和受控联调，生产必须显式修改。

## 12. 维护检查清单

- 新增后台能力时，确认角色边界和项目成员校验。
- 新增项目级配置时，确认是否属于项目管理员权限；涉及审计数据保留策略时，默认收口为超级管理员配置全局默认值、项目管理员只读查看。
- 修改登录或项目切换时，检查前端 store、路由守卫和 API 401 行为。
- 修改模型字段时，必须新增 Alembic migration 并跑迁移测试。
