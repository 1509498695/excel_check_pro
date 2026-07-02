# Test Case Generation V3 Full Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old synchronous test case generation flow with short-lived asynchronous full-generation runs that read the complete selected planning sheet, extract requirement atoms, generate cases in batches, and prove coverage through an audit.

**Architecture:** Keep `Source Evidence Run` as the short-lived source reading session. Add `Generation Run` as the short-lived generation workflow that builds `Full Planning Sheet Context`, chunks it, extracts `Requirement Atom` records, generates blueprint/cases, runs `Coverage Audit`, and exports by run id.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, Alembic, pytest, Vue 3, TypeScript, Vitest, Element Plus, existing project AI provider adapter.

---

## Execution Rules

- Do not keep the old synchronous `/test-cases/generate` flow as the frontend primary path.
- Do not rely on `PlanningSnapshotLimits` or `GENERATION_SNAPSHOT_MAX_CHARS` for V3 completeness.
- Do not store raw prompts, full provider responses, API keys, Feishu tokens, SVN passwords, local sensitive paths, or unadopted visual observation details.
- Do not let reference test cases create requirements. Reference cases may only shape fields, naming, hierarchy, granularity, and export order.
- Do not let unobserved, observed-but-not-adopted, revoked, expired, or cross-sheet visual resources become requirement atoms.
- Do not build Project QA Knowledge Library in this V3 slice.
- Do not auto-classify and merge every visible workbook sheet. V3 scope is the currently selected `Planning Sheet`.
- Do not revert unrelated dirty-worktree changes. Read affected files before editing.
- After each implementation prompt, run the listed tests and append `PROJECT_RECORD.md`; update `CHANGELOG.md` when user-visible behavior changes.
- Commit after each prompt with only the files touched for that prompt.

## Source Documents

Always read these before starting a prompt:

- `CONTEXT.md`
- `docs/adr/0003-replace-synchronous-test-case-generation-with-full-generation-runs.md`
- `docs/superpowers/specs/2026-07-02-test-case-generation-v3-full-generation-design.md`
- `docs/specs/test-case-generation.md`
- `docs/specs/test-case-generation-v2-source-evidence.md`
- `docs/specs/test-case-generation-v2-requirements.md`

## Prompt 0: Baseline And Scope Audit

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

为“用例生成 V3 全量异步生成”做基线审计；这一刀不要改业务代码。

必须读取：
- CONTEXT.md
- docs/adr/0003-replace-synchronous-test-case-generation-with-full-generation-runs.md
- docs/superpowers/specs/2026-07-02-test-case-generation-v3-full-generation-design.md
- backend/app/test_cases/generation.py
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/visual_evidence.py
- backend/app/test_cases/exporter.py
- backend/app/test_cases/schemas.py
- backend/app/api/test_cases_api.py
- backend/app/models.py
- frontend/src/views/TestCaseGeneratorView.vue
- frontend/src/api/testCases.ts
- frontend/src/types/testCases.ts
- backend/tests/test_test_case_generation.py
- backend/tests/test_source_evidence_generation.py
- backend/tests/test_test_case_exporter.py
- frontend/tests/unit/TestCaseGeneratorView.test.ts
- frontend/tests/unit/testCasesApi.test.ts

