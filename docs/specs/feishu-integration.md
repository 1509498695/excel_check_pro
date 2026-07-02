# 飞书集成 Spec

## 0. Codex 快速入口

- 先读文件：`backend/app/admin/router.py` 的飞书机器人接口、`backend/app/api/feishu_api.py`、`backend/app/integrations/feishu_client.py`、`backend/app/integrations/feishu_bot.py`、`backend/app/integrations/feishu_long_conn.py`、`backend/app/loaders/feishu_reader.py`、`frontend/src/components/admin/FeishuBotConfigCard.vue`。
- 最常改文件：`frontend/src/api/admin.ts`、`frontend/src/features/admin/feishuBotConfigForm.ts`、`backend/app/services/feishu_sheet_authorization_service.py`。
- 不要改契约：飞书在配置表查询中是通道和项目路由；查询业务语义写在 `rule-configs-config-lookup.md`。
- 新增功能入口：机器人配置从 `/api/v1/admin/projects/{project_id}/feishu-bot*` 接入；数据源授权从 `/api/v1/feishu/sources/*` 接入。
- 必跑测试：`python -m pytest backend/tests/test_admin_feishu_bot.py backend/tests/test_feishu_permission_api.py backend/tests/test_feishu_reader.py backend/tests/test_feishu_client.py backend/tests/test_feishu_bot_client.py backend/tests/test_feishu_long_conn.py -q`；前端跑 `adminFeishuBotApi.test.ts`、`feishuBotConfigForm.test.ts`。
- 常见误区：不要把飞书 app 配置做成全局单例；项目配置、chat 绑定、下载根和查询根都按项目隔离。

## 1. 模块目标

飞书集成提供项目机器人配置、电子表格授权、表格读取、消息发送和事件通道能力。它是多个业务能力的通道，不承载配置表查询本身的规则语义。

## 2. 用户入口与适用场景

| 入口 | 说明 |
|---|---|
| `/admin` 飞书机器人配置卡片 | 项目管理员维护 App ID、App Secret、默认群、chat 绑定、触发用户、SVN 凭据和查询根。 |
| 个人校验数据源面板 | 检测飞书表格权限并发送授权卡片。 |
| V1 Feishu OAuth callback | 完成飞书电子表格单 Sheet 只读协作者授权。 |

## 3. 核心概念

- 项目级飞书机器人配置：每个项目独立维护。
- Shared Feishu Bot App：多个项目可共用同一 App ID，但同 App ID 的 App Secret 必须一致。
- Project Feishu Service Identity：服务端项目自动化读取飞书来源时使用项目级 App/Bot 身份，不使用当前登录用户的个人 OAuth token 作为长期读取身份。
- Chat-Scoped Project Routing：机器人事件按 chat 绑定路由到项目。
- Default Bot Chat：默认主动通知群，必须属于项目 chat 绑定。
- Feishu Sheet Authorization：项目和 source 维度的表格授权记录。

## 4. 前端边界

- 管理后台飞书配置组件：`frontend/src/components/admin/FeishuBotConfigCard.vue`。
- 表单逻辑：`frontend/src/features/admin/feishuBotConfigForm.ts`。
- 管理 API：`frontend/src/api/admin.ts`。
- 个人校验数据源授权入口：`DataSourcePanel.vue` 和 `frontend/src/api/workbench.ts`。
- Source Evidence 授权申请必须接入 `/test-cases` 主流程的 Source Evidence 状态区：当 run/resource 为 `pending_permission`，或资源下载状态为 `download_failed` 时显示“申请授权”按钮，调用 `POST /api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request`，并展示发送目标摘要和“等待作者授权，授权后请点击重试读取”。不为本刀新增单独授权管理页；项目管理员授权审计列表可先只提供 API。
- Source Evidence 授权申请前端状态映射固定：`authorization_sent`/`already_sent` 展示“等待作者授权”，禁用重复申请并保留“重试读取”；`already_authorized`/`already_readable` 提示可直接重试读取，不再显示申请按钮；`send_failed`/`bot_not_configured` 展示脱敏错误摘要并允许再次点击申请；`expired_or_cleaned` 禁用申请和生成并提示重新读取来源；`invalid_run_state` 展示当前状态不可申请，不自动改变 run。
- Source Evidence 页面不自动轮询授权状态；授权卡发送后只展示等待提示，用户点击“重试读取”或再次显式申请授权时，后端才重新检查授权记录和读取能力。

