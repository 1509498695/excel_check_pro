# Source Evidence Sheet-Scoped Snapshot Implementation Prompts

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make workbook Source Evidence runs support sheet selection, generate snapshots from one selected planning sheet, and default-select all current-sheet images for visual observation.

**Architecture:** Keep `Source Evidence Run` as the whole-source read/audit session. Add a sheet-scoped boundary at snapshot, visual selection, generation, and export so one test case generation is based on one `Planning Sheet`.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, pytest, Vue 3, TypeScript, Vitest, Element Plus.

---

## Execution Rules

- Do not reintroduce V1 `uploaded_excel/planning-snapshot` for new local/SVN workbook reads.
- Do not parse only one sheet at Source Evidence run creation; runs must keep the full visible-sheet inventory.
- Do not treat selected images as requirements. Default image selection only prepares observation; only `Adopted Visual Evidence` may become generation evidence.
- Do not delete adopted visual evidence on sheet switch. Filter and validate by selected sheet at generation/export time.
- Do not revert unrelated dirty-worktree changes. Read affected files before editing.
- After each prompt, run the listed tests and append `PROJECT_RECORD.md`; update `CHANGELOG.md` only when user-visible behavior changes.

## Source Documents

Always read these before starting a prompt:

- `CONTEXT.md`
- `docs/superpowers/specs/2026-07-02-source-evidence-sheet-scoped-snapshot-design.md`
- `docs/specs/test-case-generation-v2-source-evidence.md`
- `docs/specs/test-case-generation-v2-requirements.md`
- `docs/adr/0002-generalize-source-evidence-for-test-case-generation-v2.md`

## Prompt 0: Baseline And Worktree Audit

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

为“Source Evidence 按 Sheet 读取快照”做基线检查；这一刀不要改业务代码。

必须读取：
- CONTEXT.md
- docs/superpowers/specs/2026-07-02-source-evidence-sheet-scoped-snapshot-design.md
- docs/specs/test-case-generation-v2-source-evidence.md
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/visual_evidence.py
- backend/app/test_cases/schemas.py
- backend/app/api/test_cases_api.py
- frontend/src/views/TestCaseGeneratorView.vue
- frontend/src/api/testCases.ts
- frontend/src/types/testCases.ts
- backend/tests/test_source_evidence_snapshot.py
- frontend/tests/unit/TestCaseGeneratorView.test.ts

请输出：
1. 当前 Source Evidence Run 如何保存 parsed source、sheet units、resources 和 warnings。
2. 当前 snapshot API 为什么只能整 run 输出，缺少哪些 sheet_name 契约。
3. 当前 visual candidates / visual selections 是否有 sheet 信息，默认选中逻辑在哪里。
4. 当前 generation/export 能否从 planning_snapshot.sheet_name 推导所选 Sheet。
5. 需要新增/修改的后端文件、前端文件和测试文件。
6. dirty worktree 中哪些相关文件已有改动，后续不能回滚。
7. 推荐下一刀的最小实现边界和测试命令。
```

## Prompt 1: Backend Contract For Sheet Options And Snapshot Request

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现后端契约骨架：Source Evidence Run 响应暴露可选 Sheet 摘要，snapshot API 接收 sheet_name。先写失败测试，再实现最小代码。

必须读取：
- backend/app/test_cases/schemas.py
- backend/app/test_cases/source_evidence.py
- backend/app/api/test_cases_api.py
- backend/tests/test_source_evidence_api.py
- backend/tests/test_source_evidence_snapshot.py

目标：
- 新增 `SourceEvidenceSheetOption`，字段至少包含 `name`、`kind`、`cell_count`、`resource_count`、`is_default`。
- `SourceEvidenceRunResponse` 增加 `sheet_options: list[SourceEvidenceSheetOption]`，只暴露可见/可用 sheet。
- 从 `raw/parsed_source.json` 的 `ParsedSourceUnit(kind="sheet")` 构造 sheet options。
- 默认 sheet 是第一个可见 sheet；如果没有 sheet units，则 `sheet_options` 为空。
- 新增 `SourceEvidenceSnapshotRequest`，字段为 `sheet_name: str | None = None`。
- `POST /api/v1/test-cases/source-evidence-runs/{run_id}/snapshot` 接收可选 JSON body，并把 `sheet_name` 传入 service。
- 多 sheet workbook 缺少 `sheet_name` 时返回 400；单 sheet workbook 可默认使用唯一 sheet；非 sheet source 兼容旧行为。
- 不改变旧 `/api/v1/test-cases/planning-snapshot`。

必须覆盖：
- 多 sheet parsed source 的 run response 返回两个 sheet options，第一个 `is_default=true`。
- 单 sheet parsed source 不传 body 也能 snapshot。
- 多 sheet parsed source 不传 `sheet_name` 返回 400。
- 非 sheet docx/wiki source 不传 `sheet_name` 仍走现有 snapshot 行为。
- 未知 sheet_name 返回 400，错误信息包含“Sheet 不存在”或同等中文说明。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_api.py backend/tests/test_source_evidence_snapshot.py -q

完成后追加 PROJECT_RECORD.md。
```