请输出：
1. 当前同步 generate/export 主链路的入口、请求/响应、状态管理和导出方式。
2. 当前两层截断限制：PlanningSnapshotLimits 和 generation prompt rendering。
3. 当前 Source Evidence safe context 如何按 sheet 和 adopted evidence 校验。
4. V3 需要新增的后端表、服务、API、测试文件和前端状态。
5. 哪些旧接口可以删除、改成 410，或保留但不再由前端调用。
6. dirty worktree 中哪些相关文件已有改动，后续不能回滚。
7. 推荐的第一刀实现范围和测试命令。
```

## Prompt 1: Persistence Model And API Contracts

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现 V3 Generation Run 的数据模型、Pydantic 契约和 API 骨架。先写失败测试，再实现最小代码；这一刀不调用 AI，不生成真实用例。

必须读取：
- backend/app/models.py
- backend/app/test_cases/schemas.py
- backend/app/api/test_cases_api.py
- backend/tests/test_test_case_api_contracts.py
- backend/tests/test_alembic_migrations.py
- migrations/versions/0015_source_evidence_svn_roots.py

目标：
- 新增 Alembic migration，创建：
  - `test_case_generation_runs`
  - `test_case_generation_chunks`
  - `test_case_requirement_atoms`
  - `test_case_generation_cases`
  - `test_case_coverage_audits`
- 在 `backend/app/models.py` 增加 ORM records。
- 在 `schemas.py` 增加 V3 请求/响应模型。
- Generation run 状态枚举固定为：
  `queued, reading, chunking, extracting_atoms, merging_atoms, blueprinting, generating_cases, auditing_coverage, supplementing, completed, partial_completed, failed, cancelled, expired`。
- 新增 API 骨架：
  - `POST /api/v1/test-cases/generation-runs`
  - `GET /api/v1/test-cases/generation-runs/{run_id}`
  - `POST /api/v1/test-cases/generation-runs/{run_id}/cancel`
  - `POST /api/v1/test-cases/generation-runs/{run_id}/retry-failed-chunks`
  - `GET /api/v1/test-cases/generation-runs/{run_id}/atoms`
  - `GET /api/v1/test-cases/generation-runs/{run_id}/cases`
  - `POST /api/v1/test-cases/generation-runs/{run_id}/export`
- API 骨架必须做严格项目成员校验、跨项目隔离、TTL/expired 基础判断。
- `POST /generation-runs` 接收 `source_evidence_run_id`、`planning_sheet_name`、`reference_ids`、`primary_reference_id`、`primary_reference_sheet_name`、`strict_mode`。
- 旧同步 `/generate` 不作为 V3 主路径；如果保留路由，返回 410 或明确说明该入口不支持 V3 全量生成。
- 不保存 raw prompt / raw response 字段。

必须覆盖：
- Alembic upgrade/downgrade 包含新增表和索引。
- 创建 run 返回 `queued`，项目和用户字段正确。
- 非项目成员不能读取或取消 run。
- 跨项目 run 返回 404 或 403。
- cancel 将可取消状态转为 `cancelled`。
- completed/failed/expired run 不允许 cancel。
- atoms/cases/export endpoint 对无结果 run 返回明确中文错误。
- 旧 `/generate` 不再被测试视为 V3 主路径。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_api_contracts.py backend/tests/test_alembic_migrations.py -q

完成后追加 PROJECT_RECORD.md。
```

## Prompt 2: Generation Run Service And TTL Cleanup

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现 Generation Run 服务层和 TTL 清理骨架。目标是让 run 能创建、读取、推进状态、取消、过期和清理详细内容；这一刀不接 AI。

必须读取：
- backend/app/test_cases/source_evidence_cleanup.py
- backend/app/test_cases/source_evidence.py
- backend/app/services/runtime_cleanup.py
- backend/app/test_cases/schemas.py
- backend/app/models.py
- backend/tests/test_source_evidence_cleanup.py
- backend/tests/test_runtime_cleanup.py

建议新增：
- backend/app/test_cases/generation_runs.py
- backend/tests/test_test_case_generation_runs.py

目标：
- 新增 service helper：
  - `create_generation_run`
  - `get_project_generation_run`
  - `cancel_generation_run`
  - `mark_generation_run_expired_if_needed`
  - `cleanup_expired_generation_runs`
  - `update_generation_run_stage`
- TTL 默认 7 天，和 Source Evidence 默认 TTL 对齐。
- 详细数据清理包括 chunks、atoms、cases、coverage audit detail、sanitized stage payload。
- 清理后保留最小审计字段：run id、project id、source evidence run id、planning sheet name、status、counts、created by、created at、completed at、expired at。
- API 访问过期 run 时执行懒清理。
- cancelled run 保留已完成 chunk/atom 到 TTL，但不能导出为 complete result。
- cleanup 路径不能删除 Source Evidence 文件；Generation Run 清理只处理自身 DB 详细内容。

必须覆盖：
- run TTL 到期后访问会变为 `expired`。
- expired run 不返回 atoms/cases 详情。
- cleanup 删除 atoms/cases/audit detail，但保留最小审计。
- cancelled run 不允许继续推进到 completed。
- failed run 保留错误摘要但不保存 raw response。
- cleanup 不影响 source evidence cleanup audit。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_generation_runs.py backend/tests/test_runtime_cleanup.py backend/tests/test_source_evidence_cleanup.py -q

