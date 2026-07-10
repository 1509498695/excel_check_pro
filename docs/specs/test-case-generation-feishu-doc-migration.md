# 用例生成飞书文档读取移植方案

## 0. Codex 快速入口

- 当前前置状态：用例生成 V1 主链路已开发完成，已有策划案快照、AI 整理稿、无参考/参考增强生成、Excel 导出和 `/test-cases` 前端页面；本方案是在 V1 之后移植 `qa-case` 的飞书文档读取能力。
- 先读当前项目文件：`docs/specs/test-case-generation.md`、`docs/specs/feishu-integration.md`、`docs/specs/ai-project-credentials.md`、`CONTEXT.md`。
- 先读当前实现文件：`backend/app/test_cases/planning_snapshot.py`、`backend/app/test_cases/generation.py`、`backend/app/test_cases/snapshot_brief.py`、`backend/app/api/test_cases_api.py`、`frontend/src/views/TestCaseGeneratorView.vue`。
- 当前飞书底座：`backend/app/loaders/feishu_reader.py`、`backend/app/integrations/feishu_client.py`、`backend/app/api/feishu_api.py`。
- QA Workspace 参考来源：`D:\project\QAWORK\qa_workspace\skills\workspace\context-reading\SKILL.md`、`core/context_readers/feishu/rich_reader.py`、`docx_blocks.py`、`openapi.py`、`router.py`、`visual.py`、`source_guard.py`。
- 不要直接移植：`uv run qa ...` CLI、`tasks/<task>/sources/` 本地目录、个人 user token cache、QA Workspace preflight/setup/role、知识库维护流。
- 迁移主线：复用 `qa-case` 的读取规则、证据模型、视觉证据边界和降级策略；实现形态必须适配当前项目的项目权限、项目级服务身份、数据库、API 和页面态。

## 1. 文档状态

| 项 | 内容 |
|---|---|
| 版本 | V1 完成后的增量方案 |
| 状态 | 需求方案已收敛，待实现 |
| 目标能力 | 把 `qa-case`/QA Workspace 的飞书文档富读取能力移植到当前项目的用例生成工作台 |
| 主要边界 | 不保存生成历史；允许短期保存来源证据；默认 7 天 TTL 自动清理；视觉证据需用户采纳后才进入生成依据 |
| 主要使用者 | 项目成员、项目管理员、超级管理员 |

## 2. 背景与目标

当前 V1 已经可以从上传 Excel 或飞书电子表格单个 Sheet 读取 `Planning Sheet Snapshot`，再按内置 `QA Case Method` 生成用例。问题是很多策划案实际是飞书文档、Wiki 文档、文档内多 Sheet、图片、附件和原型截图混合材料，现有“单 Sheet 二维表”不足以支撑完整用例生成。

本方案目标是移植 `qa-case` 的飞书文档读取能力，让用例生成可以读取飞书文档的正文、表格、页签和资源清单，并在视觉模型可用时支持图片/附件 observation 和人工采纳。

迁移后仍必须保持 V1 的安全边界：

- 不保存生成历史。
- 不把来源证据当成永久知识库。
- 不把图片 observation 自动当成需求事实。
- 不写回既有飞书文档或表格。
- 不强依赖参考案例库；参考案例仍只是格式、粒度和历史风格增强。

## 3. 核心结论

- V1 已完成的上传 Excel、飞书电子表格单 Sheet 快照链路保持不变。
- 新增 `Source Evidence Run` 作为飞书文档富读取的短期证据会话，不属于生成历史，也不属于项目级 QA 知识库。
- `Source Evidence Run` 默认按项目隔离，TTL 为 7 天。
- TTL 到期后删除原文快照、图片/附件文件、视觉包和 observation 详情，只保留最小审计元数据。
- 最小审计元数据不随 7 天 TTL 删除，按项目审计数据保留策略保留。
- 飞书读取主体采用项目级 `Project Feishu Service Identity`，不复用或长期保存当前登录用户个人 OAuth token。
- 视觉理解使用独立 `Project Vision AI Credential`，不复用文本生成的 `Project AI Credential`。
- Vision AI 缺失或不可用时允许继续，但降级为“文本/表格 + 资源清单 + 待观察图片/附件”。
- 图片/附件先形成资源清单，再做系统推荐和用户可调整的 `Visual Observation Selection`，不默认全量观察。
- observation 完成后必须经用户确认采纳，形成 `Adopted Visual Evidence` 后才能进入生成上下文、蓝图、用例备注和导出。
- TTL 内页面和导出可引用 `Adopted Visual Evidence`；TTL 后不再提供证据复查，用户需要重新读取来源。

## 4. 范围

### 4.1 本期必须支持