## Prompt 2: Sheet-Scoped Snapshot Renderer

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现 sheet-scoped snapshot renderer。Source Evidence Run 仍保留全量 parsed source；PlanningSnapshotResponse 只包含所选 Sheet 的文本、表格和图片资源行。

必须读取：
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/schemas.py
- backend/app/test_cases/excel_source_reader.py
- backend/tests/test_source_evidence_snapshot.py
- backend/tests/test_source_evidence_excel_reader.py

目标：
- `build_source_evidence_snapshot` 接受 `sheet_name`。
- 对 `ParsedSourceUnit(kind="sheet")` 按 `unit.title == sheet_name` 过滤。
- `PlanningSnapshotResponse.sheet_name` 设置为所选 Sheet 名。
- snapshot rows 只包含所选 Sheet 的 cell rows，`evidence_status=table`。
- resources 按 metadata `sheet` / `sheet_index` 优先过滤到所选 Sheet；position 解析仅作兜底。
- 所选 Sheet 图片作为 `pending_visual` rows 进入 snapshot；其他 Sheet 图片不进入。
- 隐藏 Sheet 已在 reader 阶段排除；如果用户请求隐藏 Sheet 名，按未知/不可用 Sheet 处理并返回 400。
- 空 Sheet 返回 warning，不抛 500。
- snapshot 响应不得泄露 local_path、SVN 密码、Feishu token、provider response。

必须覆盖：
- 多 sheet `.xlsx`：选择 `需求A` 时只含 `需求A` 文本和图片。
- 选择 `需求B` 时输出不同 rows。
- 其他 Sheet 图片不会出现在 `pending_visual` rows。
- 空 Sheet 返回 warning。
- snapshot columns 仍为 `来源类型, 位置, 标题/页签, 内容, 证据状态`。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_snapshot.py backend/tests/test_source_evidence_excel_reader.py -q

完成后追加 PROJECT_RECORD.md。
```

## Prompt 3: Sheet-Scoped Visual Candidate Defaults

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

让视觉候选支持 selected sheet 语义：当前 Sheet 的所有图片默认选中，用户仍可手动调整。默认选中不等于自动采纳。

必须读取：
- backend/app/test_cases/visual_evidence.py
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/schemas.py
- backend/app/api/test_cases_api.py
- backend/tests/test_source_evidence_visual_candidates.py
- backend/tests/test_source_evidence_observations.py

目标：
- `GET /source-evidence-runs/{run_id}/visual-candidates` 支持 `sheet_name` query 参数。
- 如果传入 `sheet_name`，候选响应中当前 Sheet 的 image resources 默认 `selected=true`，`selected_refs` 包含当前 Sheet 全部图片 ref。
- 非当前 Sheet 图片仍可在 items 中展示，但默认不选中；如果现有 UI 更适合只展示当前 Sheet，也必须保留可手动选择跨 Sheet 资源的能力。
- `POST /visual-selections` 继续保存用户选择，不自动采纳。
- 如果用户已经手动保存过选择，同一 Sheet 内再次打开候选时保留用户选择；切换 Sheet 的默认重置由前端触发。
- observation 只观察 `selected_refs`。
- warning 文案明确“未采纳资源不作为需求事实”。

必须覆盖：
- 当前 Sheet 有 2 张图片时，visual candidates 默认 `selected_refs` 含 2 个 ref。
- 其他 Sheet 图片不在默认 selected_refs。
- 用户保存自定义 selected_refs 后，再查候选保留自定义选择。
- 未采纳 selected 图片不进入 adopted evidence。
- docx/wiki 或独立图片不传 sheet_name 时保持现有行为。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_visual_candidates.py backend/tests/test_source_evidence_observations.py -q

完成后追加 PROJECT_RECORD.md。
```

