# 用例生成飞书文档读取移植 Codex 分步执行提示词

> 用途：把 `docs/specs/test-case-generation-feishu-doc-migration.md` 拆成可逐步复制给 Codex 执行的实现提示词。当前前置状态是用例生成 V1 主链路已完成；本计划只处理 `qa-case` / QA Workspace 飞书文档富读取能力移植，不重做 V1。

## 执行总原则

- 每个切片开始前先读：`CONTEXT.md`、`docs/specs/test-case-generation.md`、`docs/specs/test-case-generation-feishu-doc-migration.md`、`docs/specs/feishu-integration.md`、`docs/specs/ai-project-credentials.md`。
- 当前 V1 代码入口：`backend/app/test_cases/planning_snapshot.py`、`backend/app/test_cases/generation.py`、`backend/app/test_cases/snapshot_brief.py`、`backend/app/api/test_cases_api.py`、`frontend/src/views/TestCaseGeneratorView.vue`、`frontend/src/api/testCases.ts`、`frontend/src/types/testCases.ts`。
- 当前飞书底座：`backend/app/loaders/feishu_reader.py`、`backend/app/integrations/feishu_client.py`、`backend/app/api/feishu_api.py`、`backend/app/services/feishu_sheet_authorization_service.py`。
- QA Workspace 参考来源：`D:\project\QAWORK\qa_workspace\skills\workspace\context-reading\SKILL.md`、`D:\project\QAWORK\qa_workspace\core\context_readers\feishu\rich_reader.py`、`docx_blocks.py`、`openapi.py`、`visual.py`、`source_guard.py`、`rich_models.py`。
- 只移植读取规则、证据模型、资源清单、视觉证据边界和降级策略；不要移植 QA Workspace CLI、`uv run qa ...`、`tasks/<task>/sources/` 本地任务目录、个人 token cache、preflight/setup/role 和知识库维护流。
- 飞书读取主体使用项目级 `Project Feishu Service Identity`，不长期保存当前登录用户个人 OAuth token。
- `Source Evidence Run` 是短期来源证据会话，不是生成历史，不是项目级 QA 知识库。
- 默认 7 天 TTL；到期删除原文快照、图片/附件文件、视觉包和 observation 详情，只保留最小审计元数据。
- 生成用例不得强依赖参考案例，也不得强依赖 Vision；未选择参考案例、未配置 Vision AI 时仍要能基于文本/表格生成。
- 图片/附件 observation 必须先展示，再由用户确认采纳为 `Adopted Visual Evidence` 后才能进入生成上下文和导出。
- 每个切片都要补测试；能跑的测试必须跑，跑不了要记录原因。
- 每个切片完成后追加 `PROJECT_RECORD.md`；用户可见行为完成后再更新 `CHANGELOG.md`。

## 推荐实施顺序

1. 基线检查：确认 V1 工作面、dirty worktree、现有飞书限制和可复用代码。
2. Source Evidence 数据模型、存储目录、TTL 字段和最小审计基础。
3. 飞书富文档 URL 解析与 reader adapter：docx raw+blocks、wiki、sheets 富读取、bitable 预留。
4. Source Evidence Run API：创建 run、状态、资源清单、snapshot 转换、retry，先不接 Vision。
5. 生成与导出接入 Source Evidence：文本/表格 + 资源清单 + 待观察资源闭环。
6. 前端最小闭环：保持 01/02/03/04 布局，新增飞书文档来源、证据状态和资源清单抽屉。
7. Project Vision AI Credential：独立配置、状态、权限、测试连接和脱敏。
8. Visual Observation Selection：资源推荐、用户选择、下载/优化图片和候选包。
9. Observation 与 Adopted Visual Evidence：视觉调用、采纳/撤销、prompt 和导出注入。
10. TTL 清理、懒清理和审计摘要硬化。
11. 全量验收、文档同步和风险清理。

建议先完成 1-6，形成不依赖 Vision 的可用闭环；再做 7-10。这样可以先解决“原有飞书读取不满足需要”的主问题。

## Prompt 0：移植前基线检查

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

阅读当前项目代码和文档，为“用例生成飞书文档读取移植”做基线检查；这一刀不要改业务代码。

