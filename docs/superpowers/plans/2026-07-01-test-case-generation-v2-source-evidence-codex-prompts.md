# 用例生成 V2 Source Evidence Codex 分步执行提示词

> 用途：把 `docs/specs/test-case-generation-v2-requirements.md` 和 `docs/specs/test-case-generation-v2-source-evidence.md` 拆成可逐步复制给 Codex 执行的实现提示词。当前前置状态是飞书 Source Evidence、视觉证据、采纳和清理基础已经存在；本计划重点把 V2 主链路扩展到本地文件、SVN 文件、`.xls` 内嵌图片和最终验证。

## 执行总原则

- 每个切片开始前先读：`CONTEXT.md`、`docs/adr/0002-generalize-source-evidence-for-test-case-generation-v2.md`、`docs/specs/test-case-generation-v2-requirements.md`、`docs/specs/test-case-generation-v2-source-evidence.md`、`docs/specs/data-sources.md`、`docs/specs/ai-project-credentials.md`。
- 当前关键代码入口：`backend/app/test_cases/source_evidence.py`、`backend/app/test_cases/visual_evidence.py`、`backend/app/test_cases/source_evidence_storage.py`、`backend/app/test_cases/source_evidence_cleanup.py`、`backend/app/test_cases/generation.py`、`backend/app/test_cases/exporter.py`、`backend/app/test_cases/schemas.py`、`backend/app/api/test_cases_api.py`、`frontend/src/views/TestCaseGeneratorView.vue`、`frontend/src/api/testCases.ts`、`frontend/src/types/testCases.ts`。
- 当前 V2 主链路目标：`feishu`、`local_file`、`svn_file` 都创建 `Source Evidence Run`；本地/SVN 不再把新能力塞进旧 `planning-snapshot`。
- 当前代码差距：`SourceEvidenceRunCreateRequest.source_type` 仍是 `Literal["feishu"]`；`source_evidence.py` 创建、重试和 snapshot 读取仍调用 `_read_and_persist_feishu_source`；前端 `createFeishuSourceEvidenceRun` 仍硬编码 `source_type: 'feishu'`。
- `.xls` 内嵌图片是 V2.0 首批硬要求。实现应通过受控 LibreOffice headless / `soffice` 转换为 `.xlsx` 后复用 `.xlsx` 图片解析；转换失败不得伪装为图片已读取。
- 图片永远不是自动事实。只有 `Adopted Visual Evidence` 可以进入生成和导出；未观察、未采纳、提取失败或转换失败的图片只能进入 warnings。
- SVN Source Evidence 必须使用项目级 SVN 凭据和 `Source Evidence SVN Root`；不要把个人 SVN 凭据读取出的内容做成项目级共享证据。
- 本计划不以旧 V1 `Planning Sheet Snapshot` 兼容为主要验收目标；旧代码可以保留，但 V2 页面默认应走 Source Evidence。
- 每个切片都要补自动化测试；能跑的测试必须跑，跑不了要记录原因。
- 每个实现切片完成后追加 `PROJECT_RECORD.md`；用户可见行为完成后同步 `CHANGELOG.md`。
- 不要回滚工作区已有的飞书迁移、Source Evidence、Vision、前端或文档改动；遇到 dirty worktree 先确认差异来源，再在最小范围内追加修改。

## 推荐实施顺序

1. V2 基线检查：确认当前 Source Evidence 能力、dirty worktree、飞书迁移已完成范围和剩余差距。
2. 通用 Source Evidence adapter 契约：扩展 `source_type`、拆出 reader dispatcher、准备 `local_file` 上传和 `svn_file` 创建入口。
3. 本地文件 reader：支持 `.xlsx` 文本/表格/图片和独立图片文件。
4. `.xls` 转换器：新增受控 `soffice` converter，转换后复用 `.xlsx` reader，并覆盖失败降级。
5. SVN Source Evidence：新增 `Source Evidence SVN Root` 校验，使用项目级 SVN 凭据拉取文件后复用本地 reader。
6. 通用 snapshot 和资源 manifest：去掉 snapshot 对 `ParsedFeishuSource` 的硬编码，统一本地/SVN/飞书输出。
7. `visual validate`：生成和导出前强制校验 adopted evidence；未采纳图片只出 warning。
8. 前端 V2 三入口统一：本地文件、SVN 文件、飞书文档全部展示同一套 Source Evidence 状态和视觉流程。
9. 运行能力展示：暴露 SVN、Vision、LibreOffice/soffice 可用性和降级提示。
10. 全链路验收：用真实 `.xlsx`、`.xls`、SVN `.xls`、独立图片和 Vision/soffice 缺失场景验证。