## Prompt 4: Sheet-Scoped Generation And Export Validation

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

硬化 generation/export 的 Sheet 范围校验：只允许当前 Planning Sheet 范围内的 adopted visual evidence 进入生成和导出。

必须读取：
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/visual_evidence.py
- backend/app/test_cases/generation.py
- backend/app/test_cases/exporter.py
- backend/tests/test_source_evidence_generation.py
- backend/tests/test_test_case_exporter.py

目标：
- `build_source_evidence_safe_context` 从 `planning_snapshot.sheet_name` 获取当前 Sheet。
- `validate_source_evidence_for_generation` 增加 sheet-scope 校验。
- adopted evidence 必须属于当前 run、当前 project、状态 adopted、未过期/未撤销，且 resource 位于 `planning_snapshot.sheet_name`。
- 跨 Sheet adopted evidence 不删除，但本次 generation/export 必须拒绝或过滤；推荐阻塞并返回中文错误，避免静默错用。
- prompt_context 只说明当前 Sheet 范围，不再说整 workbook 全部 sheet 都是需求范围。
- export summary 写明当前 Sheet 名、图片参与情况和 adopted evidence 摘要。
- 未观察、未采纳、跨 Sheet、未选中的资源只能作为 warning/open question/remarks。

必须覆盖：
- 当前 Sheet adopted evidence 可进入 prompt。
- 另一 Sheet adopted evidence 传入 generation 时被阻塞。
- 撤销 adopted 后被阻塞。
- 未观察图片只产生 warning，不阻塞纯文本工作簿生成。
- 导出 summary 不包含跨 Sheet adopted evidence。
- 导出不泄露 local_path、provider response、图片原始路径。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_generation.py backend/tests/test_test_case_exporter.py -q

完成后追加 PROJECT_RECORD.md。
```

## Prompt 5: Frontend Sheet Selector And Snapshot API Wiring

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

接前端：Source Evidence workbook run 显示 Sheet 下拉，默认第一张 Sheet；读取快照时传 sheet_name；切换 Sheet 后清空旧快照、AI 整理稿、生成结果和导出状态。

必须读取：
- frontend/src/types/testCases.ts
- frontend/src/api/testCases.ts
- frontend/src/views/TestCaseGeneratorView.vue
- frontend/tests/unit/testCasesApi.test.ts
- frontend/tests/unit/TestCaseGeneratorView.test.ts

目标：
- 类型增加 `SourceEvidenceSheetOption` 和 `sheet_options`。
- `readSourceEvidenceSnapshot(runId, payload?)` 支持 `{ sheet_name }` body。
- Source Evidence run 有 `sheet_options.length > 0` 时，`shouldShowPlanningSheetSelector` 为 true。
- 默认选中 `sheet_options.find(is_default)`，否则第一项。
- 本地 `.xlsx/.xls`、SVN `.xlsx/.xls`、飞书 sheets 显示 Sheet selector；飞书 docx/wiki、独立图片不显示。
- 点击“读取快照”传当前 `selectedPlanningSheetName`。
- 切换 Sheet 清空 `planningSnapshot`、`snapshotBriefMarkdown`、`generationResult`、`sourceEvidenceSnapshotRunId`、export readiness。
- 切换 Sheet 后重新拉 visual candidates，并让当前 Sheet 图片默认全选。
- 资源抽屉继续允许用户手动调整 selection。

必须覆盖：
- API 单测验证 snapshot body 带 `sheet_name`。
- 多 Sheet run 默认选择第一张。
- 切换 Sheet 后旧生成结果消失，生成按钮要求重新读取快照。
- docx/wiki run 不显示 Sheet selector。
- 当前 Sheet 图片候选默认选中。
- 用户手动取消图片后不会立即被重新默认选中，直到切换 Sheet。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build

完成后追加 PROJECT_RECORD.md；同步 CHANGELOG.md，因为这是用户可见行为。
```