必须读取：
- CONTEXT.md
- docs/specs/test-case-generation.md
- docs/specs/test-case-generation-feishu-doc-migration.md
- docs/specs/feishu-integration.md
- docs/specs/ai-project-credentials.md
- backend/app/test_cases/schemas.py
- backend/app/test_cases/planning_snapshot.py
- backend/app/test_cases/generation.py
- backend/app/api/test_cases_api.py
- backend/app/loaders/feishu_reader.py
- backend/app/integrations/feishu_client.py
- backend/app/services/runtime_cleanup.py
- backend/app/models.py
- frontend/src/views/TestCaseGeneratorView.vue
- frontend/src/api/testCases.ts
- frontend/src/types/testCases.ts

同时读取 QA Workspace 参考文件：
- D:\project\QAWORK\qa_workspace\skills\workspace\context-reading\SKILL.md
- D:\project\QAWORK\qa_workspace\core\context_readers\feishu\rich_reader.py
- D:\project\QAWORK\qa_workspace\core\context_readers\feishu\docx_blocks.py
- D:\project\QAWORK\qa_workspace\core\context_readers\feishu\openapi.py
- D:\project\QAWORK\qa_workspace\core\context_readers\feishu\visual.py
- D:\project\QAWORK\qa_workspace\core\context_readers\feishu\source_guard.py