- 在“用例生成”页面新增飞书文档类来源读取能力。
- 支持飞书 `docx`、`wiki` 指向的 `docx`、飞书电子表格富读取、飞书多维表格只读读取的架构预留。
- 对飞书文档整篇读取，而不是只读取 URL 中某一个局部片段。
- 对飞书电子表格富读取时默认列出所有 Sheet，并按 `qa-case` 规则分类和纳入范围。
- 读取正文、表格、可见页签、资源清单和资源位置。
- DOCX 不只依赖 `raw_content`，必须读取 blocks，提取图片、附件、文件块、inline file、表格单元格子块等资源候选。
- 输出受控的文本/表格快照给现有生成链路使用。
- 输出资源清单，标记待观察图片/附件。
- 支持项目级 Vision AI 配置状态和不可用降级。
- 支持用户选择需要观察的资源，并对观察结果进行确认采纳。
- 生成用例时只使用文本/表格快照和已采纳视觉证据。
- warnings 明确展示未读图、未观察、未采纳、权限不足、TTL 过期和证据已清理。

### 4.2 明确不支持

- 不迁移 QA Workspace CLI。
- 不创建本地 `tasks/<task>` 目录。
- 不保存生成结果、蓝图、用例表或 prompt。
- 不提供生成历史、重复生成比对或历史回放。
- 不建设可维护 QA 知识库。
- 不把 observation 自动沉淀为知识。
- 不写回既有飞书文档、飞书表格或评论。
- 不自动观察全部图片/附件。
- 不长期保存个人 OAuth token。
- 不把参考案例库升级为需求来源。

## 5. 术语边界

| 概念 | 本方案定义 |
|---|---|
| Source Evidence Run | 一次短期的项目级来源读取会话，保存飞书正文、表格、资源清单、视觉包和 observation，用于本次或短期复查，不是生成历史 |
| Source Evidence Snapshot | 从 Source Evidence Run 提炼出的受控文本/表格输入，可适配当前 `PlanningSnapshotResponse` |
| Source Resource Inventory | 飞书文档中的图片、附件、文件块、表格内资源和未支持资源候选清单 |
| Visual Observation Selection | 用户可调整的待观察资源集合，由系统推荐但不默认全量观察 |
| Visual Observation | Vision AI 或人工看图后形成的结构化观察结果，未采纳前不能进入生成依据 |
| Adopted Visual Evidence | 用户确认采纳的视觉 observation，允许进入生成上下文和导出说明 |
| Project Feishu Service Identity | 项目级飞书应用/机器人身份，用于服务端读取和权限申请 |
| Project Vision AI Credential | 项目级视觉模型凭据，独立于文本生成用的项目级 AI 凭据 |

## 6. 飞书读取规则

### 6.1 文档整体读取

从 `qa-case` 移植以下读取原则：

- 用户提供飞书文档链接时，默认按整篇文档处理。
- Feishu 多页签文档需要先列出所有页签并分类：策划正文、规则、美术需求、文本需求、打点需求、配置说明、过程产物、反馈记录。
- 隐藏页签默认不分析、不纳入蓝图和用例拆分；若 OpenAPI 返回 hidden/visible 状态，必须记录排除原因。
- 明确标记 `CP` 的过程产物页签、标题含“反馈”的内部玩测反馈页签默认不作为需求事实生成用例。
- `反馈`、`战场反馈` 等反馈类页签只能作为排查背景或人工参考；用户明确要求按反馈补回归用例时，备注必须标明“反馈来源，待确认是否需求”。
- 除隐藏页签、过程产物、反馈页签和用户明确排除页签外，其他策划相关页签默认纳入快照和用例拆分。

### 6.2 DOCX block 读取

DOCX 读取不能只用 `raw_content`。必须移植 QA Workspace 中 `docx_blocks.py` 的核心思路：

- 调用 `raw_content` 作为文本兜底。
- 调用 `/docx/v1/documents/{token}/blocks` 分页读取所有 blocks。
- 按 block 顺序渲染 Markdown。
- 提取图片块、文件块、inline file、inline block、表格单元格子块、白板/嵌入对象候选。
- 为可支持资源生成稳定 ref，例如 `docx_img_001`、`docx_att_001`。
- 在文本中保留 `<image ref="..." position="..." />` 和 `<attachment ref="..." position="..." />` marker。
- 不把 `raw_content` 中出现的 `image.png` 文件名当作真实图片证据。
- 对未知资源候选保留结构化记录，但不得渲染成 `<image>`，避免暗示已获得视觉证据。

### 6.3 表格富读取

飞书电子表格单 Sheet 快照仍保留 V1 现有路径。新增富读取路径用于飞书文档整体证据：

- 读取可见 Sheet 列表和二维值。
- 保留 Sheet 标题、行列坐标、稀疏单元格、资源位置。
- 避免把大稀疏表格强行补成巨大 Markdown。
- 对图片、附件和浮动图提取资源清单。
- 对隐藏 Sheet、空 Sheet 和排除 Sheet 写入 manifest/warnings。

### 6.4 Bitable 预留

V1 后续切片可以先不开放多维表格 UI，但读取层应预留：

- app/table/view/records 只读读取。
- 文件和图片字段进入资源清单。
- 表格记录转换为可追踪的文本/表格片段。

## 7. 权限方案

### 7.1 项目级读取身份

当前项目已有项目级飞书机器人配置、电子表格权限检测、授权卡片和 OAuth 回调。本方案在这个基础上扩展：

