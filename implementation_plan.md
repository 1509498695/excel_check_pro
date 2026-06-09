# 配置表查询与共享飞书机器人实施梳理

> 本文基于 `CONTEXT.md`、`C:/Users/chenzhen/Desktop/飞书查询配置表文档.md` 与当前代码阅读整理。本文只描述实施计划与代码位置，不改业务代码，不新增数据库迁移。

## 1. 现有项目模型、成员权限、项目级配置代码位置

### 后端项目与成员模型

| 领域 | 代码位置 | 现状 |
|---|---|---|
| 项目表 | `backend/app/models.py:13` `Project` | 项目基础信息，`name` 唯一，关联成员。 |
| 用户表 | `backend/app/models.py:29` `User` | 用户账号、超级管理员标记、当前主项目。 |
| 用户-项目角色 | `backend/app/models.py:53` `UserProjectRole` | `role` 为 `admin` 或 `user`，按项目隔离权限。 |
| 项目校验配置 | `backend/app/models.py:72` `FixedRulesConfigRecord` | 项目级固定规则 JSON，按 `project_id` 隔离。 |
| 个人工作台配置 | `backend/app/models.py:87` `WorkbenchConfigRecord` | 按 `project_id + user_id` 隔离。 |
| 个人 AI 凭据 | `backend/app/models.py:105` `AiProviderCredentialRecord` | 当前是用户级，不满足项目级 AI 凭据需求。 |
| 飞书机器人配置 | `backend/app/models.py:212` `FeishuBotConfigRecord` | 项目级一条记录；当前包含 App ID/Secret、默认群、白名单、下载根目录。 |

### 权限与项目上下文

| 领域 | 代码位置 | 现状 |
|---|---|---|
| 请求身份上下文 | `backend/app/auth/dependencies.py:20` `CurrentUserContext` | 封装当前用户、项目与角色。 |
| 项目成员权限 | `backend/app/auth/dependencies.py:57` `require_project_member` | 成员和超级管理员可访问项目功能。 |
| 严格项目成员权限 | `backend/app/auth/dependencies.py:72` `require_strict_project_member` | 数据源接口使用，避免 token 项目静默回退。 |
| 项目管理员权限 | `backend/app/auth/dependencies.py:82` `require_project_admin` | 管理员或超级管理员可操作。 |
| 项目管理接口 | `backend/app/admin/router.py` | 项目 CRUD、成员管理、飞书机器人配置集中在一个路由文件。 |

### 项目级配置读写

| 配置类型 | 代码位置 | 说明 |
|---|---|---|
| 固定规则配置 API | `backend/app/api/fixed_rules_api.py:187` 读取，`:274` 保存 | 项目成员可读写当前项目固定规则。 |
| 固定规则 DB 服务 | `backend/app/fixed_rules/db_service.py` | `load_fixed_rules_config_from_db`、`save_fixed_rules_config_to_db`。 |
| 工作台配置 API | `backend/app/api/workbench_api.py:698` 读取，`:719` 保存 | 当前用户当前项目的个人配置。 |
| 飞书机器人配置 API | `backend/app/admin/router.py:606` 读取，`:629` 保存，`:772` 删除 | 目前要求项目管理员权限。 |

## 2. 现有飞书机器人配置、长连接、消息分发、命令解析代码位置

### 配置与 OpenAPI 客户端

| 领域 | 代码位置 | 现状 |
|---|---|---|
| 飞书配置 schema | `backend/app/admin/schemas.py` `FeishuBotConfigUpdateRequest` | 当前字段不含绑定群列表、查询根、项目级 SVN/AI 凭据。 |
| 飞书配置序列化 | `backend/app/admin/router.py` `_serialize_feishu_bot_config` | 返回脱敏 App Secret 状态、下载根、连接状态。 |
| 飞书 token 与消息发送 | `backend/app/integrations/feishu_bot.py` | 按 `project_id` 缓存 tenant token；发送 text/card/file。 |
| token 获取 | `backend/app/integrations/feishu_bot.py:162` `get_tenant_access_token` | 从项目机器人配置读取 app secret 并缓存。 |

### 长连接 supervisor 与事件分发