## 5. 后端边界

- 项目飞书机器人配置：`backend/app/admin/router.py`。
- 飞书数据源授权：`backend/app/api/feishu_api.py`。
- 飞书 HTTP 客户端、机器人和长连接：`backend/app/integrations/feishu_*`。
- 飞书电子表格读取：`backend/app/loaders/feishu_reader.py`。
- 授权记录：`backend/app/services/feishu_sheet_authorization_service.py`。
- Source Evidence 专用授权能力新增 `backend/app/test_cases/source_evidence_authorization.py` 承载 service、状态机、发送策略和 callback 校验；API 先挂在现有 `backend/app/api/test_cases_api.py`，如果文件继续变重再拆独立 router。
- Source Evidence 授权一刀新增/扩展测试边界为 `backend/tests/test_source_evidence_authorization.py` 和 `backend/tests/test_alembic_migrations.py`；不要复用 V1 `FeishuSheetAuthorizationRecord` 测试作为唯一覆盖。

## 6. 数据与持久化边界

- `app_secret` 加密落库。
- 表格授权记录按 `project_id + source_id` 记录，并可按 spreadsheet token 复用。
- Chat 绑定按项目隔离；同一 chat 不能绑定多个项目。

## 7. API 契约

| API | 说明 |
|---|---|
| `GET /api/v1/admin/projects/{project_id}/feishu-bot` | 获取项目飞书机器人配置。 |
| `PUT /api/v1/admin/projects/{project_id}/feishu-bot` | 保存项目飞书机器人配置。 |
| `DELETE /api/v1/admin/projects/{project_id}/feishu-bot` | 删除项目飞书机器人配置。 |
| `POST /api/v1/admin/projects/{project_id}/feishu-bot/test-send` | 测试发送消息。 |
| `POST /api/v1/feishu/sources/check-permission` | 检查表格读取权限。 |
| `POST /api/v1/feishu/sources/send-authorization-card` | 发送授权卡片。 |
| `GET /api/v1/feishu/sources/oauth/callback` | OAuth 回调并追加协作者。 |
| `POST /api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request` | 对当前 Source Evidence Run 显式发送整篇源文档协作者授权申请。 |
| `GET /api/v1/test-cases/source-evidence-authorizations?limit=50&offset=0` | 项目管理员/超级管理员查看 Source Evidence 授权最小审计列表。 |
| `POST /api/v1/test-cases/source-evidence-authorizations/{authorization_id}/invalidate` | 项目管理员/超级管理员手动失效 Source Evidence 授权复用记录。 |
| `GET /api/v1/test-cases/source-evidence-authorizations/oauth/callback` | Source Evidence 专用 OAuth 回调，把项目 App/Bot 加为整篇源文档 `edit` 协作者。 |

## 8. 关键流程

1. 项目管理员保存飞书机器人配置。
2. 用户添加飞书数据源时，后端检查表格权限。
3. 权限不足时，项目机器人向默认群发送授权卡片。
4. 有权限的飞书用户点击卡片完成 OAuth。
5. 后端把机器人加入表格只读协作者并记录授权。
6. 后续 metadata、preview 和执行复用飞书读取链路。

### 8.1 Source Evidence Run 授权主体

用例生成 V2 若扩展到飞书文档、图片、附件和 `Source Evidence Run`，读取主体仍以 `Project Feishu Service Identity` 为准：