完成后追加 PROJECT_RECORD.md。
```

## Prompt 3: Full Planning Sheet Context Builder

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现 Full Planning Sheet Context builder。目标是从当前 selected Planning Sheet 全量读取文本/表格事实和已采纳视觉证据，不使用旧 snapshot 截断限制。

必须读取：
- backend/app/test_cases/source_evidence.py
- backend/app/test_cases/visual_evidence.py
- backend/app/test_cases/generation.py
- backend/app/test_cases/schemas.py
- backend/tests/test_source_evidence_snapshot.py
- backend/tests/test_source_evidence_generation.py

建议新增：
- backend/app/test_cases/full_generation_context.py
- backend/tests/test_test_case_full_generation_context.py

目标：
- 新增 `FullPlanningSheetContext` 内部模型，包含 source summary、sheet name、columns、all fact rows、adopted visual evidence summaries、warnings。
- 从 `source_evidence_run_id + planning_sheet_name` 读取完整 selected sheet。
- 对 workbook/sheets 来源，只读取当前 sheet；不合并其他可见 sheet。
- 对 docx/wiki 等无 sheet 来源，使用兼容 sheet name `Source Evidence` 或 service 现有解析名。
- 不使用 `PlanningSnapshotLimits.max_rows/max_chars/max_cell_chars` 裁剪 V3 输入。
- 保留行号、列号、列名、source unit title、evidence status。
- pending/unobserved/unadopted/revoked/expired/cross-sheet visual resources 不进入 fact，只进入 warnings。
- adopted visual evidence 必须通过当前 project/run/sheet 校验后才能进入 context。
- API 响应和 logs 不泄露 local_path、token、provider response。

必须覆盖：
- 一个超过旧 800 行限制的 sheet，在 context 中保留所有非空行事实。
- 一个超过旧 60000 字符的 sheet，context 不按旧 prompt budget 截断。
- 当前 sheet adopted visual evidence 进入 context。
- 其他 sheet adopted visual evidence 被阻塞。
- 未采纳图片只进入 warning。
- docx/wiki 无 sheet 来源可构造 context。
- 不泄露本地路径或 provider response。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_full_generation_context.py backend/tests/test_source_evidence_generation.py -q

完成后追加 PROJECT_RECORD.md。
```

## Prompt 4: Structural Chunking

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现结构优先的 chunking。目标是把 Full Planning Sheet Context 切成可控 AI 输入，同时保留完整覆盖范围。

必须读取：
- backend/app/test_cases/full_generation_context.py
- docs/superpowers/specs/2026-07-02-test-case-generation-v3-full-generation-design.md
- backend/tests/test_test_case_full_generation_context.py

建议新增：
- backend/app/test_cases/generation_chunking.py
- backend/tests/test_test_case_generation_chunking.py

目标：
- 新增 `GenerationChunk` 内部模型，包含 chunk key、sheet name、row range、column range、title hints、fact count、char count、resource refs、status。
- 结构优先切片：
  - 标题行变化
  - 空行分区
  - 合并单元格区域或 source unit boundary
  - 表头变化
  - fallback 到固定行数窗口
- fallback 行窗口要有重叠边界提示，避免切断连续规则。
- 所有 input facts 必须被某个 chunk 覆盖。
- chunk 记录到 `test_case_generation_chunks`。
- chunking 不调用 AI。

必须覆盖：
- 标题行分区能产生多个 chunk。
- 空行分区能产生多个 chunk。
- 表头变化能产生多个 chunk。
- 无结构信号时 fallback 行窗口覆盖所有事实。
- chunk row ranges 不丢行、不重复计入 coverage 事实。
- 超大 sheet 产生多个 chunk，run status/progress 可更新。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_generation_chunking.py backend/tests/test_test_case_full_generation_context.py -q