| 领域 | 代码位置 | 现状 |
|---|---|---|
| 长连接 supervisor | `backend/app/integrations/feishu_long_conn.py:686` `FeishuLongConnSupervisor` | 当前按 `project_id` 管理客户端。 |
| app_id 独占逻辑 | `FeishuLongConnSupervisor.start_one` | 当前 `_app_id_owner` 会阻止不同项目复用同一 `app_id`。 |
| 单项目事件 handler | `_build_event_handler` / `_make_message_callback` | 回调绑定固定 `project_id`。 |
| 消息分发入口 | `backend/app/integrations/feishu_long_conn.py:559` `dispatch_message_event` | 当前根据文本识别项目校验、下载、目录查询。 |
| 下载命令处理 | `backend/app/integrations/feishu_long_conn.py:376` `_handle_download_command` | 使用飞书配置中的本地/SVN 下载根。 |
| 目录查询命令处理 | `backend/app/integrations/feishu_long_conn.py:448` `_handle_query_command` | 使用 `extract_query_request` 与 `resolve_query_listing`。 |

### 命令解析

| 领域 | 代码位置 | 现状 |
|---|---|---|
| 项目校验命令 | `matches_project_check_command` | 支持纯文本“项目校验”和 @ 机器人后跟“项目校验”。 |
| 下载命令解析 | `backend/app/integrations/feishu_download.py:55` `extract_download_path` | 格式为 `@机器人 下载 <文件路径>`。 |
| 目录查询命令解析 | `backend/app/integrations/feishu_download.py:75` `extract_query_request` | 格式为 `@机器人 查询 <目录> <前缀>`。 |
| 目录查询结果分段 | `backend/app/integrations/feishu_long_conn.py` `_split_text_messages` | 当前用于目录查询消息分段，最大约 3500 字符。 |

## 3. 现有 SVN 下载、Excel 文件读取、缓存刷新代码位置

### SVN 工作副本与远端缓存

| 领域 | 代码位置 | 现状 |
|---|---|---|
| SVN CLI 探测/update | `backend/app/loaders/svn_manager.py` | `update_svn_working_copy` 处理本地工作副本 update、cleanup、文件占用恢复。 |
| SVN 远端 list/checkout/update | `backend/app/loaders/svn_manager.py` | `list_svn_directory`、`checkout_remote_directory`、`update_remote_cache_directory`。 |
| 远端缓存入口 | `backend/app/loaders/svn_cache.py:110` `prepare_remote_svn_source` | HTTP(S) SVN URL 按目录 hash 落到 `settings.svn_cache_dir`。 |
| 强制刷新 | `prepare_remote_svn_source(..., force_refresh=True)` | 绕过 TTL 执行远端缓存 update。 |
| 缓存状态 | `backend/app/loaders/svn_cache.py` `get_remote_cache_state` | 返回缓存路径、revision、更新时间。 |
| SVN 个人凭据 | `backend/app/loaders/svn_credentials.py` | 当前按 `user_scope + host` 加密存储，不是项目级凭据。 |

### 飞书机器人下载/目录查询

| 领域 | 代码位置 | 现状 |
|---|---|---|
| 下载文件解析 | `backend/app/integrations/feishu_download.py:197` `resolve_download_file` | 基于配置的本地/SVN 工作副本根目录解析文件。 |
| 查询目录解析 | `backend/app/integrations/feishu_download.py:109` `resolve_query_listing` | 查询根目录下一级目录/文件名。 |
| 路径安全 | `feishu_download.py` `_reject_relative_escape`、`_is_relative_to` | 禁止绝对路径、盘符、`..`，并限制在配置根内。 |

### Excel 读取

| 领域 | 代码位置 | 现状 |
|---|---|---|
| 元数据读取 | `backend/app/loaders/local_reader.py:66` `read_source_metadata` | 读取 Excel sheet 与列结构。 |
| 列预览 | `preview_source_column`、`preview_composite_variable` | 读取指定列或组合变量预览。 |
| 变量读取 | `read_local_excel` | 使用 pandas `ExcelFile.parse` 读取 sheet/列。 |
| 数据源路径解析 | `backend/app/loaders/local_reader.py:468` `_resolve_source_path` | SVN 远端 URL 会调用 `prepare_remote_svn_source`。 |
| Excel engine | `_get_excel_engine` | `.xls` 使用 `xlrd`，`.xlsx` 使用 `openpyxl`。 |