请输出：
1. 当前 V1 已有能力和不能破坏的契约。
2. 当前飞书电子表格读取与飞书文档富读取的差距。
3. QA Workspace 哪些逻辑要移植，哪些明确不要移植。
4. 本次实现建议新增的后端包、模型、API、前端类型和测试文件边界。
5. dirty worktree 中哪些文件已有改动，后续实现时不能误回滚。
6. 第一刀建议从哪个切片开始，以及最小测试命令。
```

## Prompt 1：Source Evidence 数据模型、存储目录和 TTL 基础

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现 Source Evidence Run 的后端基础：数据模型、迁移、存储目录解析、状态枚举、TTL 字段和最小审计元数据。不要接飞书 OpenAPI，不要接前端，不要接 Vision。

目标：
- 新增 Source Evidence Run 和 Source Evidence Resource 的 ORM 模型。
- 新增 Alembic migration。
- Source Evidence Run 按 project_id 隔离，默认 expires_at = created_at + 7 天。
- 存储目录使用 settings.source_evidence_dir 或等价配置，默认位于 runtime/source-evidence/<project_id>/<run_id>/。
- 目录安全校验必须保证所有读写和删除都在 source_evidence_dir 内。
- Run 状态至少支持 reading、ready、pending_permission、vision_pending、failed、expired、cleaned。
- Resource 状态至少支持 pending、downloaded、download_failed、pending_permission、unobserved、observed、adopted、rejected、expired。
- TTL 到期后要能清空敏感字段，但本刀只做字段和 helper，不做完整清理任务。
- 最小审计元数据字段要能保存 run id、项目、来源标识、资源文件名、状态、操作人、创建/清理时间。
- 不新增生成历史表，不保存蓝图/用例/prompt/provider response。

建议文件：
- backend/app/models.py
- migrations/versions/0012_source_evidence_runs.py
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/source_evidence_storage.py
- backend/app/test_cases/schemas.py
- backend/tests/test_source_evidence_models.py
- backend/tests/test_source_evidence_storage.py
- backend/tests/test_alembic_migrations.py

必须覆盖：
- 创建 run 时 project_id、created_by、expires_at、status 正确。
- 不同 project_id 的 run/resource 查询隔离。
- storage path 不能逃逸 source_evidence_dir。
- TTL 过期判断以 expires_at 为准。
- cleanup/minimal audit helper 不保留原文、文件路径、observation 详情或 prompt。
- 不创建任何生成历史表。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_models.py backend/tests/test_source_evidence_storage.py backend/tests/test_alembic_migrations.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 2：飞书富文档 Reader Adapter

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现当前项目内的飞书富文档 reader adapter。只做可单测的读取/解析层，不落库、不接 API、不接前端。

目标：
- 新增 Feishu source URL 解析，支持 docx、docs、wiki、sheets、base/bitable 的识别；原有 feishu_reader.py 的电子表格解析保持兼容，不要破坏个人校验和 V1 单 Sheet 快照。
- wiki 链接先解析 obj_type，再路由到 docx/sheets/bitable。
- docx 读取必须同时读取 raw_content 和 /docx/v1/documents/{token}/blocks。
- docx blocks 要提取图片块、文件块、inline file、inline block、表格单元格子块和 unsupported resource candidates。
- docx 文本中保留 <image ref="..." position="..." /> 和 <attachment ref="..." position="..." /> marker。
- 不把 raw_content 中出现的 image.png 文件名当作真实图片证据。
- sheets 富读取要读取可见 Sheet 集合，保留 Sheet title、坐标、稀疏单元格、资源位置、隐藏 Sheet 排除 warning。
- bitable 先做架构预留和只读 records/search 基础解析，允许 API 暂不开放。
- 输出统一 Parsed Source 结构，包含 markdown/source units/resources/raw manifest/warnings。
- 所有 Feishu 错误必须脱敏，不输出 app_secret、tenant_access_token、user_access_token、OAuth code。

建议文件：
- backend/app/test_cases/feishu_rich_reader.py
- backend/app/test_cases/feishu_source_parser.py
- backend/app/integrations/feishu_client.py（只补必要通用 OpenAPI helper，避免破坏现有 sheets API）
- backend/app/test_cases/schemas.py
- backend/tests/test_test_case_feishu_source_parser.py
- backend/tests/test_test_case_feishu_rich_reader_docx.py
- backend/tests/test_test_case_feishu_rich_reader_sheets.py
- backend/tests/test_feishu_client.py
- backend/tests/test_feishu_reader.py

参考实现：
- D:\project\QAWORK\qa_workspace\core\context_readers\feishu\rich_reader.py
- D:\project\QAWORK\qa_workspace\core\context_readers\feishu\docx_blocks.py
- D:\project\QAWORK\qa_workspace\core\context_readers\feishu\rich_models.py

不要移植：
- QA Workspace CLI 命令。
- 本机个人 token cache。
- tasks/<task>/sources 目录命名。
- preflight/setup/role。
- 知识库草稿和审阅流程。

必须覆盖：
- docx URL 解析成功。
- wiki docx 解析后读取 docx。
- docx raw_content 缺失 content 时失败。
- docx blocks 分页 has_more 正常处理。
- image/file/inline block/table cell resource 生成稳定 ref。
- unsupported candidates 不渲染为 image marker。
- sheets 隐藏页签被排除并记录 warning。
- sheets 稀疏单元格保留坐标，不强行生成巨大 dense Markdown。
- 旧 feishu 电子表格 metadata/preview 单测不回归。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_feishu_source_parser.py backend/tests/test_test_case_feishu_rich_reader_docx.py backend/tests/test_test_case_feishu_rich_reader_sheets.py backend/tests/test_feishu_client.py backend/tests/test_feishu_reader.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 3：Source Evidence Run API 文本/表格闭环

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

把飞书富文档 reader 接入 Source Evidence Run API，先形成“文本/表格 + 资源清单 + 待观察图片/附件”的后端闭环。不要接 Vision，不要改生成 prompt。

目标：
- 新增 POST /api/v1/test-cases/source-evidence-runs。
- 新增 GET /api/v1/test-cases/source-evidence-runs/{run_id}。
- 新增 GET /api/v1/test-cases/source-evidence-runs/{run_id}/resources。
- 新增 POST /api/v1/test-cases/source-evidence-runs/{run_id}/snapshot。
- 新增 POST /api/v1/test-cases/source-evidence-runs/{run_id}/retry。
- 创建 run 后服务端读取飞书来源，写入 source.md、source.meta.json、manifest.json、resources.json、tables.json、raw/ 等短期证据文件。
- 图片/附件下载允许失败；失败不阻断文本/表格 ready，但资源状态要标记 pending_permission/download_failed。
- snapshot 接口把 Source Evidence Run 转成兼容 PlanningSnapshotResponse 的 Source Evidence Snapshot。
- 兼容列建议为 来源类型、位置、标题/页签、内容、证据状态。
- run 过期或 cleaned 时 snapshot/generate 相关接口必须拒绝使用，并提示重新读取来源。
- 所有 API 走严格项目成员校验；跨项目 run/resource 不可读。
- 保留 V1 /planning-snapshot 的 uploaded_excel/feishu 单 Sheet 行为，不强行把旧路径切到 Source Evidence。

建议文件：
- backend/app/api/test_cases_api.py
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/source_evidence_storage.py
- backend/app/test_cases/feishu_rich_reader.py
- backend/app/test_cases/schemas.py
- backend/tests/test_source_evidence_api.py
- backend/tests/test_source_evidence_snapshot.py
- backend/tests/test_source_evidence_permissions.py

必须覆盖：
- 项目成员创建 docx source evidence run 成功。
- ready run 能返回 source summary、warnings、TTL、资源数量。
- resources API 返回 ref/type/position/filename/download_status/adoption_status。
- 下载失败只进入 warnings，不阻断文本/表格 snapshot。
- pending_permission 状态可 retry。
- snapshot 转换后的 PlanningSnapshotResponse 可被现有 brief/generate schema 接收。
- expired/cleaned run 拒绝 snapshot。
- 跨项目 run/resource 返回 404 或 403。
- 公共请求仍拒绝 knowledge_context。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_api.py backend/tests/test_source_evidence_snapshot.py backend/tests/test_source_evidence_permissions.py backend/tests/test_test_case_api_contracts.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 4：生成和导出接入 Source Evidence

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

把 Source Evidence Run 接入现有 generate/export，但仍以文本/表格为主，不接视觉 observation。目标是让飞书文档读取后的 snapshot 可以生成高质量用例。

目标：
- TestCaseGenerationRequest 新增可选 source_evidence_run_id。
- TestCaseExportRequest 新增可选 source_evidence_summary 或 evidence_summary。
- generate 继续要求 planning_snapshot；当传 source_evidence_run_id 时，校验 run 属于当前项目、未过期、未清理。
- prompt 中加入 Source Evidence 读取范围、排除页签/章节、资源清单摘要和未观察/未采纳限制。
- prompt 必须区分“文本/表格事实”和“待观察图片/附件”，不得把文件名、附近文字或未观察资源写成已确认需求依据。
- 未选择参考案例时仍能生成；参考案例仍只是格式、粒度和历史风格增强。
- 导出生成说明 Sheet 增加 Source Evidence 摘要和 TTL 状态；不写入原文全文、token、prompt 或 provider response。
- TTL 已过期或 cleaned 的 source_evidence_run_id 拒绝生成和导出证据复查。

建议文件：
- backend/app/test_cases/schemas.py
- backend/app/test_cases/generation.py
- backend/app/test_cases/exporter.py
- backend/app/test_cases/source_evidence.py
- backend/app/api/test_cases_api.py
- backend/tests/test_test_case_generation.py
- backend/tests/test_test_case_exporter.py
- backend/tests/test_source_evidence_generation.py

必须覆盖：
- source_evidence_run_id 为空时 V1 原链路不回归。
- source_evidence_run_id 有效时 prompt 包含读取范围、资源清单摘要和未观察 warning。
- 未观察图片/附件不会进入需求事实。
- expired/cleaned run 被拒绝生成。
- 导出包含 evidence summary，但不包含原文、token、prompt、API Key。
- 无参考 + Source Evidence Snapshot 能成功生成。
- 参考案例仍不能作为需求来源。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_generation.py backend/tests/test_test_case_generation.py backend/tests/test_test_case_exporter.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 5：前端接入飞书文档来源和证据状态

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

在现有 TestCaseGeneratorView 上接入飞书文档来源和 Source Evidence 状态。不要重排 01/02/03/04，不恢复“原始表格/追踪视图”和“用例蓝图”页签。

目标：
- frontend/src/types/testCases.ts 增加 Source Evidence Run、Resource、Snapshot 请求/响应类型。
- frontend/src/api/testCases.ts 增加 source-evidence-runs 相关 API。
- 01 数据源保留现有 DataSourcePanel，同时新增“飞书文档 URL”入口或轻量输入区。
- 创建 Source Evidence Run 后展示来源标题、状态、TTL、warnings、资源数量。
- 02 生成输入展示“纳入页签/章节范围”“文本/表格已读取”“资源清单已生成”“图片/附件待观察”。
- 资源清单使用抽屉或弹窗展示，不塞进主预览表格。
- 读取快照时，飞书文档来源走 /source-evidence-runs/{run_id}/snapshot；旧 Excel/飞书表格单 Sheet 仍走 /planning-snapshot。
- 生成请求在有 run 时带 source_evidence_run_id。
- 切换来源、run 状态、资源选择或 snapshot 后，旧生成结果失效，导出禁用。
- 04 结果预览只保留 AI 整理稿、测试用例、限制提示，并增加证据状态提示。

建议文件：
- frontend/src/types/testCases.ts
- frontend/src/api/testCases.ts
- frontend/src/views/TestCaseGeneratorView.vue
- frontend/tests/unit/testCasesApi.test.ts
- frontend/tests/unit/TestCaseGeneratorView.test.ts

必须覆盖：
- 旧 uploaded_excel 读取和生成不回归。
- 创建 Source Evidence Run 后能读取兼容 snapshot。
- generate 请求带 source_evidence_run_id。
- Vision 未接入时页面显示“文本/表格可继续，图片/附件待观察”。
- resources 抽屉展示 ref/type/position/status。
- expired/cleaned 状态禁用生成并提示重新读取来源。
- 预览页签不出现“原始表格/追踪视图”和“用例蓝图”。

必须测试：
cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build

完成后追加 PROJECT_RECORD.md；用户可见行为完成后更新 CHANGELOG.md。
```