建议先完成 1-6，形成“来源读取 + resource + snapshot”闭环；再做 7-9。这样可以先证明本地/SVN/`.xls` 图片进入 Source Evidence，而不把前端和生成校验混进同一刀。

## Prompt 0：V2 基线检查和切片确认

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

阅读当前项目代码和文档，为“用例生成 V2 Source Evidence”做基线检查；这一刀不要改业务代码。

必须读取：
- CONTEXT.md
- docs/adr/0002-generalize-source-evidence-for-test-case-generation-v2.md
- docs/specs/test-case-generation-v2-requirements.md
- docs/specs/test-case-generation-v2-source-evidence.md
- docs/specs/data-sources.md
- docs/specs/ai-project-credentials.md
- backend/app/test_cases/schemas.py
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/visual_evidence.py
- backend/app/test_cases/source_evidence_storage.py
- backend/app/test_cases/source_evidence_cleanup.py
- backend/app/test_cases/generation.py
- backend/app/test_cases/exporter.py
- backend/app/api/test_cases_api.py
- backend/app/loaders/local_reader.py
- backend/app/loaders/svn_cache.py
- backend/app/loaders/svn_manager.py
- backend/app/admin/router.py
- backend/config.py
- frontend/src/views/TestCaseGeneratorView.vue
- frontend/src/api/testCases.ts
- frontend/src/types/testCases.ts