## 4. 现有 AI provider 或大模型调用封装代码位置

| 领域 | 代码位置 | 现状 |
|---|---|---|
| Provider 预设 | `backend/app/ai/providers.py` `PROVIDER_PRESETS` | OpenAI、Anthropic、Gemini、DeepSeek、Qwen 等。 |
| 统一调用 | `backend/app/ai/providers.py:134` `call_provider_json` | 调用上游模型并解析 JSON。 |
| Provider 门面 | `backend/app/ai/provider_client.py:11` `call_model_json` | 保留可注入 caller 的薄封装。 |
| 个人凭据读取 | `backend/app/ai/credentials.py` | `load_user_credential`、`decrypt_credential_key`、`parse_extra_headers`。 |
| AI API | `backend/app/api/ai_api.py` | 当前 `/ai/providers/me` 是用户级配置。 |
| AI 规则服务 | `backend/app/ai/agent_service.py` | 个人校验智能规则草稿入口。 |
| 供应商连通测试 | `backend/app/ai/providers.py` `test_provider_connection` | 用最小 JSON 请求测试。 |

本需求的“项目级 AI 凭据”不能直接复用 `AiProviderCredentialRecord`，需要新增项目级凭据模型/服务，并复用 `providers.call_provider_json` 作为底层调用边界。

## 5. 现有前端项目配置页面、导航、权限控制、表单组件代码位置

### 路由、导航、权限

| 领域 | 代码位置 | 现状 |
|---|---|---|
| 主导航 | `frontend/src/App.vue:27` `navItems` | 个人校验、项目校验、管理后台、个人设置。 |
| 管理后台可见性 | `frontend/src/App.vue:53` | `show: auth.isProjectAdmin`。 |
| 路由表 | `frontend/src/router/index.ts` | `/fixed-rules` 成员可访问，`/admin` 需要 admin meta。 |
| 路由守卫 | `frontend/src/router/index.ts:69` | `to.meta.admin && !auth.isProjectAdmin` 时跳回主页。 |
| 预加载 | `frontend/src/router/routePreload.ts` | 当前未包含规则配置页。 |
| 权限状态 | `frontend/src/store/auth.ts` | `isProjectAdmin`、`currentRole`、`currentProjectId`。 |

### 项目配置与表单组件

| 领域 | 代码位置 | 现状 |
|---|---|---|
| 管理后台页面 | `frontend/src/views/AdminView.vue` | 项目列表、项目详情、成员管理、飞书机器人卡片。 |
| 飞书配置卡片 | `frontend/src/components/admin/FeishuBotConfigCard.vue` | App ID/Secret、默认群、白名单、下载根、后缀、测试发送。 |
| 飞书配置 API | `frontend/src/api/admin.ts:101` 起 | `apiGetFeishuBotConfig`、`apiUpsertFeishuBotConfig`、`apiDeleteFeishuBotConfig`。 |
| 飞书配置类型 | `frontend/src/types/admin.ts` | `FeishuBotConfig`、`FeishuBotConfigPayload`。 |
| 个人 AI 设置 | `frontend/src/components/profile/AiProviderSettingsCard.vue` | 用户级 AI provider 配置和测试。 |
| 数据源面板 | `frontend/src/components/workbench/DataSourcePanel.vue` | 复用 Element Plus 表单、SVN 选择器、SVN 凭据弹窗。 |
| SVN 选择器 | `frontend/src/components/workbench/SvnPickerDialog.vue` | 远端目录浏览。 |
| SVN 凭据弹窗 | `frontend/src/components/workbench/SvnCredentialDialog.vue` | 用户级 SVN host 凭据录入。 |
| 共享 shell 组件 | `frontend/src/components/shell/*` | `AppCard`、`PageHeader`、`SectionHeader`、`PrimaryButton`、`SecondaryButton`、`StatusBadge` 等。 |

## 6. 本需求需要新增/修改的模块、模型、测试

