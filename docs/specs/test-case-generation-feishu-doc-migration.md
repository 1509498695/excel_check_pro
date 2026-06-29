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
- 不默认观察全部图片/附件。
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

- 可选；若直接在 `source_evidence_runs.minimal_audit_json` 中保留摘要，也可以不单独建表。
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

### 10.2 Visual Evidence

- `POST /api/v1/test-cases/source-evidence-runs/{run_id}/visual-selections`
  - 保存本次用户选择的待观察资源集合。
- `POST /api/v1/test-cases/source-evidence-runs/{run_id}/observations`
  - 调用 Vision AI 观察选中资源；Vision 不可用时返回降级错误，不影响文本生成。
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

### 13.2 前端

- 飞书文档 URL 创建 Source Evidence Run。
- ready/pending_permission/failed/expired/cleaned 状态展示。
- Vision 未配置时显示文本/表格可继续、图片待观察。
- 资源清单推荐和用户选择。
- observation 结果采纳后生成按钮使用已采纳证据。
- 切换来源或证据状态变化后旧结果失效，导出禁用。
- TTL 过期后提示重新读取来源。

### 13.3 清理与安全

- 源码包不包含 `runtime/source-evidence`。
- 清理脚本不删除参考案例库，但会清理过期 Source Evidence Run。
- 错误、日志、页面和导出不泄露 App Secret、AI Key、Feishu token、OAuth code、原始 prompt。

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