请输出：
1. 当前 Source Evidence 已有能力：run/resource/visual/observation/adoption/cleanup/generate/export。
2. 当前 Feishu-only 限制点：source_type、reader、snapshot、retry、前端创建入口。
3. 本地文件、SVN 文件、`.xls` 图片、visual validate 的缺口。
4. 需要新增或修改的后端模块、前端模块、配置项和测试文件。
5. dirty worktree 中哪些文件已有改动，后续实现时不能误回滚。
6. 推荐第一刀和最小测试命令。
```

## Prompt 1：通用 Source Evidence Adapter 契约和 API 骨架

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现 V2 Source Evidence 通用来源契约和 API 骨架。目标是让后端不再把 Source Evidence 创建、重试和 snapshot 绑定死在 Feishu reader 上；本刀不实现 `.xlsx/.xls` 图片提取，也不接前端。

必须先读：
- docs/specs/test-case-generation-v2-requirements.md
- docs/specs/test-case-generation-v2-source-evidence.md
- backend/app/test_cases/schemas.py
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/feishu_rich_reader.py
- backend/app/api/test_cases_api.py
- backend/tests/test_source_evidence_api.py
- backend/tests/test_source_evidence_snapshot.py

目标：
- 将 `SourceEvidenceRunCreateRequest.source_type` 扩展为 `feishu | svn_file`。
- 新增本地文件上传创建接口骨架：`POST /api/v1/test-cases/source-evidence-runs/upload`，用于后续 `local_file`。
- 在 service 层引入 reader dispatcher，例如 `read_and_persist_source_evidence_run`，按 `run.source_type` 分发到 Feishu/local/SVN reader。
- 保留 Feishu 现有行为，但把 `_read_and_persist_feishu_source` 变成 adapter 分支，不再由 create/retry 直接硬编码调用。
- 设计通用 parsed source 模型或最小通用 manifest，使 snapshot 后续可以读取 `raw/parsed_source.json` 而不依赖 `ParsedFeishuSource`。
- `local_file` 和 `svn_file` 暂可返回明确的 501/400 待实现错误，但接口、类型和分发边界必须可测。
- 不改旧 `/planning-snapshot` 主体逻辑；V2 新入口走 Source Evidence。

建议文件：
- backend/app/test_cases/schemas.py
- backend/app/test_cases/source_evidence.py
- backend/app/api/test_cases_api.py
- backend/tests/test_source_evidence_api.py
- backend/tests/test_source_evidence_snapshot.py
- frontend/src/types/testCases.ts（只同步类型可选，前端行为留后续 prompt）

必须覆盖：
- `feishu` 创建 run 行为不因 dispatcher 改造失败。
- `svn_file` JSON 创建请求能进入 dispatcher，并在 reader 未实现时返回明确中文错误。
- `local_file` 上传接口存在，未实现 reader 时返回明确中文错误。
- retry 不再直接调用 Feishu 私有函数，而是走 dispatcher。
- snapshot 读取 Feishu run 仍可用。
- source_type 非允许值被 Pydantic 拒绝。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_api.py backend/tests/test_source_evidence_snapshot.py backend/tests/test_test_case_api_contracts.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 2：本地文件 Source Evidence Reader（.xlsx + 独立图片）

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现 `local_file` Source Evidence reader 的第一阶段：本地上传 `.xlsx` 工作簿和独立图片文件。不要实现 `.xls` 转换；不要接 SVN。

必须先读：
- docs/specs/test-case-generation-v2-requirements.md
- docs/specs/test-case-generation-v2-source-evidence.md
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/source_evidence_storage.py
- backend/app/test_cases/visual_evidence.py
- backend/app/loaders/local_reader.py
- backend/app/api/test_cases_api.py
- backend/config.py

目标：
- `POST /source-evidence-runs/upload` 接收浏览器上传文件并创建 `local_file` run。
- 上传文件只写入当前 Source Evidence Run 目录，随 TTL 清理；不要写入长期数据源配置。
- 支持 `.xlsx`：
  - 读取可见 Sheet 的文本/表格。
  - 隐藏 Sheet 默认排除并写 warning。
  - 提取内嵌图片，写入 run 的 `images/` 目录。
  - 每张图片登记为 `SourceEvidenceResourceRecord`，包含 ref、type=image、position、filename、mime_type、local_path、download_status。
- 支持独立图片 `.png/.jpg/.jpeg/.webp`：
  - 创建 run 后登记为 image resource。
  - 因无文本主体，snapshot 可以返回资源摘要和 warning；生成前必须依赖后续 adopted evidence。
- 生成通用 `source.md`、`raw/parsed_source.json`、`resources.json`、`manifest.json`。
- 图片 ref 使用稳定格式，例如 `excel_img_s001_001`、`local_img_001`。
- position 使用人可读格式，例如 `excel:sheet=活动配置:image=1:anchor=B12`。

建议新增文件：
- backend/app/test_cases/local_source_reader.py
- backend/app/test_cases/excel_source_reader.py
- backend/tests/test_source_evidence_local_file.py
- backend/tests/test_source_evidence_excel_reader.py

建议修改文件：
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/schemas.py
- backend/app/api/test_cases_api.py

必须覆盖：
- 上传 `.xlsx` 后 run 为 ready。
- `.xlsx` 可见 Sheet 文本进入 snapshot。
- 隐藏 Sheet 不进入文本主体，并产生 warning。
- `.xlsx` 内嵌图片进入 resources，local_path 在 run 目录内。
- 图片 ref 稳定、无本地绝对路径泄露到 API 响应。
- 独立图片 run 在 resources 中有 image，但 snapshot 明确提示缺少文本主体。
- 非允许后缀拒绝。
- 上传文件路径不能逃逸 source_evidence_dir。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_local_file.py backend/tests/test_source_evidence_excel_reader.py backend/tests/test_source_evidence_api.py backend/tests/test_source_evidence_storage.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 3：.xls 转换器和 .xls 内嵌图片读取

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现 `.xls` 内嵌图片读取。首选技术路线是受控 LibreOffice headless / `soffice` 转换为 `.xlsx`，再复用上一刀的 `.xlsx` 图片解析。

必须先读：
- docs/specs/test-case-generation-v2-requirements.md
- docs/specs/test-case-generation-v2-source-evidence.md
- docs/adr/0002-generalize-source-evidence-for-test-case-generation-v2.md
- backend/app/test_cases/excel_source_reader.py
- backend/app/test_cases/source_evidence_storage.py
- backend/config.py
- backend/requirements.in
- backend/requirements.txt

目标：
- 新增配置项，例如 `source_evidence_soffice_executable`、`source_evidence_conversion_timeout_seconds`。
- 新增 converter 模块，服务端固定读取配置的 `soffice`，不接受请求传入命令。
- `.xls` 文本继续用 `xlrd` 读取。
- `.xls` 图片提取流程：
  1. 把源 `.xls` 复制或只读传入 converter。
  2. 转换产物写入 `raw/converted/source.xlsx`。
  3. 用 `.xlsx` reader 提取图片和位置。
  4. 文本主体仍以 `.xls` 读取结果为准，避免转换改变单元格显示。
- converter 必须使用独立临时 profile、输出目录限制、超时、错误脱敏。
- 不执行宏、不联网、不跟随外部链接。
- 转换失败时：
  - 如果 `.xls` 文本可读，run 仍可 ready。
  - warnings 明确写入“`.xls` 内嵌图片未参与语义理解”。
  - 不创建伪 image resource。

建议新增文件：
- backend/app/test_cases/xls_converter.py
- backend/tests/test_source_evidence_xls_converter.py

建议修改文件：
- backend/app/test_cases/excel_source_reader.py
- backend/app/test_cases/source_evidence.py
- backend/config.py

必须覆盖：
- fake converter 成功时 `.xls` run 产生文本和 image resources。
- fake converter 失败时 `.xls` run 文本可用、图片 warning 存在、无伪图片。
- 未配置 soffice 时 `.xls` 文本可用、图片 warning 存在。
- converter 命令参数不包含用户可控 executable。
- 转换产物写在 run 目录并会被 TTL 清理覆盖。
- 错误摘要不泄露本地敏感路径或完整命令行。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_xls_converter.py backend/tests/test_source_evidence_excel_reader.py backend/tests/test_source_evidence_local_file.py

完成后追加 PROJECT_RECORD.md；如配置项对部署可见，同步 CHANGELOG.md。
```