完成后追加 PROJECT_RECORD.md。
```

## Prompt 5: Requirement Atom Extraction And Merge

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现 Requirement Atom 抽取和合并。目标是每个 chunk 通过 AI 抽取结构化 atoms，再由后端合并去重；这一刀不生成用例。

必须读取：
- backend/app/test_cases/generation.py
- backend/app/test_cases/qa_case_method.py
- backend/app/ai/providers.py
- backend/app/ai/credentials.py
- backend/app/test_cases/generation_chunking.py
- backend/tests/test_test_case_generation.py

建议新增：
- backend/app/test_cases/requirement_atoms.py
- backend/tests/test_test_case_requirement_atoms.py

目标：
- 定义 atom schema：atom_id、atom_type、text、source_sheet、source_rows、source_columns、source_excerpt、visual_evidence_ids、confidence、warnings、merge_key、is_unfounded_candidate。
- Atom types 至少支持：rule, entry, state, timing, config, reward, role, ui_text, visual_fact, open_question, limitation。
- 每个 chunk 抽取 prompt 必须强调：只能从当前 chunk facts 和已采纳视觉证据抽取；不能从参考案例、常识或旧知识补需求。
- 并发默认最多 2 个 chunk AI 调用。
- provider 返回非法 JSON、缺字段、空 atoms 时，chunk 标记 failed 或 warning，不让整 run 立即崩溃。
- 合并阶段按 merge_key、来源范围和文本相似度去重。
- 冲突解释保留为 warning。
- 无当前来源依据的内容只能标记 unfounded candidate，不能参与 blueprint/cases。
- 不保存 raw prompt/response；只保存 normalized atoms、warnings、sanitized error summary 和 provider meta。

必须覆盖：
- 单 chunk 正常抽取 atoms。
- 多 chunk 重复 atom 被合并。
- provider 返回非法 JSON 时 chunk failed，run 可继续。
- 空 atoms 产生 warning。
- unfounded candidate 不进入 official atom set。
- adopted visual evidence 可形成 visual_fact atom。
- 未采纳图片 ref 出现在 provider 输出时被阻塞或剔除。
- 不保存 raw provider response。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_requirement_atoms.py backend/tests/test_test_case_generation_runs.py -q

完成后追加 PROJECT_RECORD.md。
```

## Prompt 6: Blueprint Generation From Atoms

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现基于 Requirement Atoms 的 Test Case Blueprint 生成。目标是蓝图只从 merged official atoms 生成，不再直接从 Planning Sheet Snapshot 生成。

必须读取：
- backend/app/test_cases/schemas.py
- backend/app/test_cases/generation.py
- backend/app/test_cases/qa_case_method.py
- backend/app/test_cases/requirement_atoms.py
- backend/tests/test_test_case_generation.py

建议新增：
- backend/app/test_cases/full_generation_blueprint.py
- backend/tests/test_test_case_full_generation_blueprint.py

目标：
- 新增 blueprint generation stage：status `blueprinting`。
- prompt 输入为 merged official atoms、QA Case Method 矩阵、source summary 和 warnings。
- prompt 不包含 raw sheet 全文。
- 输出仍使用 `TestCaseBlueprint` 或 V3 扩展 schema，但必须包含 requirement_traces 到 atom ids。
- blueprint warnings 合并到 run warnings。
- 如果 atom set 为空，run 进入 `partial_completed` 或 failed，错误清晰说明没有可生成需求。
- Reference Test Case Library 不参与 blueprint facts。

必须覆盖：
- atoms 能生成 blueprint。
- blueprint traces 包含 atom ids 或 source fragment。
- 空 atom set 不生成空成功结果。
- provider 输出无依据模块时进入 unsupported/unfounded warnings。
- blueprint 不包含未采纳视觉 ref。
- 不保存 raw prompt/response。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_full_generation_blueprint.py backend/tests/test_test_case_requirement_atoms.py -q

完成后追加 PROJECT_RECORD.md。
```

## Prompt 7: Batched Case Generation And Trace Enforcement

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现按 atom group/module 分批生成测试用例，并强制每条正式用例引用至少一个 Requirement Atom。无依据用例默认剔除并写入 Coverage Audit 候选。

必须读取：
- backend/app/test_cases/generation.py
- backend/app/test_cases/exporter.py
- backend/app/test_cases/reference_library.py
- backend/app/test_cases/full_generation_blueprint.py
- backend/app/test_cases/requirement_atoms.py
- backend/tests/test_test_case_generation.py
- backend/tests/test_test_case_reference_library_api.py

建议新增：
- backend/app/test_cases/full_generation_cases.py
- backend/tests/test_test_case_full_generation_cases.py

目标：
- 新增 status `generating_cases`。
- 按 blueprint module 或 atom group 分批生成 cases。
- 每个 case 必须含 atom_ids。
- 如果 provider 返回 case 没有 atom_ids，尝试用 source_requirement 匹配 atom；匹配失败则记录为 unfounded candidate，不进入 official cases。
- 保持 GeneratedTestCase 标准字段，补默认 case_id、priority、initial_status。
- 去重 case_id 和重复标题/步骤。
- Reference Test Case Library 只作为输出格式、字段顺序、粒度和命名风格参考。
- cases 写入 `test_case_generation_cases`，atom refs 用 JSON 或关联表结构保存，按当前项目隔离。
- 不保存 raw prompt/response。

必须覆盖：
- 正常 atom group 生成 official cases。
- 无 atom 支撑的 case 被剔除。
- source_requirement 可匹配 atom 时补 atom_ids。
- 重复 case_id 被稳定改写。
- reference profile 影响 export columns，但不生成新需求。
- provider 返回数组 steps/expected_results 等旧兼容形态仍归一化为字符串。
- 未采纳视觉 ref 出现在 case 输出时被阻塞或剔除。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_full_generation_cases.py backend/tests/test_test_case_reference_library_api.py -q

完成后追加 PROJECT_RECORD.md。
```