- 当前登录用户只触发读取、授权申请或重试，不作为长期来源读取身份。
- 不把 QA Workspace 的本机个人 user token 模式直接迁移到当前 Web 项目。
- 权限不足时，记录资源的待授权状态，并沿用项目级机器人/授权卡片方向申请给 App/Bot 可读取权限。
- Source Evidence 文档、图片和附件链路默认为项目 App/Bot 申请 `edit` 权限；授权卡文案必须说明该权限仅用于读取正文、表格、下载图片/附件和生成短期证据，不修改源文档、表格或评论。
- 授权成功时把项目 App/Bot 加为整篇源文档协作者，不做图片、附件或单个资源粒度授权；后续 retry 应基于该协作者权限补读正文、表格、图片和附件。
- Source Evidence 授权采用一次性 OAuth 回调闭环：点击授权卡的人必须具备源文档分享/授权能力；后端仅在本次回调内使用 `user_access_token` 把项目 App/Bot 加为整篇源文档 `edit` 协作者，不保存个人 token。
- Source Evidence OAuth `state` 只能是一段一次性随机值，不得携带源文档 URL、doc token、wiki token、file token 或 source token；数据库仅保存 `state_hash`、过期时间、专用授权记录 id 和 originating run id。callback 通过 `state_hash` 回查授权记录和未过期 run，再从 run 的短期敏感字段解析真实对象 token 完成协作者添加。
- Source Evidence OAuth callback 到达时，如果 originating run 已过期或已清理，不得继续添加协作者；callback 应失败并提示“证据已过期，请重新读取来源并重新申请授权”。授权记录可标记为 `expired` 或 `authorization_failed`，但不得绕过 Source Evidence 7 天敏感材料清理边界恢复或保留源文档 token。
- Source Evidence OAuth callback 不要求点击授权卡的人是当前系统项目成员；callback 只校验一次性 `state`、OAuth code、专用授权记录、originating run 未过期，以及点击人在飞书侧确实能把项目 App/Bot 加为协作者。`authorization-request` 发起接口仍必须要求当前系统项目成员权限。
- Source Evidence OAuth callback 成功后，授权审计只记录点击人的飞书 `open_id`、可选脱敏展示名/邮箱摘要、`authorized_at`、`verification_status` 和 `last_error_summary`；不得保存完整 `user_access_token`、OAuth code、手机号、邮箱全文或其他个人敏感信息。
- Source Evidence 授权记录列表仅项目管理员/超级管理员可查看；普通项目成员不能查看项目级授权列表，只能在当前 run 页面看到与本 run 相关的授权状态提示。列表仅返回 `doc_type`、`permission`、状态、脱敏 source 指纹、发送目标摘要、授权人 `open_id`/脱敏名、创建/发送/授权/过期/失效时间和最后错误摘要，不返回 source URL、doc token、wiki token、file token、OAuth code、`user_access_token` 或 App Secret。
- Source Evidence 必须使用专用 OAuth callback：`GET /api/v1/test-cases/source-evidence-authorizations/oauth/callback`，不复用 V1 飞书电子表格 `/api/v1/feishu/sources/oauth/callback`；回调状态、成功/失败页文案和授权记录都按 Source Evidence 整篇源文档协作者语义处理。
- Source Evidence 授权申请由当前 run 显式触发：`POST /api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request`；服务端仍按 `project_id + app_id + resolved obj_token hash + permission=edit` 查找或更新复用授权记录，不把授权状态绑定到单个 run。
- `authorization-request` 响应字段固定为最小安全摘要：`status`、`message`、`authorization_id`、`target_mode`、`sent_targets_count`、`failed_targets_count`、`fallback_to_default_chat`、`owner_candidates_truncated`、`expires_at`、`can_retry_read`；不得返回 open_id 明细、完整飞书 URL、doc/wiki/file/source token 或完整错误堆栈。
- `authorization-request.status` 枚举固定为 `authorization_sent`、`already_sent`、`already_authorized`、`already_readable`、`send_failed`、`bot_not_configured`、`invalid_run_state`、`expired_or_cleaned`。
- `authorization-request.target_mode` 枚举固定为 `owner_direct`、`creator_direct`、`default_chat`、`not_sent`；多个 owner 成功时仍返回 `owner_direct`，发送数量由 `sent_targets_count` 表达，全部直发失败后降级到默认群时返回 `default_chat`。
- `authorization-request` HTTP 状态码约定：未登录、非项目成员和跨项目仍使用标准 `401`/`403`/`404`；`expired_or_cleaned` 返回 `409`；其他业务结果返回 `200` 并通过 `status` 区分，包括 `already_sent`、`already_authorized`、`already_readable`、`bot_not_configured`、`send_failed` 和 `invalid_run_state`。
- `authorization-request` 作为 Source Evidence POST 接口，必须继续拒绝公共知识字段：`knowledge_context`、`qa_knowledge_context`、`project_qa_knowledge`。
- Source Evidence Run 创建或首次读取遇到权限不足时，不自动发送授权卡；run/resource 只标记 `pending_permission`，返回可展示的 owner / creator 或默认群降级提示，并由页面用户点击“申请授权”后才调用 `authorization-request`。
- Source Evidence 显式授权申请需要防重复：已有未过期 `authorization_sent` 时不重复发卡，返回“已发送，等待授权”；已有有效 `authorized` 且当前 run/resource 没有权限失败时不发卡，返回 `already_authorized` 并提示重试读取；当前 run/resource 为 `pending_permission`/`download_failed`，或授权记录为 `failed`/`authorization_failed`/`expired`/`invalidated` 时，允许用户显式重新发送。
- Source Evidence `authorization-request` 不允许对 `ready` 且无资源权限失败的 run 发送授权卡；此类请求返回 `already_readable` 或 `already_authorized`，避免无意义地骚扰 owner / creator。
- Source Evidence OAuth callback 授权成功后不自动触发当前 run retry；成功页只提示“授权已完成，请回到页面点击重试读取”，由页面用户显式执行 retry。
- Source Evidence OAuth callback 页面文案固定：成功页显示“授权已完成，请回到用例生成页面点击重试读取。”；originating run 过期或已清理时显示“证据已过期，请重新读取来源并重新申请授权。”；点击人缺少飞书分享权限时显示“授权失败：当前飞书账号可能没有分享该文档的权限，请联系文档 owner。”；系统错误页只展示脱敏错误摘要，不展示 OAuth code、URL、token、Authorization 或堆栈。
- Source Evidence OAuth callback 添加整篇源文档协作者成功后，必须再使用项目 App/Bot tenant token 做一次轻量读取校验；只有校验通过才把专用授权记录标记为 `authorized`。如果添加协作者成功但 App/Bot 仍不可读，则记录 `pending_verification` 或 `authorization_failed`，并继续让 run/resource 保持 `pending_permission`，避免页面误判权限已生效。
- Source Evidence 授权卡优先通过 Drive metadata 查询文档 owner / creator 并直接发送；如果 metadata 不可用、owner / creator 不可达或卡片发送失败，则降级发送到项目默认群，并明确提示“无法定位作者，请有权限的人点击授权”。
- Drive metadata 返回多个候选人时，Source Evidence 授权卡按 owner 优先、creator 兜底发送：如果存在 owner，最多发送给前 3 个 owner，超出时在审计中记录 `owner_candidates_truncated=true`；如果 owner 不可达再尝试 creator；owner 和 creator 都不可达时再降级到项目默认群，避免一次性骚扰过多人。
- 多个 owner / creator 候选发送时，只要至少一个直发目标发送成功，`authorization-request` 即返回 `authorization_sent`，并在响应和审计中记录 `sent_targets_count`、`failed_targets_count` 和脱敏失败摘要；只有全部直发目标失败时才降级发送到项目默认群。
- Source Evidence 授权卡不得展示完整飞书 URL、doc token、wiki token、file token 或 source token；卡片只展示项目名、来源类型、文档标题、申请人、安全用途说明和“仅用于读取正文、表格、下载图片/附件和生成证据，不修改源文档”。metadata 无法取得标题时，使用来源类型和脱敏 source 指纹辅助定位。
- V1 飞书电子表格单 Sheet 链路继续只申请 `view` 权限，避免扩大既有个人校验和单 Sheet 快照的授权范围。
- Source Evidence 授权成功后按 `project_id + app_id + resolved obj_token hash + permission=edit` 复用授权状态，不绑定单个 `Source Evidence Run`；新的 run 可复用读取权限，但不能复用已过期或已清理的证据内容。
- Source Evidence 授权复用必须新增专用表/模型，不复用 `FeishuSheetAuthorizationRecord`；现有表只服务 V1 飞书电子表格单 Sheet 的 `view` 授权，Source Evidence 专用模型负责 docx/wiki/sheets/bitable 的整篇源文档 `edit` 授权。
- Source Evidence 专用授权表/模型需要独立 Alembic migration 和后端实现切片；该切片只包含模型、迁移、service、API/callback 和权限/安全测试，不和飞书富 reader 读取逻辑混在同一刀。
- Source Evidence 专用授权表名为 `source_evidence_authorizations`；唯一键为 `project_id + app_id + source_token_hash + permission`，其中 `source_token_hash` 保存 wiki resolve 后真实 `obj_token` 的 sha256。
- Source Evidence 专用授权记录必备字段：`project_id`、`app_id`、`doc_type`、`permission`、`source_token_hash`、`source_token_alias_hashes_json`、`status`、`state_hash`、`state_expires_at`、`originating_run_id`、`target_mode`、`sent_targets_count`、`failed_targets_count`、`owner_candidates_truncated`、`authorized_by_open_id`、`authorized_by_display_name_masked`、`authorized_at`、`expires_at`、`invalidated_at`、`invalidated_by`、`last_error_summary`、`created_at`、`updated_at`。
- Source Evidence 专用授权表索引：唯一索引 `project_id, app_id, source_token_hash, permission`；列表/过期查询索引 `project_id, status, expires_at`；callback 查询使用唯一 `state_hash`；run 页面回查索引 `project_id, originating_run_id`。
- `originating_run_id` 只作为审计值保存，不对 `SourceEvidenceRun` 建外键；授权复用生命周期默认 90 天，不能被 run 的 7 天 TTL、清理或删除耦合。
- `source_token_alias_hashes_json` 不建索引；service 只在 wiki resolve 后用真实对象 `obj_token` 写主 `source_token_hash`，alias 仅用于审计和排查。
- `source_token_hash` 在数据库中保存完整 sha256 hex 以支持唯一键；对外展示和审计摘要只使用 `sha256:<16hex>` 指纹。`source_token_alias_hashes_json` 只保存 alias 的完整 sha256 hex 和展示指纹，不保存明文 alias。
- `state_hash` 保存 OAuth 一次性随机 state 的完整 sha256 hex；OAuth URL 只携带随机 state 明文，不携带任何 source URL、doc token、wiki token、file token 或 source token。
- `last_error_summary` 和所有授权响应错误信息必须复用现有 Feishu 脱敏规则，覆盖 `app_secret`、`tenant_access_token`、`user_access_token`、OAuth code、`Authorization` header 和 Bearer token。
- Source Evidence 专用授权记录的唯一复用键应基于 `project_id`、`app_id`、resolved `obj_token` 的 `source_token_hash` 和 `permission`；模型仅保存 token hash、wiki alias hash、doc_type、permission、状态、发送目标、授权人最小审计、创建/授权/失效/过期时间和最小错误摘要，不长期保存完整 source URL、doc token、wiki token、file token、OAuth code 或个人 access token。
- Source Evidence 专用授权记录状态至少包括：`authorization_sent`、`authorized`、`pending_verification`、`authorization_failed`、`expired`、`invalidated`。`pending_verification` 只用于授权记录，表示添加协作者 API 成功但项目 App/Bot 读取校验未通过；run/resource 不新增对应状态，仍保持 `pending_permission`。
- Source Evidence 授权复用记录需要独立过期时间，默认 90 天，可由项目管理员手动失效；该过期时间不跟 `Source Evidence Run` 默认 7 天 TTL 绑定。
- 项目管理员/超级管理员可通过 `POST /api/v1/test-cases/source-evidence-authorizations/{authorization_id}/invalidate` 手动把 Source Evidence 授权记录标记为 `invalidated`；该操作只停止本系统复用该授权，不自动从飞书源文档移除项目 App/Bot 协作者。
- Source Evidence 授权记录 90 天到期或被管理员手动失效时，只表示本系统不再复用该授权记录，不自动把项目 App/Bot 从飞书源文档协作者中移除；飞书侧撤权需要后续单独设计可审计流程，避免误删其他项目或人工授予的协作关系。
- `source_token` 使用解析后的真实对象 token；wiki 链接先 resolve 到 `obj_token` 后再参与授权复用，原始 wiki token 仅作为 alias/audit hash 保留，不作为主授权 hash。
- Source Evidence 授权复用记录不得长期保存完整 source URL、doc token、wiki token 或 file token；只保存 `source_token_hash`、`source_token_alias_hashes`、`doc_type`、`permission`、`app_id`、状态、授权人 open_id 和时间等最小审计字段。
- 如果已有可复用 `edit` 授权但本次读取或资源下载仍失败，不自动重复发送授权卡；run/resource 进入 `pending_permission` 或 `download_failed`，页面提供用户显式触发的“重新申请授权”入口。
- OAuth 回调中添加协作者失败时，记录 `authorization_failed` 并保留 run/resource 的 `pending_permission` 状态；不得自动再次发送授权卡。
- 授权成功后，未过期的 `Source Evidence Run` 可以重试读取资源和视觉 observation。
- Source Evidence 授权一刀明确不做：不自动从飞书源文档移除项目 App/Bot 协作者；不自动轮询授权状态；不新增前端管理员授权列表页；不把授权记录纳入 `Source Evidence Run` 7 天 TTL 清理；不保存完整 source URL、doc token、wiki token、file token、OAuth code、`user_access_token` 或 App Secret。