## Prompt 4：SVN Source Evidence Root 和 svn_file Reader

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现 `svn_file` Source Evidence。必须使用项目级 SVN 凭据和 `Source Evidence SVN Root`，拉取文件后复用本地文件 reader。不要复用个人 SVN 凭据作为项目级证据来源。

必须先读：
- CONTEXT.md 中 `Source Evidence SVN Root` 和 `Remote SVN Query Root`
- docs/specs/test-case-generation-v2-requirements.md
- docs/specs/test-case-generation-v2-source-evidence.md
- docs/specs/data-sources.md
- backend/app/admin/router.py
- backend/app/admin/schemas.py
- backend/app/models.py
- backend/app/loaders/svn_cache.py
- backend/app/loaders/svn_manager.py
- backend/app/loaders/svn_credentials.py
- backend/app/test_cases/source_evidence.py

目标：
- 为项目配置新增或复用明确的 `Source Evidence SVN Root` 列表；不要把它混同为 `Remote SVN Query Root`。
- `svn_file` 创建请求必须包含 SVN 文件 URL。
- 后端校验 SVN URL：
  - host 命中全局 allowlist。
  - URL 位于项目级 `Source Evidence SVN Root` 内。
  - 后缀属于 V2 支持范围：`.xlsx/.xls/.png/.jpg/.jpeg/.webp`。
- 使用项目级 SVN 凭据拉取文件，落到受控 cache 或 run 临时目录。
- 读取后复用 local reader，生成同样的 `source.md`、resources、manifest、snapshot。
- run manifest 记录 SVN URL、revision 或 last changed rev、文件 hash、读取时间。
- 超出 root、缺凭据、鉴权失败、文件不存在要返回可区分中文错误。

