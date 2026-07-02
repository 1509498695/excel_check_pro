# Test Case Generation V3 Full Generation Design

## Status

Approved direction from the planning session on 2026-07-02. This spec replaces the old synchronous generation path as the product direction; it does not preserve old `/generate` semantics as the frontend main flow.

## Goal

Generate test cases from the complete currently selected `Planning Sheet` without silently dropping later rows or over-budget content. V3 must read the full selected sheet, extract traceable requirement atoms, generate cases in batches, and prove coverage with an audit result.

## Non-Goals

- Do not build the project QA knowledge library in this slice.
- Do not auto-classify and merge every visible sheet in a workbook.
- Do not make unobserved or unadopted visual resources into requirement facts.
- Do not keep permanent generation history or raw prompt/response archives.
- Do not keep the old synchronous generate/export path as the frontend primary flow.

## Confirmed Decisions

- Scope is the current selected `Planning Sheet`; docx/wiki sources without sheets are treated as one document-shaped sheet.
- Full generation is asynchronous and may use multiple AI calls.
- Detailed generation data is short-lived; default TTL is 7 days and should align with Source Evidence cleanup unless a later deployment setting changes it.
- V3 introduces `Generation Run`, `Full Planning Sheet Context`, `Requirement Atom`, and `Coverage Audit`.
- Failed chunks can be retried. A run with failed chunks or uncovered atoms is `partial_completed`, not complete.
- Coverage audit may allow export with visible warnings by default; strict mode can block export when unmapped requirements remain.
- The system may do one automatic supplement generation pass for coverage gaps, then stop.
- Export reads backend-stored generation run results by id. The frontend no longer posts generated cases back as export truth.

## Architecture

The V3 flow is:

```text
Source Evidence Run or uploaded source
-> select Planning Sheet
-> create Generation Run
-> build Full Planning Sheet Context
-> structural chunking
-> extract Requirement Atoms per chunk
-> merge and deduplicate atoms
-> create Test Case Blueprint
-> generate case rows in batches
-> run Coverage Audit
-> supplement uncovered atoms once
-> save short-lived result
-> export by Generation Run id
```

### Full Planning Sheet Context

V3 reads every readable text/table fact from the selected sheet. Page preview can still paginate and summarize, but generation must not rely on the old snapshot limits such as first N rows or fixed prompt character budgets.

The context includes adopted visual evidence that belongs to the selected sheet. Pending, unobserved, observed-but-not-adopted, revoked, expired, or cross-sheet visual resources are warnings only.

### Chunking

Chunking should be structure-first and row-range second:

- Prefer title rows, blank-row sections, merged-cell regions, table header changes, and source unit boundaries.
- Fall back to bounded row windows only when structure is unclear.
- Each chunk records source row range, column range, title hints, resource refs, and status.

The service should limit AI chunk extraction concurrency to 2 by default.

### Requirement Atoms

Each chunk extraction returns requirement atoms. Each atom must include:

- stable atom id within the run
- atom type, such as rule, entry, state, timing, config, reward, role, UI text, visual fact, open question, or limitation
- concise requirement text
- source sheet, row range, column names, and optional cell excerpts
- adopted visual evidence id/ref when applicable
- confidence and warnings

Atoms without a traceable current-source basis are invalid. They can be recorded as unfounded candidates but cannot drive official cases.

### Atom Merge

The merge stage deduplicates overlapping atoms, resolves chunk boundary duplicates, preserves conflicting interpretations as warnings, and produces the atom set used for blueprint and case generation.

### Blueprint and Cases

Blueprint generation uses merged atoms as the requirement source of truth. The reference test case library may influence case field order, naming, hierarchy, and granularity only during case shaping and export; it cannot create new requirement atoms.

Case generation runs by module or atom group. Each case must reference one or more requirement atoms. Cases that cannot be traced to an atom are excluded from official output and recorded in the audit as unfounded candidates.

### Coverage Audit

Coverage audit compares atoms, blueprint nodes, and generated cases. It reports:

- total atoms
- covered atoms
- uncovered atoms
- cases without valid atom support
- failed chunks
- skipped visual resources
- supplement generation result
- export limitations

If the first audit finds gaps, the system runs one supplement pass against uncovered atoms. If gaps remain, the run becomes `partial_completed` and the UI must show that status.