## Prompt 8: Coverage Audit And One Supplement Pass

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现 Coverage Audit 和一次自动补生成。目标是证明 atoms 是否被 cases 覆盖，并在有缺口时只补一轮，不无限循环。

必须读取：
- backend/app/test_cases/full_generation_cases.py
- backend/app/test_cases/requirement_atoms.py
- backend/app/test_cases/generation.py
- backend/app/test_cases/schemas.py

建议新增：
- backend/app/test_cases/coverage_audit.py
- backend/tests/test_test_case_coverage_audit.py

目标：
- 新增 status `auditing_coverage` 和 `supplementing`。
- Coverage Audit 输出：
  - total atoms
  - covered atoms
  - uncovered atoms
  - unfounded candidates
  - failed chunks
  - skipped visual resources
  - supplement pass result
  - export limitations
- 一轮 supplement pass 只针对 uncovered official atoms。
- supplement 生成出的 cases 仍必须引用 atom ids。
- supplement 后仍未覆盖则 run `partial_completed`。
- 全部 chunk 成功、无阻塞视觉错误、coverage 完成且无未覆盖 required atoms 才 `completed`。
- strict mode 下存在 uncovered atoms 时 export 阻塞。
- 非 strict mode 允许 export，但页面和导出必须显著提示 partial/coverage gaps。

必须覆盖：
- fully covered atoms -> completed。
- uncovered atoms -> supplement 一轮。
- supplement 后覆盖 -> completed。
- supplement 后仍未覆盖 -> partial_completed。
- failed chunk -> partial_completed。
- strict mode 阻止 export。
- non-strict mode 可 export with warning。
- unfounded candidates 不计为 coverage。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_coverage_audit.py backend/tests/test_test_case_full_generation_cases.py -q

完成后追加 PROJECT_RECORD.md；用户可见行为完成后更新 CHANGELOG.md。
```

## Prompt 9: Orchestrator And API Integration

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

把 V3 各阶段串成 Generation Run orchestrator，并接入 API。第一版可以在请求内启动后台任务或同步执行测试 helper，但 API 语义必须是异步 run。

必须读取：
- backend/app/api/test_cases_api.py
- backend/app/test_cases/generation_runs.py
- backend/app/test_cases/full_generation_context.py
- backend/app/test_cases/generation_chunking.py
- backend/app/test_cases/requirement_atoms.py
- backend/app/test_cases/full_generation_blueprint.py
- backend/app/test_cases/full_generation_cases.py
- backend/app/test_cases/coverage_audit.py
- backend/tests/test_test_case_generation_runs.py

建议新增：
- backend/app/test_cases/full_generation_orchestrator.py
- backend/tests/test_test_case_full_generation_orchestrator.py

目标：
- `POST /generation-runs` 创建 run 并启动 orchestrator。
- Orchestrator 顺序：
  1. reading
  2. chunking
  3. extracting_atoms
  4. merging_atoms
  5. blueprinting
  6. generating_cases
  7. auditing_coverage
  8. supplementing when needed
  9. completed/partial_completed/failed
- 每个阶段更新 progress、counts、warnings。
- cancel request 被 orchestrator 尊重，尽快停止后续阶段。
- retry failed chunks 只重跑 failed chunk extraction，然后重新 merge/blueprint/cases/audit。
- provider/API 错误写 sanitized summary，不写 raw prompt/response。
- project AI 未配置时 run failed，错误清晰。
- source evidence run 不 ready/expired/cleaned 时 run failed 或 create 被拒绝。

必须覆盖：
- happy path 从 queued 到 completed。
- project AI 未配置 -> failed。
- source evidence expired -> rejected/failed。
- cancel during extracting -> cancelled，不继续生成 cases。
- retry failed chunks 后 partial 变 completed。
- progress API 返回 stage counts。
- old `/generate` 不被前端 API 测试依赖。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_full_generation_orchestrator.py backend/tests/test_test_case_generation_runs.py backend/tests/test_source_evidence_generation.py -q

完成后追加 PROJECT_RECORD.md；同步 CHANGELOG.md。
```