## Prompt 6：Project Vision AI Credential

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

新增独立项目级 Vision AI Credential。它不能复用当前文本生成的 Project AI Credential，但可以复用加密、脱敏、provider preset 和测试连接的代码风格。

目标：
- 新增 ProjectVisionAiCredentialRecord 或等价 credential kind，按 project_id 唯一。
- 密钥加密存储，普通成员只看 configured/enabled/status，不看密钥。
- 项目管理员/超级管理员可查看、保存、删除、测试 Vision AI 配置。
- Vision 未配置时 Source Evidence 文本/表格读取和生成继续可用，只提示图片/附件待观察。
- 不让文本 AI 凭据自动兜底 Vision 调用。
- 错误、日志和响应不得泄露完整 API Key、Base URL 中敏感 query、额外 header。

建议文件：
- backend/app/models.py
- migrations/versions/0013_project_vision_ai_credentials.py
- backend/app/ai/vision_credentials.py
- backend/app/admin/schemas.py
- backend/app/admin/router.py
- frontend/src/api/projectVisionAiConfig.ts 或并入 admin API
- frontend/src/types/projectVisionAiConfig.ts
- frontend/src/features/admin/projectVisionAiConfigForm.ts
- frontend/src/components/admin/FeishuBotConfigCard.vue 或合适的后台配置卡片
- backend/tests/test_project_vision_ai_config_api.py
- frontend/tests/unit/projectVisionAiConfig*.test.ts