建议新增文件：
- backend/app/test_cases/svn_source_reader.py
- backend/tests/test_source_evidence_svn_file.py
- backend/tests/test_source_evidence_svn_root.py

建议修改文件：
- backend/app/admin/router.py
- backend/app/admin/schemas.py
- backend/app/models.py（如需要新增 root 字段或模型）
- migrations/versions/00xx_source_evidence_svn_roots.py（如需要）
- backend/app/test_cases/source_evidence.py
- backend/app/loaders/svn_cache.py（尽量复用，少改）

必须覆盖：
- root 内 SVN `.xls` 创建 run 成功，并进入本地 reader。
- root 外 SVN URL 被拒绝。
- 缺项目级 SVN 凭据被拒绝。
- host 不在 allowlist 被拒绝。
- SVN `.xls` 转换成功时有 image resources。
- SVN `.xls` 转换失败时文本可用并有 warning。
- API 响应不泄露 SVN 密码、缓存绝对路径或完整命令行。
- `Remote SVN Query Root` 相关配置表查询测试不被误改。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_svn_file.py backend/tests/test_source_evidence_svn_root.py backend/tests/test_svn_cache.py backend/tests/test_svn_manager.py backend/tests/test_admin_feishu_bot.py

完成后追加 PROJECT_RECORD.md；同步 docs/specs/data-sources.md 和 docs/specs/test-case-generation-v2-source-evidence.md 中实际字段名。
```

## Prompt 5：通用 Source Evidence Snapshot 和 Manifest Renderer

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

把 Source Evidence Snapshot 从 Feishu-only renderer 泛化为通用 renderer，确保 feishu/local_file/svn_file 都能输出兼容生成的 PlanningSnapshotResponse。

必须先读：
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/schemas.py
- backend/app/test_cases/feishu_rich_reader.py
- backend/app/test_cases/local_source_reader.py
- backend/app/test_cases/excel_source_reader.py
- backend/tests/test_source_evidence_snapshot.py
- backend/tests/test_source_evidence_generation.py

目标：
- `build_source_evidence_snapshot` 不再直接 `ParsedFeishuSource.model_validate`。
- 定义通用 parsed source payload，至少包含 source_type、doc_type、title、source_units、resources、warnings、raw_manifest。
- Feishu reader 输出可适配通用结构；local/SVN reader 直接输出通用结构。
- snapshot rows 统一包含：来源类型、位置、标题/页签、内容、证据状态。
- Excel 可见 Sheet 的文本/表格进入 snapshot；图片 marker 只作为资源引用，不当作已理解需求事实。
- 独立图片 run 的 snapshot 要明确“无文本主体，需先采纳视觉证据”。
- manifest warnings、resource warnings、reader warnings 必须合并且去重。

建议文件：
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/schemas.py
- backend/app/test_cases/local_source_reader.py
- backend/app/test_cases/feishu_rich_reader.py
- backend/tests/test_source_evidence_snapshot.py
- backend/tests/test_source_evidence_generation.py

必须覆盖：
- Feishu run snapshot 不回到 Feishu-only 路径失败。
- local `.xlsx` snapshot 包含 Sheet 文本和图片待观察 warning。
- local `.xls` 转换失败 snapshot 包含文本和转换 warning。
- svn `.xls` snapshot 包含 SVN 来源摘要和文本。
- 独立图片 snapshot 不允许伪造文本需求。
- snapshot 响应不泄露 local_path、SVN 密码、token、provider response。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_snapshot.py backend/tests/test_source_evidence_generation.py backend/tests/test_source_evidence_local_file.py backend/tests/test_source_evidence_svn_file.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 6：visual validate 和生成/导出强校验

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现 V2 的 `visual validate`。目标是让任何图片内容只有被提取、观察、人工采纳并通过校验后，才允许影响生成和导出。

必须先读：
- docs/specs/test-case-generation-v2-requirements.md
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/visual_evidence.py
- backend/app/test_cases/generation.py
- backend/app/test_cases/exporter.py
- backend/tests/test_source_evidence_generation.py
- backend/tests/test_source_evidence_observations.py
- backend/tests/test_test_case_exporter.py

目标：
- 新增或硬化 `validate_source_evidence_for_generation` / `visual_validate` helper。
- 生成和导出前校验：
  - adopted evidence id 必须存在。
  - 必须属于当前 run 和当前 project。
  - 必须状态为 adopted。
  - run 未过期、未 cleaned。
  - 不允许 prompt 或结果引用未采纳图片 ref。
- warning 条件：
  - 存在未观察图片。
  - 存在图片提取失败。
  - `.xls` 转换失败。
  - Vision AI 未配置或不可用。
- prompt 中只注入 adopted evidence 摘要，不注入 unobserved/unadopted observation。
- 导出说明只包含 adopted evidence 摘要、来源位置、limitations；不包含原图、本地路径、provider response。
- 独立图片 run 没有 adopted evidence 时阻塞生成。

建议文件：
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/visual_evidence.py
- backend/app/test_cases/generation.py
- backend/app/test_cases/exporter.py
- backend/tests/test_source_evidence_generation.py
- backend/tests/test_source_evidence_observations.py
- backend/tests/test_test_case_exporter.py

必须覆盖：
- 有效 adopted evidence 能进入 prompt。
- 已观察未采纳不进入 prompt。
- 撤销采纳后不进入 prompt。
- adopted id 不存在/跨项目/非当前 run 时阻塞。
- 独立图片 run 无 adopted evidence 时阻塞。
- 未观察图片只产生 warning，不阻塞文本工作簿生成。
- 导出不包含 `images/`、`visual_evidence/images`、local_path、provider response。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_generation.py backend/tests/test_source_evidence_observations.py backend/tests/test_test_case_exporter.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 7：前端 V2 三入口统一 Source Evidence

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

把前端用例生成页的“本地文件 / SVN 文件 / 飞书文档”三入口统一到 Source Evidence Run。不要让本地/SVN V2 继续走旧 uploaded_excel/planning-snapshot。

必须先读：
- docs/specs/test-case-generation-v2-requirements.md
- docs/specs/test-case-generation-v2-source-evidence.md
- frontend/src/views/TestCaseGeneratorView.vue
- frontend/src/api/testCases.ts
- frontend/src/types/testCases.ts
- frontend/tests/unit/TestCaseGeneratorView.test.ts
- frontend/tests/unit/testCasesApi.test.ts

目标：
- `SourceEvidenceRunCreateRequest.source_type` 支持 `feishu | svn_file`。
- 新增本地上传 API 封装：`createLocalFileSourceEvidenceRun` 或等价函数。
- 本地文件入口上传 `.xlsx/.xls/.png/.jpg/.jpeg/.webp` 后创建 `local_file` run。
- SVN 文件入口提交 SVN URL 后创建 `svn_file` run。
- 飞书文档入口继续创建 `feishu` run。
- 三入口创建 run 后复用同一套状态卡、warnings、TTL、资源清单、视觉候选、observation、采纳/撤销、retry。
- `ActiveGenerationInputKind` 不再把 V2 本地/SVN 当成旧 `local_excel` / `svn` 生成输入；V2 run 统一使用 `source_evidence`。
- 读取快照时，V2 run 走 `readSourceEvidenceSnapshot(run.id)`。
- 切换来源后清空旧 snapshot、adopted evidence、生成结果和导出状态。
- 独立图片 run 在未采纳前禁用生成或给出阻塞提示。
- Vision/soffice 不可用、图片提取失败时 warning 明确显示“图片未参与语义理解”。

建议文件：
- frontend/src/types/testCases.ts
- frontend/src/api/testCases.ts
- frontend/src/views/TestCaseGeneratorView.vue
- frontend/tests/unit/testCasesApi.test.ts
- frontend/tests/unit/TestCaseGeneratorView.test.ts

必须覆盖：
- testCasesApi 覆盖 `source_type: 'svn_file'` 和本地 upload endpoint。
- 本地上传成功后展示 Source Evidence 状态卡。
- SVN URL 创建成功后展示 Source Evidence 状态卡。
- 飞书入口不回退。
- 三入口资源抽屉行为一致。
- 切换来源后旧结果失效。
- 生成请求带 source_evidence_run_id 和 adopted_visual_evidence_ids。
- 没有 adopted evidence 的独立图片 run 不能生成。

必须测试：
cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build

完成后追加 PROJECT_RECORD.md；用户可见行为完成后更新 CHANGELOG.md。
```