## Prompt 10: Export By Generation Run Id

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

改造导出：前端不再回传 blueprint/cases/stats 作为导出事实；后端按 generation run id 读取短期结果并导出 Excel，新增“覆盖审计”Sheet。

必须读取：
- backend/app/test_cases/exporter.py
- backend/app/api/test_cases_api.py
- backend/app/test_cases/generation_runs.py
- backend/app/test_cases/coverage_audit.py
- backend/tests/test_test_case_exporter.py

目标：
- `POST /api/v1/test-cases/generation-runs/{run_id}/export` 从 DB 读取 blueprint/cases/warnings/stats/audit。
- 不再接受前端提交的 generated cases 作为 V3 export truth。
- 导出 Sheet 至少包含：
  - `测试用例`
  - `用例蓝图`
  - `生成说明`
  - `覆盖审计`
- 覆盖审计 Sheet 列：atom id、source sheet、source rows、source columns、atom type、atom text、coverage status、linked case ids、failed chunk、limitation notes。
- strict mode 且 uncovered atoms 存在时，export 返回 409 中文错误。
- partial_completed non-strict 可导出，但生成说明和覆盖审计必须显著标记限制。
- export 不包含 raw prompt、provider response、local path、API key、Feishu/SVN token、未采纳视觉 observation detail。

必须覆盖：
- completed run 可导出四个 Sheet。
- partial_completed non-strict 可导出并带 warnings。
- strict mode uncovered atoms 阻止导出。
- cancelled/failed/expired run 不能导出。
- 前端篡改 cases 不影响导出，因为 API 不接受 cases payload。
- coverage sheet 内容准确。
- 敏感字段不出现在 workbook。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_exporter.py backend/tests/test_test_case_coverage_audit.py -q

完成后追加 PROJECT_RECORD.md；同步 CHANGELOG.md。
```

## Prompt 11: Frontend V3 Generation Run Workflow

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

把前端用例生成页切到 V3 Generation Run 主流程。旧同步 generate/export 不能再作为主路径。

必须读取：
- frontend/src/views/TestCaseGeneratorView.vue
- frontend/src/api/testCases.ts
- frontend/src/types/testCases.ts
- frontend/tests/unit/TestCaseGeneratorView.test.ts
- frontend/tests/unit/testCasesApi.test.ts
- docs/superpowers/specs/2026-07-02-test-case-generation-v3-full-generation-design.md

目标：
- TypeScript 增加 Generation Run、chunk、atom、case、coverage audit 类型。
- API 增加：
  - createGenerationRun
  - getGenerationRun
  - cancelGenerationRun
  - retryFailedGenerationChunks
  - listGenerationRunAtoms
  - listGenerationRunCases
  - exportGenerationRunWorkbook
- 页面主按钮改为“全量生成用例”或等价中文，创建 generation run。
- 展示 stage progress：reading/chunking/extracting/blueprinting/generating/auditing/supplementing。
- 支持 cancel。
- 支持 failed chunk retry。
- 页面刷新后恢复 active/latest short-lived run。
- 结果区展示：测试用例、覆盖审计、限制提示、需求原子明细。
- 导出使用 run id，不再 POST blueprint/cases/stats。
- partial_completed 显著提示未覆盖范围。
- strict mode 可选；开启后 uncovered atoms 阻止导出。
- 旧 snapshot preview 可以保留为来源预览，但文案不能暗示只有预览 rows 参与生成。

必须覆盖：
- create run API payload 包含 source_evidence_run_id、planning_sheet_name、reference selection、strict_mode。
- progress 渲染各 stage。
- cancel 按钮调用 API 并更新状态。
- retry failed chunks 调用 API。
- completed 显示 cases 和 coverage audit。
- partial_completed 显示限制提示。
- export 调用 run id endpoint。
- 页面不会调用旧同步 generate/export 作为主路径。
- refresh 恢复 run。

建议测试命令：
cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build

完成后追加 PROJECT_RECORD.md；同步 CHANGELOG.md。
```