必须覆盖：
- 管理员可保存/测试/删除 Vision AI 凭据。
- 普通成员不可保存/删除/测试，只能通过业务 API 看状态。
- Vision 凭据缺失不影响 Source Evidence text/table snapshot。
- 文本 Project AI Credential 和 Vision AI Credential 互不覆盖。
- 密钥脱敏和错误脱敏。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_project_vision_ai_config_api.py backend/tests/test_project_ai_config_api.py

cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- projectVisionAiConfig projectAiConfig
npm run build

完成后追加 PROJECT_RECORD.md；同步 docs/specs/ai-project-credentials.md。
```

## Prompt 7：Visual Observation Selection 和视觉候选包

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现图片/附件资源选择和视觉候选包准备，但先不调用 Vision AI 生成 observation。

目标：
- Source Evidence Run 读取后基于 resources.json 生成 visual_candidates.json。
- 对本地可用图片生成 optimized image，保存在 visual_evidence/images/。
- 系统按文档位置、文件类型、文件名、附近文本、重复度、图片尺寸和预算生成推荐观察集合。
- API 支持读取候选列表和保存用户选择。
- 不默认全量观察所有图片/附件。
- 下载失败、权限不足、非图片附件要清晰展示状态。
- Source Evidence Run 未过期时，后续配置 Vision AI 后可以重新选择和观察。

建议 API：
- GET /api/v1/test-cases/source-evidence-runs/{run_id}/visual-candidates
- POST /api/v1/test-cases/source-evidence-runs/{run_id}/visual-selections

建议文件：
- backend/app/test_cases/visual_evidence.py
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/schemas.py
- backend/app/api/test_cases_api.py
- frontend/src/types/testCases.ts
- frontend/src/api/testCases.ts
- frontend/src/views/TestCaseGeneratorView.vue
- backend/tests/test_source_evidence_visual_candidates.py
- frontend/tests/unit/TestCaseGeneratorView.test.ts

参考实现：
- D:\project\QAWORK\qa_workspace\core\context_readers\feishu\visual.py

必须覆盖：
- resources 中 image 生成候选。
- missing local_path 的资源进入 missing/pending。
- optimized image 路径在 source evidence run 目录内。
- 推荐集合不是全量默认。
- 用户选择保存后可读取。
- 过期/cleaned run 禁止创建选择。
- 前端资源抽屉能显示推荐理由和选择状态。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_visual_candidates.py backend/tests/test_source_evidence_permissions.py

cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build

完成后追加 PROJECT_RECORD.md。
```