### 后端新增模块

| 模块 | 类型 | 职责 |
|---|---|---|
| `backend/app/config_lookup/__init__.py` | 新增 | 配置表查询模块导出。 |
| `backend/app/config_lookup/schemas.py` | 新增 | 查询规则、分页、引用、输出字段、试查请求/响应等 Pydantic/domain 类型。 |
| `backend/app/config_lookup/markdown_parser.py` | 新增 | 解析中文 Markdown/YAML 配置，固定中文字段白名单，不支持同义词。 |
| `backend/app/config_lookup/validator.py` | 新增 | 发布前结构校验：查询类型唯一、路径相对、字段合法；不读真实 SVN Excel。 |
| `backend/app/config_lookup/repository.py` | 新增 | 草稿、发布版本、版本历史、回滚的 DB 读写。 |
| `backend/app/config_lookup/runtime.py` | 新增 | 根据发布配置执行配置表查询，读取 SVN 最新 Excel。 |
| `backend/app/config_lookup/path_resolver.py` | 新增 | query root + 版本目录 + 配置文件的安全拼接和远端 URL 构造。 |
| `backend/app/config_lookup/name_matcher.py` | 新增 | ID 优先、名称匹配、AI 候选排序；AI 不选择查询类型、不解析 Markdown。 |
| `backend/app/config_lookup/formatter.py` | 新增 | 查询结果格式化和飞书消息分段。 |
| `backend/app/config_lookup/project_credentials.py` | 新增 | 项目级 SVN/AI 凭据加密读写、脱敏状态、连接测试辅助。 |
| `backend/app/api/rule_config_api.py` | 新增 | 规则配置页 API：读取、保存草稿、校验、发布、历史、回滚、试查、凭据状态。 |

### 后端修改模块

| 模块 | 修改点 |
|---|---|
| `backend/app/api/router.py` | 注册 `rule_config_api`。 |
| `backend/app/models.py` | 新增规则配置、群绑定、query root、项目 SVN 凭据、项目 AI 凭据模型；扩展或拆分飞书项目配置。 |
| `backend/app/db_migrations.py` 或启动补表逻辑 | 在“不新增 Alembic 迁移”的前提下，如项目已有运行时补 schema 机制，应补齐新增表/列；需要单独确认生产部署策略。 |
| `backend/app/admin/schemas.py` | 扩展飞书配置 payload：群绑定、query roots、AI 阈值、候选数量、凭据状态输入。 |
| `backend/app/admin/router.py` | 支持共享 App ID、校验同 App Secret 一致、校验群绑定唯一、默认群必须在绑定群列表内、序列化脱敏状态。 |
| `backend/app/integrations/feishu_bot.py` | token 缓存维度需要从 `project_id` 调整或兼容到共享 `app_id`，避免相同 app 重复取 token。 |
| `backend/app/integrations/feishu_long_conn.py` | supervisor 从 `project_id -> client` 改为 `app_id -> client`；事件按 `chat_id` 路由到项目；加入配置表查询命令分发。 |
| `backend/app/loaders/svn_cache.py` | 为配置表查询提供项目级 SVN 凭据注入点和强制刷新路径。 |
| `backend/app/loaders/local_reader.py` | 如运行时直接读取构造出的 SVN DataSource，可复用现有 `_resolve_source_path`；否则新增更窄的 Excel 读取 helper。 |
| `backend/app/ai/providers.py` / `provider_client.py` | 保持底层调用不变，新增项目级调用入口时复用。 |

### 数据库模型建议