- 服务端读取主体是 `Project Feishu Service Identity`。
- 用户只是触发读取、授权申请或重试。
- 不把当前登录用户个人 OAuth token 作为长期读取身份保存。
- 权限状态按项目和来源隔离。
- Source Evidence 文档、图片和附件链路默认为项目 App/Bot 申请 `edit` 权限；授权卡文案必须明确“仅用于读取正文、表格、下载图片/附件和生成证据，不修改源文档”。
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
- Source Evidence 授权卡优先通过 Drive metadata 查询文档 owner / creator 并直接发送；如果 metadata 不可用或发送失败，则降级发送到项目默认群，并明确提示“无法定位作者，请有权限的人点击授权”。
- Drive metadata 返回多个候选人时，Source Evidence 授权卡按 owner 优先、creator 兜底发送：如果存在 owner，最多发送给前 3 个 owner，超出时在审计中记录 `owner_candidates_truncated=true`；如果 owner 不可达再尝试 creator；owner 和 creator 都不可达时再降级到项目默认群，避免一次性骚扰过多人。
- 多个 owner / creator 候选发送时，只要至少一个直发目标发送成功，`authorization-request` 即返回 `authorization_sent`，并在响应和审计中记录 `sent_targets_count`、`failed_targets_count` 和脱敏失败摘要；只有全部直发目标失败时才降级发送到项目默认群。
- Source Evidence 授权卡不得展示完整飞书 URL、doc token、wiki token、file token 或 source token；卡片只展示项目名、来源类型、文档标题、申请人、安全用途说明和“仅用于读取正文、表格、下载图片/附件和生成证据，不修改源文档”。metadata 无法取得标题时，使用来源类型和脱敏 source 指纹辅助定位。
- 旧 V1 飞书电子表格单 Sheet 快照仍保持 `view` 权限，不随 Source Evidence 扩大授权范围。
- Source Evidence 授权成功后按 `project_id + app_id + resolved obj_token hash + permission=edit` 复用授权状态，不绑定单个 run；复用的只是读取权限，证据文件、视觉包、observation 和 TTL 清理仍按每个 run 隔离。
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
- Source Evidence 授权复用记录需要独立过期时间，默认 90 天，可由项目管理员手动失效；该过期时间不跟 Source Evidence Run 默认 7 天 TTL 绑定。
- 项目管理员/超级管理员可通过 `POST /api/v1/test-cases/source-evidence-authorizations/{authorization_id}/invalidate` 手动把 Source Evidence 授权记录标记为 `invalidated`；该操作只停止本系统复用该授权，不自动从飞书源文档移除项目 App/Bot 协作者。
- Source Evidence 授权记录 90 天到期或被管理员手动失效时，只表示本系统不再复用该授权记录，不自动把项目 App/Bot 从飞书源文档协作者中移除；飞书侧撤权需要后续单独设计可审计流程，避免误删其他项目或人工授予的协作关系。
- `source_token` 使用解析后的真实对象 token；wiki 链接先 resolve 到 `obj_token` 后再参与授权复用，原始 wiki token 仅作为 alias/audit hash 保留，不作为主授权 hash，避免同一文档通过 wiki/docx 两种 URL 重复授权。
- Source Evidence 授权复用记录不得长期保存完整 source URL、doc token、wiki token 或 file token；只保存 `source_token_hash`、`source_token_alias_hashes`、`doc_type`、`permission`、`app_id`、状态、授权人 open_id 和时间等最小审计字段。
- 如果已有可复用 `edit` 授权但本次读取或资源下载仍失败，不自动重复发送授权卡；run/resource 进入 `pending_permission` 或 `download_failed`，页面提供用户显式触发的“重新申请授权”入口，避免骚扰作者。
- OAuth 回调中添加协作者失败时，记录 `authorization_failed` 并保留 run/resource 的 `pending_permission` 状态；不得自动再次发送授权卡。

### 7.2 权限不足处理

权限不足时不静默失败：

- 文本/表格读取权限不足：返回 `pending_permission` 或明确错误，提示项目成员发起授权。
- 图片/附件下载权限不足：允许降级继续文本/表格读取，但资源标记为 `pending_permission` 或 `download_failed`。
- 需要协作者/编辑权限才能下载图片时，页面说明“仅用于读取和分析图片/附件，不修改源文档”。
- 权限申请记录绑定 Source Evidence Run 或来源标识，不绑定生成历史。

### 7.3 不复用 QA Workspace 个人 token

QA Workspace 的本地 `~/.qa_workspace/feishu_tokens.json` 只适合 CLI 用户，不适合当前 Web 项目。当前项目不得移植：

- 本机 user token cache。
- `qa auth feishu-status` 拉回 token 的本地流程。
- 依赖当前 Codex/QA 用户身份的长期读取。

## 8. 视觉证据方案

### 8.1 Vision AI 凭据

- 新增独立项目级 `Project Vision AI Credential`。
- 项目管理员/超级管理员可配置。
- 项目成员只能查看“已配置/未配置/不可用”等状态，不可查看密钥。
- 不复用 `Project AI Credential`，因为视觉模型的成本、输入形态、超时、模型能力和错误处理不同。

### 8.2 降级策略

Vision AI 缺失或不可用时：

