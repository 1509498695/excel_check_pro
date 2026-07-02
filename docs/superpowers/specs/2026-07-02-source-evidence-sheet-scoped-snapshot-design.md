# Source Evidence Sheet-Scoped Snapshot Design

## Context

The test case generation workspace currently creates a `Source Evidence Run` for local files, SVN files, and Feishu documents. Workbook readers parse all visible sheets and resources into one run, while the snapshot endpoint converts the full parsed source into a single `PlanningSnapshotResponse` with `sheet_name = Source Evidence`.

The desired behavior is to restore the domain rule that one generation is based on one `Planning Sheet`: after a workbook is read, the user chooses a sheet, and the generated snapshot and test cases use that sheet's text, tables, and images.

## Resolved Decisions

1. `Source Evidence Run` remains the whole-source reading session. It still parses all visible workbook sheets, resources, warnings, TTL metadata, and audit-safe summaries.
2. `Planning Sheet Snapshot` becomes sheet-scoped for workbook-like sources. It includes only the selected sheet's text/table content and resource references located on that sheet.
3. The UI defaults to the first visible sheet after a workbook run is ready.
4. Hidden sheets are not selectable. They remain excluded and are surfaced through warnings.
5. Current-sheet images are read and selected by default for visual observation. The user can change the visual selection manually.
6. Default visual selection is not evidence adoption. Images only become generation facts after Vision observation and explicit adoption as `Adopted Visual Evidence`.
7. Switching sheets invalidates the current snapshot, AI brief, generated cases, and exportable result.
8. Existing adopted visual evidence is not deleted when switching sheets, but generation only sends adopted evidence that belongs to the current selected sheet and current visual selection.
9. Sheet selection applies to workbook/spreadsheet sources: local `.xlsx/.xls`, SVN `.xlsx/.xls`, and Feishu sheets. Feishu docx/wiki and standalone images keep the source evidence status view without a sheet selector.
10. Large selected sheets still use existing snapshot and generation budget limits. Truncation remains explicit through warnings.

## Considered Approaches

### Recommended: Sheet-Scoped Snapshot Over Whole Run

Keep full-source parsing in `Source Evidence Run`, add sheet selection to the snapshot/generation boundary, and default visual selection to all images on the selected sheet.

This preserves the full resource inventory and retry/audit behavior while aligning generation with the `Planning Sheet` glossary. It also avoids reparsing the workbook when the user switches sheets.

### Rejected: Frontend-Only Filtering

Only changing the UI would leave the backend snapshot and generation prompt using full-workbook content. That contradicts the selected-sheet requirement and would make AI briefs and generated cases vulnerable to cross-sheet contamination.

### Rejected: Parse Only One Sheet at Run Creation

Parsing only one sheet would make sheet switching require a new run or reread, weaken the resource inventory, and complicate TTL cleanup and resource audit behavior.

## API Design

`POST /api/v1/test-cases/source-evidence-runs/{run_id}/snapshot` should accept an optional request body for workbook-like sources:

```json
{
  "sheet_name": "活动配置"
}
```

For workbook/spreadsheet parsed sources, `sheet_name` is required unless the run has exactly one selectable sheet. For non-sheet sources, the server ignores a missing `sheet_name` and keeps current behavior.

The response remains `PlanningSnapshotResponse`, with `sheet_name` set to the selected sheet name. The columns stay compatible with the existing Source Evidence snapshot columns:

```text
来源类型, 位置, 标题/页签, 内容, 证据状态
```

Errors:

- Unknown sheet: `400`, message says the selected sheet is not available.
- Hidden sheet: `400`, message says hidden sheets are excluded.
- Empty visible sheet: return an empty/limited snapshot with a warning rather than failing.
- Expired or cleaned run: keep current `409` behavior.

## Backend Design

The parsed source model already carries `ParsedSourceUnit` records with `kind = sheet`, `title`, `cells`, and metadata. Snapshot building should filter these units by the selected sheet for workbook/spreadsheet sources.

Resource rows should be filtered by sheet metadata or by position parsing. Excel image resources already include metadata such as `sheet`, `sheet_index`, `image_index`, and `anchor`; this metadata should be the primary filter. Position parsing is fallback only.

Snapshot rows should include:

- Selected sheet cell rows as `table`.
- Selected sheet resource rows as `pending_visual`.
- Existing warnings, plus sheet-scope warnings when resources cannot be confidently mapped.

Prompt context and export summary should report selected sheet scope, not full workbook scope, when a sheet-scoped snapshot is used.

## Frontend Design

The source evidence readiness card should show a sheet selector for workbook/spreadsheet runs. The selector options come from the run's parsed source safe metadata or a new safe sheet summary response.

Default behavior:

- After run creation, choose the first visible sheet.
- Load visual candidates and mark every current-sheet image as selected by default.
- Keep the resource drawer usable for manual adjustment.

State invalidation:

- Changing sheet clears `planningSnapshot`, snapshot brief, generation result, export readiness, and stale source evidence snapshot run id.
- Changing sheet resets default visual selection to all images from the new sheet.
- Manual visual selection changes after that remain user-owned until the sheet changes again.

## Visual Evidence Rules

Current-sheet image resources are selected by default for observation, not automatically observed or adopted.

Generation and export must continue to validate that every submitted adopted evidence id:

- Belongs to the same run.
- Is not expired or revoked.
- Has status `adopted`.
- Belongs to the selected sheet scope for this generation.
- Still belongs to the current visual selection if the user has adjusted it.

Unobserved, observed-but-not-adopted, cross-sheet, or unselected resources can only appear as warnings, open questions, or remarks.

## Testing

Backend tests should cover:

- Multi-sheet `.xlsx` run returns/selects sheet options and snapshots only selected sheet text.
- Current-sheet images appear as `pending_visual` rows; other-sheet images do not.
- Hidden sheet selection is rejected.
- Switching to another visible sheet produces a different snapshot.
- Invalid adopted evidence from another sheet is rejected for generation/export.
- Single-sheet workbook can read snapshot without explicit sheet only if the UI/API chooses that sole sheet deterministically.

Frontend tests should cover:

- Workbook source evidence shows a sheet selector.
- Default sheet is the first visible sheet.
- Reading snapshot sends `sheet_name`.
- Current-sheet images are selected by default in visual candidates.
- Sheet changes clear snapshot, AI brief, generated cases, and export readiness.
- Docx/wiki and standalone image runs do not show the sheet selector.

Documentation updates should cover:

- `docs/specs/test-case-generation-v2-source-evidence.md`
- `docs/specs/test-case-generation-v2-requirements.md`
- `CONTEXT.md` glossary terms for `Planning Sheet` and `Planning Sheet Snapshot`

## Implementation Boundaries

Do not reintroduce the V1 `planning-snapshot` path for new local/SVN workbook reads. The implementation should remain inside the V2 Source Evidence path.

Do not treat selected images as generated requirements. Default selection only prepares them for observation.

Do not delete adopted visual evidence when sheet selection changes. Use sheet-scoped validation at generation/export time instead.