| 模型 | 关键字段 | 说明 |
|---|---|---|
| `RuleConfigDraftRecord` | `project_id`、`family`、`markdown_text`、`base_version_id`、`updated_by_user_id`、`updated_at` | 一个项目一个 config_lookup 草稿；用于并发冲突检测。 |
| `RuleConfigVersionRecord` | `project_id`、`family`、`version_no`、`markdown_text`、`parsed_json`、`status`、`published_by_user_id`、`published_at` | 发布历史与回滚来源。 |
| `ProjectChatBindingRecord` | `project_id`、`chat_id`、`chat_name`、`created_at` | `chat_id` 全局唯一，支持一个项目多个群。 |
| `ProjectQueryRootRecord` | `project_id`、`alias`、`root_url`、`display_name`、`enabled` | Markdown 使用 alias，管理员维护远端 SVN 根。 |
| `ProjectSvnCredentialRecord` | `project_id`、`host`、`username`、`password_cipher`、`updated_at` | 项目级 SVN 凭据，普通成员只见脱敏状态。 |
| `ProjectAiCredentialRecord` | `project_id`、`provider_preset`、`base_url`、`model`、`encrypted_api_key`、`extra_headers_json`、`threshold`、`candidate_limit` | 项目级 AI 名称匹配配置。 |

### 前端新增/修改模块

| 模块 | 类型 | 职责 |
|---|---|---|
| `frontend/src/views/RuleConfigView.vue` | 新增 | 成员可访问的规则配置工作区。 |
| `frontend/src/api/ruleConfig.ts` | 新增 | 规则配置、发布、历史、回滚、试查、凭据状态 API。 |
| `frontend/src/types/ruleConfig.ts` | 新增 | 规则配置页类型。 |
| `frontend/src/store/ruleConfig.ts` | 可选新增 | 页面状态、草稿、版本历史、试查结果。 |
| `frontend/src/components/rule-config/MarkdownRuleEditor.vue` | 新增 | Markdown 编辑、结构校验结果展示。 |
| `frontend/src/components/rule-config/RulePublishPanel.vue` | 新增 | 校验、发布、发布状态。 |
| `frontend/src/components/rule-config/RuleVersionHistory.vue` | 新增 | 历史版本与回滚。 |
| `frontend/src/components/rule-config/ConfigLookupTrialPanel.vue` | 新增 | 查询类型、版本目录、查询内容试查。 |
| `frontend/src/components/rule-config/ProjectCredentialStatus.vue` | 新增 | SVN/AI 凭据脱敏状态。 |
| `frontend/src/App.vue` | 修改 | 新增“规则配置”导航，项目成员可见。 |
| `frontend/src/router/index.ts` | 修改 | 注册 `/rule-config`，只需 `auth: true`。 |
| `frontend/src/router/routePreload.ts` | 修改 | 增加规则配置页懒加载和预加载。 |
| `frontend/src/components/admin/FeishuBotConfigCard.vue` | 修改 | 扩展群绑定、query root、AI 阈值、候选数、管理员凭据配置入口。 |
| `frontend/src/api/admin.ts` / `frontend/src/types/admin.ts` | 修改 | 扩展飞书项目配置类型和 payload。 |

### 后端测试文件

| 测试文件 | 覆盖点 |
|---|---|
| `backend/tests/test_config_lookup_markdown.py` | 中文固定字段解析、非法字段拒绝、查询类型唯一、相对路径校验。 |
| `backend/tests/test_config_lookup_api.py` | 成员读写/发布/历史/回滚/试查权限；普通成员不可操作凭据。 |
| `backend/tests/test_config_lookup_runtime.py` | ID 精确查、ID miss 后名称匹配、多分页命中、引用字段输出、错误文案。 |
| `backend/tests/test_config_lookup_feishu_dispatch.py` | `礼包 查询 ...` 与 `礼包查询 ...` 命令解析、权限白名单、未发布/查询类型不存在。 |
| `backend/tests/test_admin_feishu_bot.py` | 扩展共享 App ID、Secret 一致性、群绑定唯一性、默认群属于绑定群。 |
| `backend/tests/test_feishu_long_conn.py` | `app_id` 级 supervisor、`chat_id` 路由、未绑定群不回复。 |
| `backend/tests/test_svn_cache.py` | 配置表查询强制刷新、项目级凭据注入、路径逃逸拒绝。 |
| `backend/tests/test_ai_provider_client.py` 或新增 `test_project_ai_credentials.py` | 项目级 AI 凭据脱敏、连接测试、候选阈值逻辑。 |

### 前端测试文件