- 飞书正文继续读取。
- 表格继续读取。
- 资源清单继续生成。
- 图片/附件标记为“待观察图片/附件”。
- 生成允许继续，但 prompt 和 warnings 必须说明图片/附件未参与语义理解。
- 不得把图片文件名、附近文字或模型未观察内容写成已确认需求依据。

### 8.3 观察选择

默认不全量观察所有图片/附件。流程为：

1. 读取来源后生成资源清单。
2. 系统按文档位置、文件类型、文件名、附近文本、重复度和预算推荐观察集合。
3. 页面展示推荐理由、预算提示和用户调整入口。
4. 用户确认观察集合后再调用 Vision AI。
5. 未选择或未观察资源继续保持“待观察”。

### 8.4 采纳规则

observation 结果不能自动进入生成依据：

- observation 完成后先展示观察摘要、关联资源、来源位置、置信度和限制。
- 用户确认采纳后形成 `Adopted Visual Evidence`。
- 只有 `Adopted Visual Evidence` 能进入生成上下文、蓝图、用例备注、导出说明和证据追踪。
- 已观察但未采纳的资源可以在 TTL 内复核，但不得影响本次生成。

## 9. 数据与保留策略

### 9.1 存储边界

新增短期证据存储目录，建议独立于现有上传目录和参考案例库目录：

```text
runtime/source-evidence/
  <project_id>/
    <run_id>/
      source.md
      source.meta.json
      manifest.json
      resources.json
      resource_cards.json
      tables.json
      table_cards.json
      raw/
      images/
      attachments/
      visual_evidence/
        images/
        visual_candidates.json
        observations/
```

该目录是短期敏感材料，不进入源码包，不进入生成历史，不被参考案例库复用。

### 9.2 数据模型建议

建议新增以下模型，字段名实现时可按现有 ORM 风格调整：

`source_evidence_runs`

- `id`
- `project_id`
- `source_type`
- `source_url`
- `source_token`
- `source_title`
- `status`: `reading` / `ready` / `pending_permission` / `vision_pending` / `failed` / `expired` / `cleaned`
- `storage_path`
- `expires_at`
- `created_by`
- `created_at`
- `updated_at`
- `cleaned_at`
- `cleaned_by`
- `minimal_audit_json`

`source_evidence_resources`

- `id`
- `run_id`
- `project_id`
- `ref`
- `resource_type`
- `position`
- `filename`
- `download_status`
- `adoption_status`: `unobserved` / `observed` / `adopted` / `rejected` / `expired`
- `created_at`
- `cleaned_at`
- TTL 后仅保留资源 ref、文件名、类型、状态、创建/清理时间等最小审计字段，不保留可复查路径、token、observation 详情或原始内容。

`project_vision_ai_credentials`

- 结构参考现有项目级 AI 凭据，但独立表或独立 credential kind。
- 密钥加密存储。
- 文本 AI 和 Vision AI 不互相兜底。

`source_evidence_cleanup_audits`

- 当前实现不单独建表，直接在 `source_evidence_runs.minimal_audit_json` 中保留清理摘要。
- 飞书 token 类来源标识只保留 `sha256:<16hex>` 脱敏指纹，不长期保存完整 doc token、file token 或 source URL。
- 清理摘要只允许包含 run id、project id、来源类型、来源标题、脱敏来源标识、清理前/后状态、操作人、创建/过期/清理时间、最小错误摘要、资源 ref/类型/文件名/状态和统计计数。
- 只记录 run id、项目、来源标识、资源文件名、状态、操作人、创建时间、清理时间。

### 9.3 TTL 清理

默认 7 天 TTL。

到期必须删除：

- `source.md`
- `raw/`
- `images/`
- `attachments/`
- `visual_evidence/`
- observation 详情
- adopted evidence 的可复查详情
- 任何原文、图片、附件、视觉包、prompt 或模型观察原文

到期保留：

- run id
- project id
- 来源标识
- 资源文件名
- 状态
- 操作人
- 创建时间
- 清理时间
- 最小错误/清理摘要

清理触发采用双保险：

- 后台定时清理批量过期 run。
- 页面/API 访问 run 时做懒清理，发现过期立即转为已清理状态。
- 清理成功后的权威状态为 `cleaned`；`expired` 只作为 TTL 已到但尚未完成清理前的瞬时判定。
- 懒清理后 `GET run` 可返回安全摘要；snapshot、generate、export、retry、保存视觉选择、observation 和采纳操作必须拒绝继续使用，并提示重新读取来源。

## 10. API 方案

接口路径建议挂在现有 `/api/v1/test-cases/*` 下。

### 10.1 Source Evidence

- `POST /api/v1/test-cases/source-evidence-runs`
  - 输入：飞书 URL、读取选项、是否允许视觉候选。
  - 输出：run id、状态、TTL、来源摘要。
- `GET /api/v1/test-cases/source-evidence-runs/{run_id}`
  - 输出：状态、source summary、warnings、TTL、清理状态。
- `GET /api/v1/test-cases/source-evidence-runs/{run_id}/resources`
  - 输出：资源清单、推荐观察集合、权限状态、download status。
- `POST /api/v1/test-cases/source-evidence-runs/{run_id}/snapshot`
  - 将已读取来源转换为现有生成链路可使用的受控快照。