## Prompt 8：Vision Observation 与 Adopted Visual Evidence

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现 Vision observation 和 Adopted Visual Evidence。核心边界：已观察不等于已采纳，未采纳 observation 不得进入生成。

目标：
- API 调用独立 Project Vision AI Credential 对用户选择的资源生成 observation。
- observation 存储在 Source Evidence Run 的短期视觉包中，并有 DB 元数据索引。
- observation 包含 ref、summary、visible_text、confidence、limitations、source、created_by、created_at。
- observation 结果先展示给用户，不自动进入生成上下文。
- 用户确认采纳后形成 Adopted Visual Evidence。
- 支持撤销采纳；撤销后不得进入后续生成。
- generate 新增 adopted_visual_evidence_ids 可选字段。
- 只有 adopted visual evidence 能进入 prompt、蓝图 warnings、用例 remarks 和导出说明。
- Vision 不可用时返回降级错误，不影响文本/表格生成。

建议 API：
- POST /api/v1/test-cases/source-evidence-runs/{run_id}/observations
- GET /api/v1/test-cases/source-evidence-runs/{run_id}/observations
- POST /api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence
- DELETE /api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence/{evidence_id}

建议文件：
- backend/app/test_cases/visual_evidence.py
- backend/app/test_cases/generation.py
- backend/app/test_cases/exporter.py
- backend/app/test_cases/schemas.py
- backend/app/api/test_cases_api.py
- frontend/src/types/testCases.ts
- frontend/src/api/testCases.ts
- frontend/src/views/TestCaseGeneratorView.vue
- backend/tests/test_source_evidence_observations.py
- backend/tests/test_source_evidence_generation.py
- backend/tests/test_test_case_exporter.py
- frontend/tests/unit/TestCaseGeneratorView.test.ts

必须覆盖：
- Vision 未配置时 observations API 返回可展示错误，run 仍可用于文本生成。
- 已观察未采纳不进入 generate prompt。
- adopted evidence 进入 generate prompt，且带 ref/position/summary/limitations。
- 撤销采纳后不再进入 generate prompt。
- 跨项目 adopted evidence 被拒绝。
- 导出只包含已采纳证据摘要，不包含原图路径、token、prompt 或 provider response。
- TTL 过期后拒绝 observation/adoption。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_observations.py backend/tests/test_source_evidence_generation.py backend/tests/test_test_case_exporter.py backend/tests/test_project_vision_ai_config_api.py

cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build