| 测试文件 | 覆盖点 |
|---|---|
| `frontend/tests/unit/ruleConfigApi.test.ts` | API 路径、请求体、回滚/发布/试查调用。 |
| `frontend/tests/unit/RuleConfigView.test.ts` | 成员可进入、草稿加载、校验错误展示、发布按钮状态。 |
| `frontend/tests/unit/ConfigLookupTrialPanel.test.ts` | 试查表单、成功结果、多候选/低置信展示。 |
| `frontend/tests/unit/ProjectCredentialStatus.test.ts` | 普通成员只见脱敏状态，管理员显示配置入口。 |
| 扩展 `frontend/tests/unit/FeishuBotConfigCard.test.ts` | 绑定群输入、默认群校验提示、共享 App ID 错误展示。 |

## 7. 高风险改动标记

### 共享 App ID 长连接

- 当前 `FeishuLongConnSupervisor` 以 `project_id` 为运行时 key，并用 `_app_id_owner` 拒绝复用。
- 目标是 `app_id -> runtime`，同一个 App ID 只启动一条长连接。
- 事件 handler 不能再固定单个项目；必须从事件中的 `chat_id` 动态查询绑定项目。
- 当前数据库迁移里存在 `migrations/versions/0001_initial_schema.py:352` 的 `uq_feishu_bot_configs_app_id` 非空唯一索引，会阻止共享 App ID。按本次要求不新增迁移，实施时必须明确部署兼容策略，否则数据库层仍会拒绝重复 `app_id`。

### `chat_id` 路由

- 一个群只能绑定一个项目，需要数据库唯一约束或保存时事务内检测。
- 未绑定群发来的命令不回复，只记录日志，避免跨项目泄露配置存在性。
- `default_chat_id` 必须在绑定群列表中，测试发送默认群也应使用绑定校验结果。

### 凭据脱敏

- 普通成员可查看 SVN/AI 是否已配置、更新时间、用户名/模型等非敏感状态。
- 普通成员不可读取完整 SVN 密码、AI API Key，不可触发连接测试。
- 项目管理员可录入/更新/删除凭据和测试连接；后端必须以权限依赖兜底，不能只依赖前端隐藏。

### SVN 文件强制刷新

- 查询必须读取 SVN 最新配置文件，不能只依赖 TTL 缓存。
- 推荐复用 `prepare_remote_svn_source(..., force_refresh=True)`，但要支持项目级 SVN 凭据。
- 路径拼接必须拒绝 URL、盘符、绝对路径、`..`，最终 URL 必须落在管理员配置的 query root 下。
- 并发查询同一目录时要复用 `svn_cache` 现有 per-dir lock，避免重复 checkout/update。

### 飞书消息分段

- 业务语义返回全部命中结果，不做结果截断。
- 发送层按飞书消息长度拆分，复用或泛化 `_split_text_messages`。
- 分段需要保持单条结果尽量不被拆散；过长单行再做硬切。

### 命令冲突

- 现有 `@机器人 查询 ...` 是目录查询。
- 新需求是 `@机器人 <查询类型> 查询 <版本目录> <查询内容>` 和 `<查询类型>查询` 兼容格式。
- 解析顺序应先识别更具体的配置表查询，再保留旧目录查询；需要测试确保旧命令不被误判。

## 8. 建议实施顺序

1. 后端模型与 schema：新增配置表查询 domain 类型、项目级凭据类型、API 请求/响应类型。
2. Markdown 解析与发布校验：先完成 deterministic 解析和结构校验，不接 SVN。
3. 规则配置 API：草稿、发布、历史、回滚、权限与脱敏状态。
4. SVN Excel 查询 runtime：安全路径、强制刷新、Excel 读取、ID/名称匹配、结果格式化。
5. 飞书共享 App ID 改造：保存校验、chat 绑定、supervisor 按 App ID 管理、消息按 chat 路由。
6. 前端规则配置页：导航、编辑器、校验/发布、历史、试查、凭据状态。
7. 管理后台飞书配置扩展：群绑定、query root、项目级 SVN/AI 凭据配置。
8. 完整回归测试：后端 pytest、前端 lint/unit/build，必要时补 Playwright 冒烟。

## 9. 验证命令

```powershell
python -m ruff check backend
python -m pytest backend/tests -q
cd frontend
npm run lint
npm run test:unit
npm run build
```