- `POST /api/v1/test-cases/source-evidence-runs/{run_id}/retry`
  - 权限补齐后重试读取或补下载资源。
- `POST /api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request`
  - 用户显式请求发送整篇源文档协作者授权卡；UI 操作绑定当前 run，授权复用状态按真实源文档 token 归档。
  - 输出：`status`、`message`、`authorization_id`、`target_mode`、`sent_targets_count`、`failed_targets_count`、`fallback_to_default_chat`、`owner_candidates_truncated`、`expires_at`、`can_retry_read`。
  - `status`：`authorization_sent`、`already_sent`、`already_authorized`、`already_readable`、`send_failed`、`bot_not_configured`、`invalid_run_state`、`expired_or_cleaned`。
  - `target_mode`：`owner_direct`、`creator_direct`、`default_chat`、`not_sent`。
  - HTTP：未登录/非成员/跨项目按 `401`/`403`/`404`；`expired_or_cleaned` 返回 `409`；其他业务状态返回 `200`。
  - 安全：拒绝 `knowledge_context`、`qa_knowledge_context`、`project_qa_knowledge`。
- `GET /api/v1/test-cases/source-evidence-authorizations?limit=50&offset=0`
  - 项目管理员/超级管理员查看 Source Evidence 授权最小审计列表；普通成员不可查看项目级授权列表。
- `POST /api/v1/test-cases/source-evidence-authorizations/{authorization_id}/invalidate`
  - 项目管理员/超级管理员手动失效授权复用记录；只停止本系统复用，不自动移除飞书源文档协作者。
- `GET /api/v1/test-cases/source-evidence-authorizations/oauth/callback`
  - Source Evidence 专用 OAuth 回调；使用一次性 `user_access_token` 把项目 App/Bot 加为整篇源文档 `edit` 协作者，不保存个人 token。
- `GET /api/v1/test-cases/source-evidence-cleanup-audits?limit=50&offset=0`
  - 项目管理员/超级管理员查看本项目已清理 run 的最小审计摘要；普通成员不可查看项目级清理列表。
  - 返回内容不得包含已清理的 source.md、raw manifest、图片/附件路径、visual packet、observation 详情、prompt、provider response、飞书 token 或 AI key。

### 10.2 Visual Evidence

- `GET /api/v1/test-cases/source-evidence-runs/{run_id}/visual-candidates`
  - 读取或懒生成视觉候选列表，返回推荐原因、选择状态、下载/权限状态；已清理 run 只返回安全空列表和重新读取提示。
- `POST /api/v1/test-cases/source-evidence-runs/{run_id}/visual-selections`
  - 保存本次用户选择的待观察资源集合。
- `POST /api/v1/test-cases/source-evidence-runs/{run_id}/observations`
  - 调用 Vision AI 观察选中资源；Vision 不可用时返回降级错误，不影响文本生成。
- `GET /api/v1/test-cases/source-evidence-runs/{run_id}/observations`
  - 读取 observation 安全摘要；未采纳 observation 只用于页面复核，不进入生成。
- `POST /api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence`
  - 用户采纳 observation，形成可进入生成依据的证据。
- `DELETE /api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence/{evidence_id}`
  - 用户撤销采纳；撤销后不得进入后续生成。

### 10.3 生成与导出接入

现有 `POST /api/v1/test-cases/generate` 保持兼容，新增可选字段：

- `source_evidence_run_id`
- `adopted_visual_evidence_ids`

兼容原则：

- 仍必须提交 `planning_snapshot` 或由 `source_evidence_run_id` 生成出的 snapshot。
- 未提交 `source_evidence_run_id` 时走 V1 原有流程。
- 提交 run id 时，后端校验 run 属于当前项目、未过期、未清理。
- 只将 adopted visual evidence 注入 prompt。
- 未采纳、未观察、权限失败或 TTL 已过期资源只进入 warnings。

导出接口新增可选 evidence summary：

- TTL 内导出可写入 evidence ref、来源位置和采纳摘要。
- TTL 后不提供证据复查；导出只能提示“证据已清理，需要重新读取来源”。

## 11. 前端方案

保持 `/test-cases` 当前 01/02/03/04 工作台布局，不做大改版。

### 11.1 01 数据源

- 新增飞书文档 URL 来源类型。
- 读取后展示 Source Evidence Run 状态、TTL、来源标题、纳入范围和 warnings。
- 当 run/resource 为 `pending_permission`，或资源下载状态为 `download_failed` 时，在 Source Evidence 状态区显示“申请授权”按钮；点击后调用 `authorization-request`，展示发送目标摘要和“等待作者授权，授权后请点击重试读取”。不新增独立授权管理页，项目管理员授权审计列表本阶段可先只做 API。
- `authorization-request` 前端状态映射固定：`authorization_sent`/`already_sent` 展示“等待作者授权”，禁用重复申请并保留“重试读取”；`already_authorized`/`already_readable` 提示可直接重试读取，不再显示申请按钮；`send_failed`/`bot_not_configured` 展示脱敏错误摘要并允许再次点击申请；`expired_or_cleaned` 禁用申请和生成并提示重新读取来源；`invalid_run_state` 展示当前状态不可申请，不自动改变 run。
- 页面不自动轮询授权状态；授权卡发送后只展示等待提示，用户点击“重试读取”或再次显式申请授权时，后端才重新检查授权记录和读取能力。
- 原飞书电子表格单 Sheet 入口继续存在，适合快速读取单个 Planning Sheet。

