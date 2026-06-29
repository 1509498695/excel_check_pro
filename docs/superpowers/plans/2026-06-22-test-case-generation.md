# Test Case Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 Excel Check Pro 项目内新增“用例生成”页面和后端能力：项目成员读取单个策划案 Sheet 快照，通过项目级 AI 按 `qa-case` 方法论生成只读蓝图、测试用例和 warnings，并可选使用项目参考案例库增强字段、粒度和历史风格，支持页面预览与 Excel 导出。V1 不保存生成历史、不编辑蓝图、不做图片理解、不写回飞书。

**Architecture:** 后端新增 `test_cases` 领域包，按“参考案例库持久化 + 策划案快照内存化 + AI 生成编排 + Excel 导出”拆分服务；API 统一挂到 `/api/v1/test-cases/*`，鉴权复用当前项目成员/项目管理员依赖；前端新增独立路由 `/test-cases` 和 `TestCaseGeneratorView.vue`，只保留本次页面态和导出动作。

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic, Pydantic, pandas, openpyxl, project-level AI provider abstraction, Vue 3, Vue Router, Element Plus, TypeScript, Vitest, pytest.

---

## Confirmed V1 Decisions

- 页面入口：新增 `/test-cases`，导航名称为“用例生成”。
- 策划案来源：飞书表格 URL 或上传 Excel；每次只选一个 `Planning Sheet`，读取整张 Sheet，不做手动范围选择。
- 快照边界：默认最多 80,000 字符、800 行、80 列、300 字符/单元格、12,000 非空单元格；超出时截断并返回 warnings。
- AI 凭据：只使用项目级 AI 配置，不接受用户临时 API Key。
- 生成协议：内部按“蓝图 → 用例”两段编排；接口一次返回 `blueprint + cases + warnings + stats`。
- 生成主线：以 `qa-case` 方法论为主体，参考案例库是可选增强输入，不是生成前置条件。
- QA 知识库：V1 不做可维护知识库；`QA Case Method` 以内置规则随代码发布，后端仅预留 V2 的 `knowledge_context` 扩展点。
- 蓝图：作为可解释中间结果展示，只读，不作为可编辑输入。
- 统计：总数、优先级、模块分布等由代码计算，不让模型自报。
- 生成历史：V1 不持久化结果、蓝图和策划案快照，只保留页面预览和 Excel 导出。
- Excel 导出：采用“标准字段兜底 + 尽量贴近主参考”的策略，不严格复刻参考文件。
- 图片/附件：V1 不做图片理解；warnings 和备注里明确“未读取图片/附件”。
- 参考案例库权限：项目成员可查看、选择、使用、创建分类、上传；项目管理员和超级管理员可删除参考案例、重命名分类、删除分类、设置推荐主参考。
- 参考文件格式：V1 支持 `.xlsx`、`.xls`、`.md`、`.txt`。

## Contracts

### Backend Response Envelope