完成后追加 PROJECT_RECORD.md。
```

## Prompt 9：TTL 清理、懒清理和审计摘要

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

硬化 Source Evidence Run 的 TTL 清理和最小审计。重点是敏感材料到期必须删除，但最小审计元数据不跟 7 天 TTL 一起删。

目标：
- 后台 runtime cleanup 纳入过期 Source Evidence Run。
- API 访问 run/resources/snapshot/visual 时先做懒清理：如果已过期，立即清理并返回 expired/cleaned 状态。
- TTL 到期删除 source.md、raw/、images/、attachments/、visual_evidence/、observation 详情、adopted evidence 可复查详情。
- 清理后保留最小审计元数据：run id、project id、来源标识、资源文件名、状态、操作人、创建时间、清理时间、最小错误摘要。
- 项目管理员可查看本项目 Source Evidence Cleanup Audit Summary；普通成员不能查看项目级清理列表，只能在当前页面遇到过期证据时看到状态。
- 不提供已清理内容、视觉包或 observation 明细复查。
- 清理不能删除参考案例库、普通上传未到期文件或非 runtime 目录。

建议 API：
- GET /api/v1/test-cases/source-evidence-cleanup-audits

建议文件：
- backend/app/services/runtime_cleanup.py
- backend/app/test_cases/source_evidence_cleanup.py
- backend/app/test_cases/source_evidence.py
- backend/app/api/test_cases_api.py
- backend/app/test_cases/schemas.py
- backend/tests/test_source_evidence_cleanup.py
- backend/tests/test_runtime_cleanup.py
- frontend/src/types/testCases.ts
- frontend/src/api/testCases.ts

必须覆盖：
- 后台清理删除敏感文件和 observation 详情。
- 懒清理在访问过期 run 时触发。
- cleaned run 不再返回 source.md/resources local_path/observation detail。
- 最小审计元数据仍可被项目管理员查看。
- 普通成员不能查看项目级清理记录列表。
- 清理路径安全，不越界删除。
- 参考案例库物理文件不被 Source Evidence cleanup 删除。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_cleanup.py backend/tests/test_runtime_cleanup.py backend/tests/test_source_evidence_permissions.py

完成后追加 PROJECT_RECORD.md；同步 docs/specs/test-case-generation-feishu-doc-migration.md。
```

## Prompt 10：全量验收和文档同步

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

对用例生成飞书文档读取移植做全量验收、文档同步和风险清理。不要新增新功能。

必须检查：
- V1 上传 Excel、飞书电子表格单 Sheet、参考案例库、生成、导出不回归。
- Source Evidence Run 不是生成历史，不保存蓝图/用例/prompt/provider response。
- 飞书 docx/wiki 文档可以读取文本/表格和资源清单。
- Vision 未配置时，文本/表格生成仍可用，图片/附件明确待观察。
- Vision 配置后，只有用户选择的资源会被观察。
- observation 未采纳不进入生成；Adopted Visual Evidence 才能进入生成和导出。
- TTL 到期删除原文、图片/附件、视觉包和 observation 详情，只保留最小审计。
- TTL 后用户需要重新读取来源才能复查证据。
- 非项目成员不能读取 run/resource/observation/adopted evidence。
- 页面仍保持 01/02/03/04 布局，不恢复原始表格/追踪视图和用例蓝图页签。
- 错误、日志、页面和导出不泄露 App Secret、AI Key、Feishu token、OAuth code、原始 prompt。

建议后端测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_api_contracts.py backend/tests/test_test_case_planning_snapshot.py backend/tests/test_test_case_generation.py backend/tests/test_test_case_exporter.py backend/tests/test_test_case_reference_models.py backend/tests/test_test_case_reference_profiles.py backend/tests/test_test_case_reference_library_api.py backend/tests/test_source_evidence_models.py backend/tests/test_source_evidence_storage.py backend/tests/test_test_case_feishu_source_parser.py backend/tests/test_test_case_feishu_rich_reader_docx.py backend/tests/test_test_case_feishu_rich_reader_sheets.py backend/tests/test_source_evidence_api.py backend/tests/test_source_evidence_snapshot.py backend/tests/test_source_evidence_generation.py backend/tests/test_source_evidence_visual_candidates.py backend/tests/test_source_evidence_observations.py backend/tests/test_source_evidence_cleanup.py backend/tests/test_project_ai_config_api.py backend/tests/test_project_vision_ai_config_api.py backend/tests/test_feishu_client.py backend/tests/test_feishu_reader.py backend/tests/test_feishu_permission_api.py backend/tests/test_source_api_security.py backend/tests/test_alembic_migrations.py

建议前端测试：
cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView projectVisionAiConfig
npm run build

文档同步：
- 如果实现中接口名、字段名、状态枚举或限制值有变化，同步 docs/specs/test-case-generation-feishu-doc-migration.md。
- 如果飞书授权主体或权限流程有变化，同步 docs/specs/feishu-integration.md。
- 如果 Vision AI 凭据行为有变化，同步 docs/specs/ai-project-credentials.md。
- 如果新增稳定领域术语，只更新 CONTEXT.md 术语，不写实现细节。
- 更新 PROJECT_RECORD.md。
- 用户可见行为完成后更新 CHANGELOG.md。

最终输出：
1. 改动摘要。
2. 验证命令和结果。
3. 未完成项和风险。
4. 下一步建议。
```