### 11.2 02 生成输入

- 当来源为 Source Evidence Run 时，Sheet 选择改为“纳入页签/章节范围”摘要。
- 默认使用后端分类后的纳入范围。
- 允许用户排除非需求页签或反馈页签。
- 展示“文本/表格已读取”“资源清单已生成”“视觉待观察/已采纳”等状态。

### 11.3 04 结果预览

- 当前前端已经取消原始表格/追踪视图和蓝图常驻页签，继续保持聚焦 AI 整理稿、测试用例和限制提示。
- 增加证据状态提示：TTL、已采纳视觉证据数、未观察资源数、权限失败资源数。
- 生成时如证据过期，禁用旧证据生成并提示重新读取来源。

### 11.4 资源清单和视觉采纳

资源清单不应塞进主预览表格。建议使用抽屉或弹窗：

- 资源 ref、类型、来源位置、附近文本、下载状态。
- 系统推荐观察原因。
- 用户选择/取消选择。
- observation 结果预览。
- 采纳/拒绝操作。

## 12. 生成编排接入

### 12.1 Snapshot 适配

为了降低对现有 V1 生成链路的冲击，第一阶段建议将 Source Evidence Run 转换为兼容 `PlanningSnapshotResponse` 的 `Source Evidence Snapshot`：

| 兼容列 | 含义 |
|---|---|
| `来源类型` | docx paragraph、sheet cell、bitable record、resource marker |
| `位置` | block id、Sheet!A1、table record id、resource ref |
| `标题/页签` | 文档标题、Sheet 标题、章节标题 |
| `内容` | 文本/表格片段 |
| `证据状态` | text、table、pending_visual、adopted_visual、excluded |

这样现有 `generation.py` 的 `_render_snapshot_text()` 可以继续工作。后续如需要更强追踪，再新增专用 `SourceEvidenceContext` prompt renderer。

### 12.2 Prompt 规则

生成 prompt 必须加入：

- 飞书文档读取范围。
- 排除页签和原因。
- 未读取/未观察/未采纳的资源清单摘要。
- 已采纳视觉证据摘要和 ref。
- 文本/表格事实与视觉观察的区别。
- 不得把参考案例、未采纳 observation、反馈页签或图片文件名写成需求事实。

### 12.3 warnings

必须保留并合并以下 warning：

- 未读取图片/附件。
- Vision AI 未配置。
- 图片/附件未观察。
- observation 未采纳。
- 权限不足导致资源未下载。
- 某些页签被排除。
- Source Evidence Run 已过期或已清理。
- Feishu API 范围过大、截断或分页失败。

## 13. 测试覆盖

### 13.1 后端

- Feishu docx URL、wiki URL、sheets URL、bitable URL 解析。
- DOCX `raw_content + blocks` 双路径读取。
- 图片块、文件块、inline file、table cell child 提取为资源。
- `source.md` marker 与 `resources.json` ref 一致性。
- 图片下载失败不导致文本读取失败。
- Vision AI 未配置时返回降级状态。
- observation 未采纳时不进入生成 prompt。
- adopted visual evidence 进入生成 prompt 和导出说明。
- Source Evidence Run 跨项目不可读。
- Source Evidence Run TTL 到期后清理原文、图片、附件、视觉包和 observation 详情。
- 最小审计元数据在 TTL 清理后仍保留。
- 访问过期 run 触发懒清理。
- generate 在 evidence 过期时拒绝使用旧证据。
- Source Evidence 授权一刀最低覆盖：专用授权表 migration 索引/唯一键；`authorization-request` 拒绝公共知识字段；跨项目 run 返回 `404`；普通成员不能查看授权审计列表或手动失效授权；OAuth callback 不要求点击人是系统项目成员；originating run 过期或 cleaned 时 callback 失败；OAuth `state` 不包含 URL/token；已有未过期 `authorization_sent` 不重复发卡；`ready` 且无权限失败的 run 不发授权卡。
- Source Evidence 授权一刀后端最小命令：`python -m pytest backend/tests/test_source_evidence_authorization.py backend/tests/test_alembic_migrations.py backend/tests/test_source_evidence_permissions.py`。

### 13.2 前端

- 飞书文档 URL 创建 Source Evidence Run。
- ready/pending_permission/failed/expired/cleaned 状态展示。
- Vision 未配置时显示文本/表格可继续、图片待观察。
- 资源清单推荐和用户选择。
- observation 结果采纳后生成按钮使用已采纳证据。
- 切换来源或证据状态变化后旧结果失效，导出禁用。
- TTL 过期后提示重新读取来源。
- Source Evidence 授权按钮前端最小命令：`cd frontend && npm run test:unit -- testCasesApi TestCaseGeneratorView && npm run build`。

### 13.3 清理与安全