## Run Statuses

Use these statuses:

```text
queued
reading
chunking
extracting_atoms
merging_atoms
blueprinting
generating_cases
auditing_coverage
supplementing
completed
partial_completed
failed
cancelled
expired
```

`completed` requires all chunks to finish, no blocking visual validation error, and coverage audit completion. `partial_completed` is valid when the run has usable cases but also has failed chunks, uncovered atoms, or other explicit limitations.

## API Shape

Recommended endpoints:

- `POST /api/v1/test-cases/generation-runs`
  Creates a run for the selected source evidence run and planning sheet.
- `GET /api/v1/test-cases/generation-runs/{run_id}`
  Returns status, progress, summary, warnings, and current result availability.
- `POST /api/v1/test-cases/generation-runs/{run_id}/cancel`
  Cancels queued or active work.
- `POST /api/v1/test-cases/generation-runs/{run_id}/retry-failed-chunks`
  Retries failed extraction chunks.
- `GET /api/v1/test-cases/generation-runs/{run_id}/atoms`
  Returns paginated requirement atoms and coverage mapping.
- `GET /api/v1/test-cases/generation-runs/{run_id}/cases`
  Returns paginated generated cases.
- `POST /api/v1/test-cases/generation-runs/{run_id}/export`
  Exports from backend-stored run results.

Old synchronous generation should not remain the frontend path. If the route remains temporarily, it should not be documented as V3 behavior.

## Data Model

Minimum new persisted records:

- `test_case_generation_runs`
  Run ownership, source scope, selected sheet, status, progress, summary stats, TTL, created/cancelled/expired metadata.
- `test_case_generation_chunks`
  Chunk boundaries, structure hints, status, error summary, retry count.
- `test_case_requirement_atoms`
  Structured atoms, source coordinates, visual evidence references, merge metadata, warnings.
- `test_case_generation_cases`
  Official generated cases with atom references and normalized fields.
- `test_case_coverage_audits`
  Coverage result, uncovered atoms, unfounded candidates, supplement pass summary.

Do not store raw prompts or full provider responses. Store normalized structures, provider metadata, sanitized error summaries, and warnings.

## Frontend Experience

The generation page should show one primary V3 flow:

1. Select source and planning sheet.
2. Start full generation.
3. Show progress by stage and chunk completion.
4. Allow cancellation.
5. Restore the active or latest short-lived run after refresh.
6. Show result tabs for cases, coverage audit, warnings, and atoms.
7. Export through the run id.

The old snapshot preview can remain as a source preview, but it must not imply that only previewed rows are used for generation.

## Export

The V3 workbook should include at least:

- `测试用例`
- `用例蓝图`
- `生成说明`
- `覆盖审计`

The coverage sheet lists atom id, source sheet, source row/columns, atom text, coverage status, linked case ids, failed chunk status, and limitation notes.

## Security and Retention

Generation run details are short-lived and project-scoped. Detailed atoms, cases, audit rows, and sanitized model-stage data are cleaned at TTL. Minimal audit metadata can remain: run id, project id, source summary hash or safe summary, selected sheet name, status, counts, created by, created at, completed at, expired at.

No full source URL tokens, local sensitive paths, raw prompts, full provider responses, API keys, or unadopted visual observations should appear in export, logs, or persisted run details.

## Testing

Backend tests should cover:

- full selected-sheet extraction beyond old row and character limits
- structural chunking fallback to row windows
- atom extraction schema validation
- atom merge and duplicate handling
- cases without atom support excluded from official output
- coverage audit detects uncovered atoms
- one supplement pass occurs and then stops
- partial completed status for failed chunks
- cancel and retry failed chunk behavior
- export by run id includes coverage audit
- cross-project access rejection
- TTL cleanup removes detailed generation data
- unadopted or cross-sheet visual refs blocked

Frontend tests should cover:

- V3 run creation and progress rendering
- refresh restoring a short-lived run
- cancelled, failed, partial, and completed states
- coverage warnings and strict-mode export blocking
- export call by run id
- no frontend postback of generated cases as export truth

## Documentation Updates

`CONTEXT.md` defines the new domain terms. ADR 0003 records the architectural decision to replace synchronous generation with short-lived full-generation runs.