## Prompt 8：运行能力状态和管理员配置提示

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

补齐 V2 所需运行能力状态：项目级 SVN 凭据、Source Evidence SVN Root、Vision AI、LibreOffice/soffice。目标是让用户在生成页看到可用性，让管理员知道去哪里配置。

必须先读：
- docs/specs/test-case-generation-v2-requirements.md
- docs/specs/ai-project-credentials.md
- backend/app/admin/router.py
- backend/app/admin/schemas.py
- backend/config.py
- frontend/src/views/TestCaseGeneratorView.vue
- 现有 project AI / vision AI 配置相关前后端文件

目标：
- 后端提供 Source Evidence capability/status 响应，至少包含：
  - svn_credential_configured
  - source_evidence_svn_roots_configured
  - vision_ai_configured
  - soffice_configured
  - soffice_available 或最后一次检测摘要
- 普通成员只看可用/不可用和中文处理建议。
- 管理员可以在后台看到配置入口或测试结果。
- `soffice` 检测不得执行用户传入命令；只使用服务端配置。
- 错误和状态摘要不得泄露密钥、SVN 密码、完整本地敏感路径或完整命令行。
- 前端在 Source Evidence 面板显示运行能力 warning，例如“当前未配置视觉模型，图片不会参与语义理解”。