- 源码包不包含 `runtime/source-evidence`。
- 清理脚本不删除参考案例库，但会清理过期 Source Evidence Run。
- 错误、日志、页面和导出不泄露 App Secret、AI Key、Feishu token、OAuth code、原始 prompt。
- 文档-only 决策阶段不跑测试；实现阶段完成后必须执行对应后端/前端最小命令。

## 14. 实施顺序建议

1. 数据模型与存储目录：`Source Evidence Run`、资源元数据、TTL 清理、最小审计。
2. Project Vision AI Credential：配置、状态、权限和脱敏。
3. Feishu rich reader adapter：先移植文本/表格/DOCX blocks/resource inventory，不接 Vision。
4. Source Evidence API：创建 run、读取状态、snapshot 转换、权限错误和 warnings。
5. 生成接入：让 generate 支持 source evidence snapshot，先跑“文本/表格 + 资源清单 + 待观察图片”闭环。
6. 视觉选择与 observation：系统推荐、用户选择、Vision 调用、observation 存储。
7. Adopted Visual Evidence：采纳/撤销、prompt 注入、导出引用。
8. 前端资源清单与状态展示：保持当前页面布局，增加弹窗/抽屉。
9. TTL 清理和审计页面：项目管理员可查看本项目清理摘要，普通成员只在当前页面看到证据过期状态。
10. 端到端验收：真实飞书文档、权限不足、Vision 缺失、TTL 过期、导出复查。

建议先完成 1-5，形成不依赖 Vision 的可用闭环；再做 6-8。这样可以尽快替换现有不足的飞书文档读取，同时不让视觉模型成为主链路阻塞点。

Source Evidence 授权能力建议独立成一刀：先实现后端专用授权模型、Alembic migration、service、`authorization-request`、专用 OAuth callback、管理员审计/失效 API 和权限/安全测试；再接 `/test-cases` 前端“申请授权”按钮；最后把 retry 与授权复用状态打通。不要把这刀和飞书富 reader 文本/表格解析逻辑混在一起。

Source Evidence 授权一刀明确不做：

- 不自动从飞书源文档移除项目 App/Bot 协作者。
- 不自动轮询授权状态。
- 不新增前端管理员授权列表页。
- 不把授权记录纳入 `Source Evidence Run` 7 天 TTL 清理。
- 不保存完整 source URL、doc token、wiki token、file token、OAuth code、`user_access_token` 或 App Secret。

Source Evidence 授权一刀建议文件边界：

- 后端 service：新增 `backend/app/test_cases/source_evidence_authorization.py`，承载授权复用查询、状态机、owner/creator/default chat 发送策略、OAuth callback 校验和最小审计构造。
- 后端 API：先挂在现有 `backend/app/api/test_cases_api.py`，新增 `authorization-request`、专用 OAuth callback、授权审计列表和手动失效接口；如果文件继续变重，再拆独立 router。
- 后端模型/迁移：扩展 `backend/app/models.py` 并新增独立 Alembic migration；迁移必须覆盖唯一键和查询索引。
- 授权模型：新增 `source_evidence_authorizations` 表，唯一键 `project_id + app_id + source_token_hash + permission`；`source_token_hash` 使用 wiki resolve 后真实 `obj_token` 的 sha256，wiki token 只作为 alias/audit hash；查询索引覆盖 `project_id + status + expires_at`、唯一 `state_hash`、`project_id + originating_run_id`；`originating_run_id` 不建外键，只作为审计值，避免和 Source Evidence Run 7 天 TTL 耦合；`source_token_alias_hashes_json` 不建索引。
- 后端测试：新增 `backend/tests/test_source_evidence_authorization.py`，并扩展 `backend/tests/test_alembic_migrations.py`。
- 前端：只改 `frontend/src/types/testCases.ts`、`frontend/src/api/testCases.ts`、`frontend/src/views/TestCaseGeneratorView.vue`；不新增独立授权管理页，不改 V1 飞书电子表格单 Sheet 授权入口。

### 14.1 Source Evidence 授权能力实施计划

本切片目标是让 Source Evidence Run 在读取飞书文档、图片或附件权限不足时，能由项目成员显式向文档 owner / creator 申请把项目 App/Bot 加为整篇源文档 `edit` 协作者；授权成功后，后续 run 可按 `project_id + app_id + resolved obj_token hash + permission=edit` 复用读取权限。该切片不改变 V1 飞书电子表格单 Sheet `view` 授权链路，不自动发卡、不自动轮询、不自动撤销飞书侧协作者、不保存个人 token，不接 Vision。

#### 后端切片

1. 模型与迁移：
   - 在 `backend/app/models.py` 新增 `SourceEvidenceAuthorizationRecord`，表名 `source_evidence_authorizations`。
   - 新增独立 Alembic migration，包含唯一键 `project_id + app_id + source_token_hash + permission`，索引 `project_id + status + expires_at`、唯一 `state_hash`、`project_id + originating_run_id`。
   - `originating_run_id` 不建外键，只作审计值；`source_token_alias_hashes_json` 不建索引。

2. Service：
   - 新增 `backend/app/test_cases/source_evidence_authorization.py`。
   - 实现 token hash、展示指纹、状态机、复用查询、过期判断、手动失效、授权卡发送、OAuth state 生成/校验、callback 成功/失败处理和最小审计摘要。
   - owner / creator 发送策略：owner 优先，最多 3 个；owner 不可达再 creator；全部直发失败再默认群；部分成功即 `authorization_sent`。
   - 所有错误摘要必须复用 Feishu 脱敏规则。