## Prompt 6: Documentation Sync

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

同步文档，确保 V2 Source Evidence 不再写成“Source Evidence snapshot 读取全部可见 Sheet”。这一刀只改文档，不改代码。

必须读取：
- CONTEXT.md
- docs/superpowers/specs/2026-07-02-source-evidence-sheet-scoped-snapshot-design.md
- docs/specs/test-case-generation-v2-source-evidence.md
- docs/specs/test-case-generation-v2-requirements.md
- docs/specs/test-case-generation.md
- CHANGELOG.md
- PROJECT_RECORD.md

目标：
- `CONTEXT.md` 保持 `Planning Sheet` 是单个 worksheet，包含该 Sheet 文本/表格/视觉资源。
- `docs/specs/test-case-generation-v2-source-evidence.md` 更新工作簿读取规则：run 全量读取，snapshot/generation 按选中 Sheet。
- 删除或改写“Source Evidence 不提供 Sheet 下拉筛选 / snapshot 读取全集”的旧描述。
- 明确当前 Sheet 图片默认读取并默认选中为 observation candidates，但不是自动采纳。
- `docs/specs/test-case-generation-v2-requirements.md` 同步前端需求、API 需求和验收标准。
- `CHANGELOG.md` 增加用户可见变更摘要。
- `PROJECT_RECORD.md` 记录本轮文档同步和测试/未测试情况。

建议验证：
cd D:\project\excel-checkers\excel_check_pro
rg -n "不提供 Sheet|全集|所有可见 Sheet|Sheet 下拉|默认观察全部图片" docs CONTEXT.md CHANGELOG.md PROJECT_RECORD.md
git diff --check -- CONTEXT.md docs/specs/test-case-generation-v2-source-evidence.md docs/specs/test-case-generation-v2-requirements.md CHANGELOG.md PROJECT_RECORD.md
```

## Prompt 7: Full Verification And Risk Report

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

对 Sheet-scoped Source Evidence 做最终验收。不要新增新功能；只修复验收发现的缺陷。

必须验证：
- 多 Sheet `.xlsx`：默认第一张 Sheet；读取快照只含当前 Sheet 文本和图片 pending_visual 行。
- 切换 Sheet 后快照、AI 整理稿、生成结果、导出状态失效。
- 当前 Sheet 所有图片默认选中为 visual observation candidates。
- 用户手动取消图片后不会参与 observation。
- 当前 Sheet adopted visual evidence 能进入生成和导出。
- 跨 Sheet adopted visual evidence 不能进入本次生成和导出。
- 飞书 docx/wiki、独立图片不显示 Sheet selector。
- 隐藏 Sheet 不可选，只产生 warning。
- 超大 Sheet 仍按预算截断并 warning。
- 页面/API/导出不泄露 token、SVN 密码、本地路径、provider response。

后端测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_source_evidence_api.py backend/tests/test_source_evidence_snapshot.py backend/tests/test_source_evidence_visual_candidates.py backend/tests/test_source_evidence_generation.py backend/tests/test_test_case_exporter.py backend/tests/test_source_evidence_excel_reader.py

前端测试：
cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build

最终输出：
1. 自动化测试命令和结果。
2. 手工验收结果，如未做真实样例验收，明确说明。
3. 未覆盖风险。
4. 涉及的提交列表或待提交文件列表。
```