## 9. 权限、安全与错误规则

- 普通项目成员可查看必要状态，但敏感配置由项目管理员维护。
- App Secret、tenant token、access token 不得明文暴露。
- 权限不足时返回业务错误或授权状态，不触发前端登录态过期。
- 飞书来源读取不得把当前登录用户的个人 OAuth token 作为服务端长期读取凭据。
- 查询命令的业务解析归配置表查询模块；飞书模块只负责事件、路由和消息。

## 10. 测试覆盖

- 后端：`test_admin_feishu_bot.py`、`test_feishu_permission_api.py`、`test_feishu_reader.py`、`test_feishu_client.py`、`test_feishu_bot_client.py`、`test_feishu_long_conn.py`、`test_feishu_download.py`、`test_feishu_datasource_e2e.py`。
- Source Evidence 授权专项测试最低覆盖：专用授权表 migration 索引/唯一键；`authorization-request` 拒绝 `knowledge_context`、`qa_knowledge_context`、`project_qa_knowledge`；跨项目 run 返回 `404`；普通成员不能查看授权审计列表或手动失效授权；OAuth callback 不要求点击人是系统项目成员；originating run 过期或 cleaned 时 callback 失败；OAuth `state` 不包含 URL/token；已有未过期 `authorization_sent` 不重复发卡；`ready` 且无权限失败的 run 不发授权卡。
- Source Evidence 授权一刀后端最小命令：`python -m pytest backend/tests/test_source_evidence_authorization.py backend/tests/test_alembic_migrations.py backend/tests/test_source_evidence_permissions.py`。
- Source Evidence 授权按钮前端最小命令：`cd frontend && npm run test:unit -- testCasesApi TestCaseGeneratorView && npm run build`。
- 文档-only 决策阶段不跑测试；实现阶段完成后必须执行对应后端/前端最小命令。
- 前端：`adminFeishuBotApi.test.ts`、`feishuBotConfigForm.test.ts`、`FeishuBotConfigCardSvnTest.test.ts`。

## 11. 已知限制

- 仅支持飞书电子表格和 wiki 电子表格。
- 不支持多维表格、文档表格或任意 Drive 文件。
- 飞书主链路依赖真实项目机器人、OAuth callback 和应用权限。

## 12. 维护检查清单

- 改机器人配置时，检查 shared App ID 和 App Secret 一致性。
- 改 chat 绑定时，检查一群一项目规则。
- 改飞书读取时，跑权限 API、reader 和 datasource e2e 测试。
- 配置表查询相关改动，应优先更新 `rule-configs-config-lookup.md`。