3. API / callback：
   - 在 `backend/app/api/test_cases_api.py` 增加：
     - `POST /api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request`
     - `GET /api/v1/test-cases/source-evidence-authorizations/oauth/callback`
     - `GET /api/v1/test-cases/source-evidence-authorizations?limit=50&offset=0`
     - `POST /api/v1/test-cases/source-evidence-authorizations/{authorization_id}/invalidate`
   - `authorization-request` 要求项目成员；审计列表和失效只允许项目管理员/超级管理员；callback 不要求点击人是系统项目成员。
   - `authorization-request` 拒绝 `knowledge_context`、`qa_knowledge_context`、`project_qa_knowledge`。
   - originating run 过期或 cleaned 时，发卡和 callback 均拒绝继续使用旧证据。

4. Reader / retry 接入：
   - Source Evidence 首次读取权限不足时只标记 `pending_permission`，资源权限不足时标记 `pending_permission` 或 `download_failed`，均不自动发送授权卡。
   - retry 时优先检查有效授权记录；授权有效但仍读不到时不自动发卡，保持 `pending_permission` 或 `download_failed`，由用户显式重新申请。

#### 前端切片

1. 类型与 API：
   - `frontend/src/types/testCases.ts` 增加授权请求/响应、`target_mode`、`status` 类型。
   - `frontend/src/api/testCases.ts` 增加 `requestSourceEvidenceAuthorization(runId)`。

2. 页面：
   - 在 `frontend/src/views/TestCaseGeneratorView.vue` 的 Source Evidence 状态区显示“申请授权”按钮。
   - `authorization_sent` / `already_sent`：展示“等待作者授权”，禁用重复申请，保留“重试读取”。
   - `already_authorized` / `already_readable`：提示可直接重试读取，不再显示申请按钮。
   - `send_failed` / `bot_not_configured`：展示脱敏错误摘要，允许再次点击申请。
   - `expired_or_cleaned`：禁用申请和生成，提示重新读取来源。
   - `invalid_run_state`：展示当前状态不可申请，不自动改变 run。

#### 测试与验收

后端最小命令：

```powershell
python -m pytest backend/tests/test_source_evidence_authorization.py backend/tests/test_alembic_migrations.py backend/tests/test_source_evidence_permissions.py
```

前端最小命令：

```powershell
cd frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build
```

最低测试覆盖：专用授权表 migration 索引/唯一键；公共知识字段拒绝；跨项目 run 返回 `404`；普通成员不能查看审计列表或手动失效；callback 不要求系统项目成员；过期/cleaned run callback 失败；OAuth `state` 不含 URL/token；已有未过期 `authorization_sent` 不重复发卡；`ready` 且无权限失败的 run 不发授权卡；前端状态映射和按钮禁用逻辑。

## 15. 主要风险

- 飞书 DOCX blocks、附件和图片下载权限比电子表格读取复杂，必须做权限状态和重试流。
- DOCX 资源字段形态会随真实文档变化，需要用真实脱敏 fixture 补测试。
- Vision 成本和耗时不可控，所以必须坚持资源清单先出、用户选择、不可用降级。
- TTL 清理容易和“不保存生成历史”边界混淆，文档和代码都要明确 Source Evidence Run 不是生成历史。
- Adopted Visual Evidence 如果没有采纳动作，模型误读会直接污染测试用例；采纳门槛不能省。
- 当前 `PlanningSnapshotResponse` 是表格形态，短期适配可行，但长期可能需要更适合文档块的 `SourceEvidenceContext` prompt renderer。

## 16. 验收标准

- V1 原有上传 Excel、飞书电子表格单 Sheet、参考案例库、生成和导出不回归。
- 项目成员可以读取一个飞书 DOCX/Wiki 来源，得到文本/表格快照和资源清单。
- 未配置 Vision AI 时，仍能基于文本/表格生成用例，并明确提示图片/附件未参与语义理解。
- 配置 Vision AI 后，用户可选择部分资源观察，采纳后再参与生成。
- 未采纳 observation 不影响生成。
- TTL 内可复查 adopted visual evidence；TTL 后原文、图片、附件、视觉包和 observation 详情被清理。
- TTL 后仍能查看最小审计摘要，但不能复查敏感内容。
- 非项目成员不能读取 run、资源、observation 或导出证据。
- 生成和导出不创建生成历史。

## 17. 维护检查清单

- 修改飞书文档读取范围时，同步本文件和 `docs/specs/test-case-generation.md` 的 V2/V1+ 边界。
- 新增稳定领域术语时，只把术语写入 `CONTEXT.md`，不要写实现步骤。
- 改动飞书授权或机器人身份时，同步 `docs/specs/feishu-integration.md`。
- 改动 Vision AI 凭据时，同步 `docs/specs/ai-project-credentials.md`。
- 每个实现切片完成后追加 `PROJECT_RECORD.md`。
- 用户可见行为完成后再更新 `CHANGELOG.md`。