所有 JSON API 继续沿用现有风格：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {}
}
```

文件下载接口返回 `StreamingResponse`，前端使用现有 `apiDownloadFile` 保存。

### Core API Paths

- `GET /api/v1/test-cases/reference-categories`
- `POST /api/v1/test-cases/reference-categories`
- `PATCH /api/v1/test-cases/reference-categories/{category_id}`
- `DELETE /api/v1/test-cases/reference-categories/{category_id}`
- `GET /api/v1/test-cases/references`
- `POST /api/v1/test-cases/references`
- `DELETE /api/v1/test-cases/references/{reference_id}`
- `POST /api/v1/test-cases/references/{reference_id}/recommended-primary`
- `POST /api/v1/test-cases/planning-snapshot`
- `POST /api/v1/test-cases/generate`
- `POST /api/v1/test-cases/export`

### Standard Case Fields

导出和页面预览至少覆盖这些标准字段：

- `case_id`
- `module`
- `feature`
- `scenario`
- `title`
- `preconditions`
- `steps`
- `expected_results`
- `priority`
- `case_type`
- `source_requirement`
- `config_source`
- `planning_answer`
- `initial_status`
- `bug_link`
- `remarks`

### Data Model

`test_case_reference_categories`

- `id`
- `project_id`
- `name`
- `created_by`
- `created_at`
- `updated_at`
- Unique: `(project_id, name)`

`test_case_reference_files`

- `id`
- `project_id`
- `category_id`
- `original_filename`
- `storage_path`
- `file_suffix`
- `size_bytes`
- `profile_json`
- `is_recommended_primary`
- `uploaded_by`
- `created_at`
- `updated_at`
- `deleted_at`
- `deleted_by`

分类删除时将关联文件的 `category_id` 置空、`is_recommended_primary` 清空，页面展示为“未分类”。参考文件删除采用软删除，保留审计元数据但列表和生成选择只读 `deleted_at IS NULL` 的记录。
Deleting a reference soft-deletes the row for audit but also deletes the physical file immediately. After deletion, keep only minimal metadata such as original filename, suffix, size, uploader, timestamps, deleter, and deletion timestamp; clear `storage_path`, `profile_json`, and `is_recommended_primary` so the deleted row cannot be reused for generation or export.
If the referenced physical file is already missing during deletion, treat the file deletion step as idempotent success and still soft-delete the row with reusable metadata purged. If the physical file exists but cannot be deleted because of permission or IO errors, abort the delete operation, return a clear retryable admin-facing error, and leave the row active with `storage_path`, `profile_json`, and `is_recommended_primary` unchanged.
V1 不做参考案例覆盖替换；同一项目、同一分类、同一 `original_filename` 的 active 参考文件只能存在一条，软删除后的同名文件允许重新上传。
Reference profile extraction failure is treated as upload failure: delete any saved file and do not commit a reference row. V1 only stores references whose `profile_json` is ready; do not add `profile_status` or `profile_error` fields for failed half-finished references.
For Excel reference files, `ReferenceFileResponse` exposes `sheet_options: Array<{ sheet_name: string; sheet_index: number; is_default: boolean; reference_case_count: int | null }>` and optional `default_sheet_name`; non-Excel references return an empty `sheet_options` list. Store Excel reference profile data per usable sheet, for example under `profile_json.sheet_profiles`, and resolve generation/export behavior from the selected primary reference sheet. A usable sheet is a worksheet with a reliably detected header and at least one recognizable case row.
Excel reference default sheet resolution is backend-owned: prefer usable sheets whose names match `测试用例`, `用例`, then `TestCases`; if none match, use the first usable sheet. If an Excel file can be read but no usable sheet can be identified, treat profile extraction as upload failure. The frontend renders this default as the selected primary reference sheet and lets the user change it before generation.
Reference library storage is project-level server storage, not local user configuration. Do not use `/api/v1/sources/upload` as the reference library endpoint because it returns a user-scoped `selected_path` for data sources and has no category/profile/recommendation lifecycle. Reuse or extract lower-level upload and Excel helpers where practical. Reference files are long-lived project assets, so do not store them in `settings.runtime_upload_dir` unless runtime upload cleanup explicitly excludes the reference library subtree.

## Phase 1: 数据模型/迁移

- [ ] Add ORM models in `backend/app/models.py`.
  - Add `TestCaseReferenceCategoryRecord`.
  - Add `TestCaseReferenceFileRecord`.
  - Use `JSON`/`Text` consistently with existing SQLite-compatible model style; if current models store JSON as `Text`, store `profile_json` as UTF-8 JSON text with `ensure_ascii=False`.
  - Make `storage_path` and `profile_json` nullable if needed so deletion can purge reusable file/profile data while preserving the soft-deleted audit row.
  - Add relationships only when they match nearby model style; service queries can use explicit `select()` to keep scope small.

- [ ] Add Alembic migration `migrations/versions/0010_test_case_reference_library.py`.
  - Create `test_case_reference_categories`.
  - Create `test_case_reference_files`.
  - Create indexes:
    - `ix_test_case_reference_categories_project_id`
    - `ix_test_case_reference_files_project_id`
    - `ix_test_case_reference_files_category_id`
    - `ix_test_case_reference_files_project_deleted`
  - Add unique constraint `uq_test_case_reference_categories_project_name`.
  - On downgrade, drop child table before category table.

- [ ] Add model/migration coverage.
  - Extend `backend/tests/test_alembic_migrations.py` only if it asserts known tables by name.
  - Otherwise add `backend/tests/test_test_case_reference_models.py` to verify:
    - migration creates both tables,
    - duplicate category name in the same project fails after trimming leading and trailing whitespace,
    - same category name in different projects succeeds,
    - soft-deleted reference rows remain queryable by id but are excluded from active list service.

- [ ] Verification command:

```powershell
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_alembic_migrations.py backend/tests/test_test_case_reference_models.py
```

## Phase 2: 参考案例库和画像

- [ ] Create backend package files.
  - `backend/app/test_cases/__init__.py`
  - `backend/app/test_cases/constants.py`
  - `backend/app/test_cases/schemas.py`
  - `backend/app/test_cases/reference_profiles.py`
  - `backend/app/test_cases/reference_library.py`

- [ ] Define constants in `constants.py`.
  - `REFERENCE_ALLOWED_SUFFIXES = {".xlsx", ".xls", ".md", ".txt"}`
  - `REFERENCE_MAX_FILE_BYTES = 20 * 1024 * 1024`
  - `REFERENCE_DEFAULT_SHEET_NAMES = ("测试用例", "用例", "TestCases")`
  - `REFERENCE_STORAGE_ROOT = settings.runtime_dir / "test-case-references"` unless a dedicated setting is added.
  - `STANDARD_CASE_FIELDS` matching the confirmed field list.
  - `DEFAULT_CATEGORY_NAME = "未分类"` for response display only; do not persist an implicit category row.

- [ ] Define Pydantic schemas in `schemas.py`.
  - `ReferenceCategoryCreateRequest`
  - `ReferenceCategoryUpdateRequest`
  - `ReferenceCategoryResponse`
  - `ReferenceFileResponse`
  - `ReferenceSheetOption`
  - `ReferenceListResponse`
  - `ReferenceProfile`
  - `ReferenceProfileColumn`
  - `ReferenceProfileHierarchy`
  - `ReferenceProfileGranularity`
  - Use explicit Chinese validation messages where existing APIs do so; otherwise let FastAPI produce 422 for malformed payloads.

- [ ] Implement deterministic profile extraction in `reference_profiles.py`.
  - Excel:
    - Read workbook sheet metadata and evaluate every non-empty worksheet as a candidate.
    - A usable worksheet must have a reliably detected header row and at least one recognizable case row; only usable worksheets are exposed in `sheet_options`.
    - Mark one worksheet as `is_default=true` and expose it as `default_sheet_name`: choose the first usable worksheet whose name matches `测试用例`, then `用例`, then `TestCases`; if none match, choose the first usable worksheet.
    - For each candidate worksheet, detect header row from the first 20 rows by maximum non-empty cells and recognizable standard field aliases.
    - If no usable worksheet remains after header and case-row detection, raise a profile extraction error so upload is rejected.
    - Compute per-sheet `reference_case_count` from rows after the detected header; count rows containing any recognized case-content field such as title, checkpoint, step, or expected result.
    - Treat module/feature/scenario columns as hierarchy signals only: a row with only hierarchy cells and no case-content cells is a grouping row and must not increment `reference_case_count`.
    - Exclude fully empty rows, pure grouping rows, note/description-only rows, rows with only remarks, and total/summary rows from `reference_case_count`.
    - Expose `reference_case_count` for read-only UI display, not as a generation target.
    - Store per-sheet ordered columns with original names and mapped standard field names when recognized.
    - Infer per-sheet hierarchy by columns such as `模块`, `功能`, `场景`, `用例标题`.
    - Infer per-sheet priority distribution from `P0/P1/P2/P3`, `高/中/低`, `High/Medium/Low`.
    - Infer per-sheet granularity from average step count and title density.
  - Markdown/TXT:
    - Extract headings as hierarchy candidates.
    - Extract table headers when pipe tables exist.
    - Compute `reference_case_count` only when case-like table rows or checklist entries are recognizable; otherwise return null/unknown rather than guessing.
    - Infer priority only when explicit priority tokens appear.
  - Do not call AI in profile extraction.
  - Raise profile extraction errors for unreadable files, empty files, Excel files without any non-empty worksheet, and Excel files without any usable worksheet.
  - Return warnings for skipped non-usable worksheets when at least one usable worksheet remains, unknown optional columns, unsupported images/attachments, and truncated text.

- [ ] Implement reference library service in `reference_library.py`.
  - `save_reference_file(db, project_id, user_id, upload_file, category_id)`
  - `list_reference_categories(db, project_id)`
  - `create_reference_category(db, project_id, user_id, name)`
  - `rename_reference_category(db, project_id, category_id, name)`
  - `delete_reference_category(db, project_id, category_id)`
  - `list_reference_files(db, project_id, category_id=None)`
  - `soft_delete_reference_file(db, project_id, reference_id, user_id)`
  - `set_recommended_primary(db, project_id, reference_id, category_id=None)`
  - Store uploaded files under `REFERENCE_STORAGE_ROOT / str(project_id)`, or an equivalent dedicated project reference storage directory.
  - Do not store reference library files under the existing user-scoped source upload directory or any directory swept by upload retention cleanup.
  - Reuse/refactor `_sanitize_upload_filename`, chunked upload saving, suffix validation, max-size checks, Excel engine selection, and workbook opening behavior from the existing source upload/reader code where doing so keeps dependencies clean.
  - Keep `/api/v1/test-cases/references` as a separate upload API because it must write reference metadata, category linkage, profile JSON, warnings, and project-level list visibility.
  - Normalize suffix to lowercase.
  - Normalize category names by trimming leading/trailing whitespace before save and uniqueness checks; reject empty names after trim.
  - Do not case-fold category names or normalize internal whitespace/full-width characters.
  - Reject suffixes outside the V1 allowlist with HTTP 400-compatible domain error.
  - Reject uploads when an active reference with the same `project_id`, `category_id` (including null), and `original_filename` already exists; return a Chinese message telling the member to contact a project admin to delete the old file before uploading again.
  - If profile extraction fails after the file is written, delete the written file and roll back the DB insert; return a clear Chinese upload failure message.
  - When deleting a reference, delete the physical file, set `deleted_at` and `deleted_by`, clear `storage_path`, clear `profile_json`, clear `is_recommended_primary`, and exclude the row from active lists/generation.
  - If the physical file is already missing while deleting a reference, continue as a successful soft delete and metadata purge.
  - If the physical file exists but cannot be deleted because of permission or IO errors, return deletion failure and leave the active row unchanged so the admin can retry.
  - Deleted reference rows only preserve audit metadata such as original filename, suffix, size, uploader, created/updated/deleted timestamps, and deleter.
  - Allow creating an empty category; category creation must not require an existing reference file.
  - When deleting a category, set affected active references' `category_id` to null and clear `is_recommended_primary`.
  - When setting recommended primary, clear `is_recommended_primary` from other active references in the same project and category; `category_id = null` is the uncategorized scope.

- [ ] Add API router `backend/app/api/test_cases_api.py`.
  - Use `APIRouter(prefix="/test-cases", tags=["test-cases"])`.
  - Member endpoints use `current.require_strict_project_member()`.
  - Admin endpoints use `current.require_project_admin()`.
  - Category creation is a member endpoint; category rename/delete remain admin endpoints.
  - Upload endpoint accepts multipart `file` and optional `category_id`.
  - Responses use the existing API envelope described in this plan's Backend Response Envelope section.

- [ ] Register router in `backend/app/api/router.py`.

- [ ] Add backend tests `backend/tests/test_test_case_reference_library_api.py`.
  - Member can list categories and active files.
  - Member can create an empty category.
  - Category creation trims leading/trailing whitespace, rejects empty names, and rejects duplicates after trim.
  - Member can upload `.xlsx`, `.md`, `.txt`.
  - Member cannot rename/delete category.
  - Member cannot delete reference.
  - Admin can rename/delete category.
  - Deleting a category clears the recommended primary flag from references moved to uncategorized.
  - Admin can delete reference: row is soft-deleted for audit, physical file is removed, `storage_path`/`profile_json` are cleared, and the row is excluded from active lists.
  - Admin can set one recommended primary per project category, including the uncategorized scope.
  - Non-member cannot access current project reference library.
  - Different projects never see each other's references.
  - Upload rejects unsupported suffix.
  - Upload rejects a duplicate active filename in the same project category.
  - Upload allows the same filename in a different category or after the old reference has been soft-deleted.
  - Upload profile extraction failure leaves no reference row and no saved file.
  - Delete reference succeeds when the physical file is already missing, while still clearing reusable metadata.
  - Delete reference returns failure and keeps the row active when an existing physical file cannot be removed due to permission or IO errors.
  - Runtime cleanup candidate collection does not include active reference library files.
  - Excel upload exposes every usable worksheet in `sheet_options`, selects `测试用例`/`用例`/`TestCases` by priority as default, and falls back to the first usable worksheet when none match.
  - Excel upload succeeds when at least one usable worksheet exists and skips non-usable worksheets with warnings.
  - Excel upload rejects a workbook when no worksheet has both a reliably detected header and at least one recognizable case row.
  - Excel `reference_case_count` counts case-content rows after the detected header and excludes empty rows, pure module grouping rows, note-only rows, remarks-only rows, and total rows.
  - Markdown/TXT `reference_case_count` returns null/unknown when no case-like table rows or checklist entries are recognizable.

- [ ] Verification command:

```powershell
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_reference_models.py backend/tests/test_test_case_reference_library_api.py
```

## Phase 3: 策划案快照

- [ ] Create `backend/app/test_cases/planning_snapshot.py`.

- [ ] Define snapshot schemas in `schemas.py`.
  - `PlanningSourceType = Literal["feishu", "uploaded_excel"]`
  - `PlanningSnapshotRequest`
  - `PlanningSnapshotCell`
  - `PlanningSnapshotSheet`
  - `PlanningSnapshotResponse`
  - `PlanningSnapshotLimits`
  - Include `source_summary`, `sheet_name`, `rows`, `columns`, `non_empty_cell_count`, `truncated`, `warnings`.

- [ ] Implement Excel snapshot reader.
  - Accept existing source upload result as `DataSource(type="local_excel", pathOrUrl=selected_path)`.
  - Verify local path through existing local-reader allowlist rules or use the same resolved upload root.
  - Read one sheet by name using pandas/openpyxl.
  - Normalize empty cells to empty strings.
  - Preserve original row and column indexes in snapshot cells.
  - Apply limits in this order:
    - rows,
    - columns,
    - non-empty cells,
    - cell text length,
    - total characters.
  - Add warning entries for every applied truncation.
  - Add warning that V1 only reads cell text and does not read images/attachments.

- [ ] Implement Feishu snapshot reader.
  - Reuse existing Feishu URL parsing and tenant access client code.
  - Resolve spreadsheet token, optional sheet id/title, and wiki token when present.
  - If request provides `sheet_name`, match by sheet title first, then sheet id.
  - Read values only; do not request image or file attachment content.
  - Apply the same snapshot limits as Excel.
  - Surface permission failures using the same Chinese error style as existing Feishu source APIs.

- [ ] Add API endpoint.
  - `POST /api/v1/test-cases/planning-snapshot`
  - Project member only.
  - It returns snapshot data for immediate preview; it does not persist snapshot rows.

- [ ] Add tests `backend/tests/test_test_case_planning_snapshot.py`.
  - Excel snapshot returns selected sheet data.
  - Excel snapshot applies row/column/cell/total limits and warnings.
  - Excel snapshot includes image/attachment unread warning.
  - Invalid local path is rejected.
  - Feishu reader is tested with monkeypatched client functions for successful read and permission failure.
  - Snapshot response does not create generation history rows.

- [ ] Verification command:

```powershell
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_planning_snapshot.py backend/tests/test_feishu_reader.py backend/tests/test_source_api_security.py
```

## Phase 4: AI 生成编排

- [ ] Create `backend/app/test_cases/generation.py`.
- [ ] Create `backend/app/test_cases/qa_case_method.py`.
  - Define the built-in `QA Case Method` constants:
    - blueprint dimensions,
    - completeness matrix,
    - scenario library,
    - standard case fields,
    - self-check rules,
    - warning templates.
  - Keep this module deterministic and versioned with code.
  - Do not read a maintainable knowledge database in V1.
  - Expose a future-compatible internal `knowledge_context` helper that returns an empty context plus a visible “V1 未接入项目级 QA 知识库” note.

- [ ] Define generation schemas in `schemas.py`.
  - `TestCaseGenerationRequest`
  - `TestCaseGenerationResponse`
  - `TestCaseBlueprint`
  - `TestCaseBlueprintModule`
  - `GeneratedTestCase`
  - `GeneratedCaseStats`
  - `GenerationWarning`
  - `ReferenceSelection`
  - `QaCaseMethodContext`
  - `RequirementTrace`
  - Request includes:
    - `planning_snapshot`,
    - optional `reference_ids`,
    - optional `primary_reference_id`,
    - optional `primary_reference_sheet_name` for Excel primary references,
    - no public `knowledge_context` request field in V1; if a client submits `knowledge_context` or equivalent user-supplied knowledge content, reject it with HTTP 400-compatible domain error,
    - optional `generation_options` for priority preference and output style only; do not include a case count target in V1 because the UI count is read from the reference profile.
  - Response includes:
    - `blueprint`,
    - `cases`,
    - `warnings`,
    - `stats`,
    - `export_columns`,
    - `requirement_trace`,
    - `method_context`.

- [ ] Implement project AI credential loading.
  - Use `load_project_credential`.
  - Use `decrypt_credential_key`.
  - Use `parse_extra_headers`.
  - If credential missing or disabled, return an actionable Chinese message telling the user to contact project admin to configure project AI.
  - Sanitize provider errors with existing helper before returning to API client.

- [ ] Implement blueprint prompt builder.
  - Inputs:
    - bounded planning snapshot text,
    - optional selected reference profiles,
    - optional primary reference profile,
    - V1 constraints.
  - Use `qa-case` as the canonical generation method: extract module tree, flows, states, roles, time refresh points, data/config rules, external coupling, risks, open questions, and warnings before generating case rows.
  - Include the built-in method context from `qa_case_method.py`; include a knowledge-library note that V1 has no maintainable project QA knowledge library.
  - Output JSON schema requires:
    - `modules`,
    - `flows`,
    - `requirement_traces`,
    - `coverage_dimensions`,
    - `risks`,
    - `unmapped_requirements`,
    - `unsupported_or_unfounded_test_points`,
    - `open_questions`,
    - `warnings`.
  - The prompt must state that images/attachments were not read and should be reflected in warnings when relevant.

- [ ] Implement case prompt builder.
  - Inputs:
    - same planning snapshot,
    - readonly blueprint from stage 1,
    - optional selected reference profiles,
    - optional primary reference field order.
  - Output JSON schema requires `cases` array using standard field keys.
  - If no reference profile is selected, generate from the `qa-case` completeness matrix and standard case fields.
  - Every generated case should carry `source_requirement` or a clear assumption/warning when no direct source line can be mapped.
  - The prompt must prohibit invented statistics and external persistence claims.
  - The prompt must prefer explicit source requirement text from the snapshot and put uncertain interpretation in `remarks`.

- [ ] Implement provider calls.
  - Call `call_provider_json` once for blueprint and once for cases.
  - Validate returned JSON with Pydantic schemas.
  - Merge warnings from snapshot, blueprint stage, case stage, and reference profile stage.
  - Generate stable display case IDs in code when provider omits them.
  - Compute stats in code:
    - total cases,
    - priority counts,
    - module counts,
    - case type counts,
    - warning count.

- [ ] Implement reference selection rules.
  - Empty `reference_ids` and empty `primary_reference_id` are valid; generation must proceed with planning snapshot plus `qa-case` standard logic.
  - All selected references, when present, must be active and belong to current project.
  - `primary_reference_id`, when present, must be one of selected references.
  - If the primary reference is Excel, `primary_reference_sheet_name` must match one of that reference's `sheet_options`; if omitted, use `default_sheet_name`.
  - If the primary reference is Markdown/TXT, ignore an empty `primary_reference_sheet_name` and reject non-empty sheet names.
  - Do not implicitly pick newest selected reference as primary. If request omits primary id, treat all selected references as supplementary references only.
  - Export column order follows the selected primary reference sheet's mapped columns first, then missing standard fields; without primary reference, use the standard field order.

- [ ] Add API endpoint.
  - `POST /api/v1/test-cases/generate`
  - Project member only.
  - Does not insert result rows into any table.

- [ ] Add tests `backend/tests/test_test_case_generation.py`.
  - Missing project AI returns Chinese configuration error and does not call provider.
  - Disabled project AI returns the same class of configuration error.
  - Provider is called twice in successful flow.
  - Generated stats are computed from returned cases, not copied from provider payload.
  - Invalid reference from another project is rejected.
  - Omitted primary reference does not block generation and does not auto-pick newest selected reference.
  - Empty reference selection still generates blueprint and cases using standard `qa-case` logic.
  - Blueprint is returned but no editable draft or history record is created.
  - Provider error is sanitized and does not expose API key.
  - Snapshot warnings are preserved.
  - Built-in QA Case Method context is included in blueprint/case prompts.
  - Empty V1 knowledge context is surfaced as a warning or method note, not as a hard failure.
  - User-supplied knowledge content is rejected in V1 instead of being silently injected into prompts.
  - Requirement trace maps cases back to snapshot rows/fragments where available.

- [ ] Verification command:

```powershell
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_generation.py backend/tests/test_project_ai_config_api.py
```

## Phase 5: Excel 导出

- [ ] Create `backend/app/test_cases/exporter.py`.

- [ ] Define export schemas in `schemas.py`.
  - `TestCaseExportRequest`
  - It carries current page result:
    - `blueprint`,
    - `cases`,
    - `warnings`,
    - `stats`,
    - `primary_reference_profile`,
    - `export_columns`.
  - This keeps export stateless and avoids generation history persistence.

- [ ] Implement export column resolver.
  - Start with primary reference recognized columns in original order.
  - Append missing standard fields.
  - Drop unrecognized reference columns unless they have a direct mapped standard field.
  - Guarantee `title`, `steps`, `expected_results`, `priority`, `remarks` are present.
  - Use Chinese display names for standard fields where existing UX is Chinese.

- [ ] Implement workbook generation.
  - Sheet `测试用例`: generated cases using resolved columns.
  - Sheet `用例蓝图`: modules, flows, coverage dimensions, risks, open questions.
  - Sheet `生成说明`: warnings, source summary, reference summary, stats, V1 limitations.
  - Apply readable header fill, frozen header row, auto filter, wrapped text, and sane column widths.
  - Do not write hidden metadata with API key, prompts, or raw provider response.

- [ ] Add API endpoint.
  - `POST /api/v1/test-cases/export`
  - Project member only.
  - Returns `test-cases-{yyyyMMdd-HHmmss}.xlsx`.

- [ ] Add tests `backend/tests/test_test_case_exporter.py`.
  - Workbook has exactly the three planned sheets.
  - Primary reference field order is respected for recognized fields.
  - Missing standard fields are appended.
  - Unknown reference columns are not generated.
  - Warnings sheet includes image/attachment unread limitation.
  - Export response has XLSX content type and filename.
  - Export request does not persist history rows.

- [ ] Verification command:

```powershell
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_exporter.py
```

## Phase 6: 前端页面

- [ ] Create TypeScript contracts.
  - `frontend/src/types/testCases.ts`
  - Mirror backend request/response schemas.
  - Keep API-layer types separate from component view models.

- [ ] Create API wrapper.
  - `frontend/src/api/testCases.ts`
  - Functions:
    - `fetchReferenceCategories`
    - `createReferenceCategory`
    - `renameReferenceCategory`
    - `deleteReferenceCategory`
    - `fetchReferenceFiles`
    - `uploadReferenceFile`
    - `deleteReferenceFile`
    - `setRecommendedPrimaryReference`
    - `createPlanningSnapshot`
    - `generateTestCases`
    - `exportGeneratedTestCases`
  - Use `apiFetch` for JSON and `apiDownloadFile` for export.
  - Reuse `uploadSourceFile` from `frontend/src/api/workbench.ts` for 策划案 Excel 上传; do not create a second source-upload API.

- [ ] Add route and preload.
  - Modify `frontend/src/router/index.ts` to add `/test-cases`.
  - Modify `frontend/src/router/routePreload.ts` if it enumerates route components.
  - Modify `frontend/src/App.vue` navigation to show “用例生成”.

- [ ] Create view `frontend/src/views/TestCaseGeneratorView.vue`.
  - Layout:
    - left setup panel for source, sheet, reference category, reference files, primary reference,
    - main preview area with tabs `策划案快照`, `蓝图`, `用例`, `Warnings`,
    - top action bar with `读取快照`, `生成用例`, `导出 Excel`.
  - Source controls:
    - segmented mode: 飞书表格 / 上传 Excel,
    - Feishu URL input,
    - Excel upload button,
    - sheet selector from metadata/snapshot response.
  - Reference controls:
    - category selector,
    - upload reference,
    - member-visible file list,
    - primary reference sheet selector shown under primary reference; disabled with “当前参考案例无 Sheet” for Markdown/TXT references,
    - admin-only rename/delete/set recommended actions gated by backend failures and optional frontend role state if available.
  - Generation controls:
    - generate button disabled until snapshot is read; reference selection is optional,
    - show read-only reference case count from the selected primary reference profile/sheet; when no primary reference is selected, show “未使用主参考” or equivalent and do not render it as an editable target count,
    - show project AI missing errors inline,
    - show progress state for snapshot/generation/export separately.
  - Preview:
    - snapshot table capped for UI rendering,
    - blueprint read-only structured sections,
    - cases table with stable columns,
    - warnings list with level/source/message.
  - State:
    - keep only current page state,
    - clearing source clears snapshot/result,
    - changing reference selection, primary reference, or primary reference sheet clears generated result and requires regeneration,
    - no local storage for generated cases.

- [ ] Add styling inside the Vue SFC or existing page style conventions.
  - Dense operational UI; no landing page or marketing hero.
  - Avoid nested card layouts.
  - Use Element Plus tabs/table/upload/buttons consistently with current app.
  - Keep text inside buttons short and non-overlapping at desktop and mobile widths.

- [ ] Add frontend tests.
  - `frontend/tests/unit/testCasesApi.test.ts`
    - JSON endpoints call expected paths and methods.
    - export endpoint uses `apiDownloadFile`.
    - reference upload uses multipart `FormData`.
  - `frontend/tests/unit/TestCaseGeneratorView.test.ts`
    - generate button disabled before snapshot/reference selection.
    - snapshot success enables generation.
    - result renders blueprint, cases, warnings.
    - export button calls API with current in-memory result.
    - changing source clears result.
    - primary reference sheet options render for Excel references.
    - default primary reference sheet is selected from the backend-provided `default_sheet_name` and can be changed by the user.
    - read-only reference case count updates when primary reference sheet changes.
    - non-Excel primary references show a disabled no-Sheet selector.

- [ ] Verification command:

```powershell
cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build
```

## Cross-Cutting Documentation

- [ ] Keep `docs/specs/test-case-generation.md` as the product/spec source of truth.
- [ ] Do not add implementation task details to `CONTEXT.md`; it is a glossary/domain language file.
- [ ] If endpoint names or limits change during implementation, update `docs/specs/test-case-generation.md` in the same slice.
- [ ] Append `PROJECT_RECORD.md` after each completed implementation slice with actual timestamp, files touched, and verification result.
- [ ] Update `CHANGELOG.md` only when user-facing behavior changes, not for intermediate private refactors.

## Final Verification

- [ ] Run backend targeted suite:

```powershell
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_reference_models.py backend/tests/test_test_case_reference_library_api.py backend/tests/test_test_case_planning_snapshot.py backend/tests/test_test_case_generation.py backend/tests/test_test_case_exporter.py
```

- [ ] Run broader backend smoke when targeted tests pass:

```powershell
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_project_ai_config_api.py backend/tests/test_feishu_reader.py backend/tests/test_source_api_security.py backend/tests/test_alembic_migrations.py
```

- [ ] Run frontend checks:

```powershell
cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build
```

- [ ] Manual UI verification:
  - Start backend and frontend dev servers using the repository's existing commands.
  - Generate after reading a planning snapshot with no reference selected; confirm blueprint, cases, warnings, and standard export columns are produced.
  - Log in as project member and confirm view/upload/use/generate/export works.
  - Log in as normal project member and confirm category rename/delete/recommend actions are rejected.
  - Log in as project admin and confirm category rename/delete/recommend actions succeed.
  - Generate from uploaded Excel and from Feishu source.
  - Export Excel and inspect three sheets.
  - Confirm refresh loses generated result, proving V1 has no generation history.

## Execution Order

1. 架构契约和 `/api/v1/test-cases/*` router skeleton
2. 策划案快照读取，对应页面 01/02 的必需输入
3. AI 生成编排的无参考主链路，按 `qa-case` 蓝图和完整性矩阵生成
4. Excel 标准字段导出，对应页面 04 的无参考闭环
5. 参考案例库和画像，对应页面 03 的可选增强能力
6. 主参考 Sheet、字段顺序和参考风格增强接入 02/04
7. 前端真实 API 接线、文档同步与最终验证

## Deferred V2 Items

- Project QA Knowledge Library data model, maintenance UI, and permissions.
- Knowledge review, publish status, version history, rollback, and expiration policy.
- Import path from QA Workspace `knowledge_base/knowledge/` with source, reviewer, and update metadata.
- Knowledge retrieval, relevance ranking, hit explanation, and no-hit reporting.
- Conflict handling between built-in QA Case Method, project knowledge, planning snapshot, and reference case profiles.
- Prompt budget rules for injecting knowledge and protecting sensitive source text.
- Whether knowledge usage is shown only on page, included in Excel export, or auditable in a future generation history.
- How image/attachment understanding can produce reusable knowledge after V2 visual support exists.

## Deferred qa-case Migration Matrix

- QA Workspace runtime guard: do not port preflight, setup profile, role switching, or Git remote checks into V1; reserve an external workspace adapter if V2 ever integrates QA Workspace.
- Task workspace: do not create `tasks/<task>` directories or persist manifest/source files in V1; reserve generation history/source artifact models for V2.
- Knowledge base: do not read or maintain `knowledge_base/knowledge/` or `knowledge_local/drafts` in V1; reserve Project QA Knowledge Library with review/version/search.
- Context readers: do not port Jira, config SVN, server-code, Trino/Data MCP, or multi-source task ingestion in V1; reserve source connector interfaces.
- Coupling test points: do not require `coupling-test-point-generation` output in V1; reserve `confirmed_test_points` import as a future generation input.
- Visual evidence: do not port image packet, observation, or validation workflow in V1; reserve visual evidence and observation schemas.
- Feishu write targets: do not create AI-owned Feishu sheets or write back existing sheets in V1; reserve export target abstraction.
- Export formats: do not output CSV, Markdown, or Feishu-friendly text in V1; reserve `export_format` expansion on top of the structured cases payload.
- Advanced workbook layout: do not force double headers, module rows, inherited blank-cell semantics, tester/device/version execution matrices in V1; reserve export template/profile.
- Partial generation: do not support “only supplement this module/change range” in V1; reserve `scope_mode` and selected blueprint modules.
- Clarification loop: do not save pending questions or support answer-then-regenerate in V1; reserve blueprint review and second-pass generation protocol.
- Evidence package: do not store full original docs/images/attachments in V1; reserve source artifact retention, cleanup, and permission rules.
- Review workbench: do not build manual handling state for unmapped requirements or unfounded test points in V1; reserve review statuses.
- External read-only checks: do not execute external system validation steps in V1; reserve plugin-like read-only validators.
- Coverage check after generation: do not run automatic coverage statistics in V1; reserve integration with coverage summary on generated cases.
- Direct CLI reuse: do not shell out to `uv run qa ...` from Web requests in V1; any future reuse must go through a controlled service adapter.

## Risk Notes

- Feishu image/attachment unread warning should be explicit because users may assume screenshots in 策划案 were considered.
- Project AI errors must never expose full API keys or provider raw secrets.
- Reference-free generation must remain first-class; do not regress into requiring a primary reference before calling the provider.
- Do not let the future `knowledge_context` extension become an unreviewed free-form prompt input in V1; public requests must reject user-supplied knowledge content.
- Reference profile extraction is deterministic by design; adding AI here would expand cost, latency, and failure modes beyond V1.
- Deleting reference files should not retain the original file or profile JSON. V1 keeps only minimal audit metadata to reduce sensitive planning/test-case retention.
- Export remains stateless by carrying current page result in the request; this preserves the V1 “不保存历史” decision.