## Prompt 12: Documentation Sync

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

同步 V3 文档。只改文档，不新增功能；确保文档不再描述旧同步 generate 为主链路。

必须读取：
- CONTEXT.md
- docs/adr/0003-replace-synchronous-test-case-generation-with-full-generation-runs.md
- docs/superpowers/specs/2026-07-02-test-case-generation-v3-full-generation-design.md
- docs/specs/test-case-generation.md
- docs/specs/test-case-generation-v2-source-evidence.md
- docs/specs/test-case-generation-v2-requirements.md
- docs/specs/README.md
- CHANGELOG.md
- PROJECT_RECORD.md

目标：
- `docs/specs/test-case-generation.md` 增加 V3 当前方向：Generation Run、Full Planning Sheet Context、Requirement Atom、Coverage Audit、export by run id。
- 标明旧 `Planning Sheet Snapshot` 是受控预览/旧路径概念，不承担 V3 全量生成输入。
- `docs/specs/test-case-generation-v2-source-evidence.md` 保持 Source Evidence 是来源证据，不混同 Generation Run。
- `docs/specs/README.md` 加 V3 设计或实现文档索引。
- `CHANGELOG.md` 记录用户可见方向变化。
- `PROJECT_RECORD.md` 记录文档同步和测试情况。

建议验证：
cd D:\project\excel-checkers\excel_check_pro
rg -n "同步 generate|回传.*cases|PlanningSnapshotLimits|GENERATION_SNAPSHOT_MAX|旧同步" docs CONTEXT.md
git diff --check -- CONTEXT.md docs/specs/test-case-generation.md docs/specs/test-case-generation-v2-source-evidence.md docs/specs/test-case-generation-v2-requirements.md docs/specs/README.md CHANGELOG.md PROJECT_RECORD.md

完成后提交文档改动。
```

## Prompt 13: Full Verification And Release Readiness

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

对 V3 全量异步用例生成做最终验收。不要新增新功能；只修复验收发现的缺陷。

必须验证：
- 超过旧 800 行的 selected Planning Sheet 被 Full Planning Sheet Context 全量读取。
- 超过旧 60000 字符预算的 selected Planning Sheet 不按旧 prompt budget 截断。
- structural chunking 覆盖所有 facts。
- atoms 都有来源行/列/证据。
- 无依据 atom/case 不进入 official output。
- adopted visual evidence 只在当前 sheet 生效。
- unadopted/cross-sheet visual evidence 不进入 atoms/cases/export。
- Coverage Audit 能识别 covered/uncovered/unfounded/failed chunks。
- supplement pass 只执行一轮。
- completed/partial_completed/failed/cancelled/expired 状态准确。
- strict mode export 阻塞 uncovered atoms。
- non-strict partial export 明确提示限制。
- frontend 不再使用旧同步 generate/export 主路径。
- export workbook 包含 `测试用例`、`用例蓝图`、`生成说明`、`覆盖审计`。
- TTL cleanup 删除 generation run 详细 atoms/cases/audit，但保留最小审计。
- 页面/API/export 不泄露 raw prompts、provider responses、API keys、tokens、SVN passwords、local sensitive paths。

建议后端测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_generation_runs.py backend/tests/test_test_case_full_generation_context.py backend/tests/test_test_case_generation_chunking.py backend/tests/test_test_case_requirement_atoms.py backend/tests/test_test_case_full_generation_blueprint.py backend/tests/test_test_case_full_generation_cases.py backend/tests/test_test_case_coverage_audit.py backend/tests/test_test_case_full_generation_orchestrator.py backend/tests/test_test_case_exporter.py backend/tests/test_source_evidence_generation.py backend/tests/test_alembic_migrations.py

建议前端测试：
cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build

真实样例验收：
- 用一个超过旧行数/字符限制的真实策划 Sheet 跑完整 generation run。
- 用包含当前 Sheet adopted image 和其他 Sheet adopted image 的 Source Evidence run 验证 sheet-scope visual validation。
- 用 partial_completed 场景验证导出限制提示。

最终输出：
1. 自动化测试命令和结果。
2. 真实样例验收结果；如果缺少真实样例，明确说明缺口。
3. 未覆盖风险。
4. 本轮提交列表。
5. 是否可以进入发布或还需要用户提供样例/配置。
```