建议文件：
- backend/app/test_cases/source_evidence_capabilities.py
- backend/app/api/test_cases_api.py
- backend/app/admin/router.py
- backend/app/admin/schemas.py
- backend/config.py
- frontend/src/types/testCases.ts
- frontend/src/api/testCases.ts
- frontend/src/views/TestCaseGeneratorView.vue
- backend/tests/test_source_evidence_capabilities.py
- frontend/tests/unit/TestCaseGeneratorView.test.ts

必须覆盖：
- 未配置 soffice 时 status 可见但不泄露路径。
- 未配置 Vision 时不阻断文本/表格读取。
- 普通成员不能触发管理员测试连接。
- 管理员可以看到更明确的配置状态。
- 前端基于 status 展示降级提示。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_capabilities.py backend/tests/test_project_vision_ai_config_api.py backend/tests/test_source_evidence_permissions.py

cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build

完成后追加 PROJECT_RECORD.md；同步 docs/specs/ai-project-credentials.md 或 V2 spec 中实际字段。
```

## Prompt 9：TTL 清理覆盖本地/SVN 转换产物和图片

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

硬化 Source Evidence TTL 清理，确保本地上传文件、SVN 缓存副本、`.xls` 转换产物、图片、视觉包和 observation 详情都按 V2 规则清理。

必须先读：
- backend/app/test_cases/source_evidence_cleanup.py
- backend/app/test_cases/source_evidence_storage.py
- backend/app/services/runtime_cleanup.py
- backend/tests/test_source_evidence_cleanup.py
- backend/tests/test_runtime_cleanup.py

目标：
- TTL 到期删除 run 目录中的：
  - source.md
  - raw/
  - raw/converted/
  - images/
  - attachments/
  - visual_evidence/
  - observation detail
  - adopted evidence 可复查详情
- 清理后保留最小审计元数据：run id、project id、source_type、source_identifier、资源文件名、状态、操作人、创建时间、清理时间、最小错误摘要。
- API 访问过期 run/resources/snapshot/visual 时触发懒清理。
- 清理路径必须严格限制在 `source_evidence_dir/<project_id>/<run_id>` 内。
- 不删除参考案例库、普通上传缓存、SVN 全局 cache 中仍被其他功能使用的文件，除非它们被复制进 run 目录。
- cleaned run 的 API 响应不返回 local_path、converted path、image path、observation detail。

建议文件：
- backend/app/test_cases/source_evidence_cleanup.py
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/source_evidence_storage.py
- backend/app/services/runtime_cleanup.py
- backend/tests/test_source_evidence_cleanup.py
- backend/tests/test_runtime_cleanup.py

必须覆盖：
- local_file run 清理删除上传源文件和图片。
- `.xls` run 清理删除 `raw/converted/source.xlsx`。
- svn_file run 清理删除 run 内副本，但不越界删全局 svn cache。
- visual_evidence/images 和 observations detail 被删除。
- cleaned run 不返回敏感详情。
- lazy cleanup 生效。
- 项目管理员 cleanup audit summary 可见，普通成员不能看项目级列表。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_cleanup.py backend/tests/test_runtime_cleanup.py backend/tests/test_source_evidence_permissions.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 10：V2 自动化和真实样例全链路验收

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

对用例生成 V2 Source Evidence 做全链路验收和文档同步。不要新增新功能；只修复验收发现的缺陷。

必须准备或确认样例：
- 本地 `.xlsx`：含文本、可见 Sheet、至少 2 张内嵌图片、1 个隐藏 Sheet。
- 本地 `.xls`：含文本和内嵌图片。
- SVN `.xls`：位于 `Source Evidence SVN Root` 内，含文本和内嵌图片。
- 独立图片：`.png` 或 `.jpg`。
- 飞书文档：含正文、表格、图片。
- 异常场景：未配置 Vision、未配置 soffice、超出 SVN root。

必须检查：
- `local_file .xlsx` 创建 run 后 ready，文本、可见 Sheet 和图片 resources 正确。
- `local_file .xls` 触发转换，文本和图片 resources 正确。
- soffice 未配置或转换失败时，`.xls` 文本可用，图片 warning 明确，图片不进 prompt。
- `svn_file .xls` root 校验、项目级 SVN 凭据、缓存、reader 复用都正确。
- root 外 SVN URL 被拒绝。
- 独立图片 run 无 adopted evidence 时不能生成。
- 图片候选、选择、observation、采纳、撤销全通。
- `visual validate` 阻塞无效 adopted id、跨 run evidence、未采纳图片 ref。
- 只有 adopted evidence 进入 prompt 和导出说明。
- TTL 清理删除原文、图片、转换产物、视觉包和 observation 详情。
- 前端三入口都展示同一套 Source Evidence 状态和资源抽屉。
- 错误、日志、页面和导出不泄露 API Key、SVN 密码、Feishu token、本地敏感路径、provider response。

建议后端测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_api.py backend/tests/test_source_evidence_snapshot.py backend/tests/test_source_evidence_local_file.py backend/tests/test_source_evidence_excel_reader.py backend/tests/test_source_evidence_xls_converter.py backend/tests/test_source_evidence_svn_file.py backend/tests/test_source_evidence_svn_root.py backend/tests/test_source_evidence_visual_candidates.py backend/tests/test_source_evidence_observations.py backend/tests/test_source_evidence_generation.py backend/tests/test_source_evidence_cleanup.py backend/tests/test_runtime_cleanup.py backend/tests/test_test_case_exporter.py backend/tests/test_alembic_migrations.py

建议前端测试：
cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build

真实环境验收：
- 用真实 LibreOffice/soffice 跑一次本地 `.xls` 图片提取。
- 用项目级 SVN 凭据跑一次 SVN `.xls` 图片提取。
- 用真实 Vision AI 跑一次 observation + adoption + generation + export。

文档同步：
- 如果接口、字段、状态或配置项和文档不同，同步 docs/specs/test-case-generation-v2-requirements.md。
- 同步 docs/specs/test-case-generation-v2-source-evidence.md。
- 如 SVN root 配置落点变化，同步 CONTEXT.md 的术语或 data-sources spec。
- 更新 PROJECT_RECORD.md。
- 用户可见行为完成后更新 CHANGELOG.md。

最终输出：
1. 自动化测试命令和结果。
2. 真实样例验收结果。
3. 仍未覆盖的风险。
4. 需要用户配置或提供样例的事项。
```
