# ADR 0004: Canonical template case contract and quality audit

V3 adopts a versioned `Test Case Export Template` as the canonical visible case-row contract instead of allowing reference test case profiles to redefine exported fields or layout. Reference cases may still influence hierarchy, naming, and granularity, while requirement traces and supporting metadata remain in remarks, the blueprint, and audits; this favors stable QA execution and statistics over arbitrary reference-workbook fidelity.

A Generation Run also applies a deterministic `Case Quality Audit` after coverage checking and may perform one targeted repair pass. Unresolved quality gaps produce `partial_completed`, and strict mode blocks export, so template-conformant rows cannot be mistaken for executable cases when numeric expectations or other required QA Case Method checks are missing.

The V3 template row contract is introduced beside the legacy synchronous generated-case payload rather than replacing that compatibility surface in place. Only case-bearing requirement atoms drive official cases and coverage totals; open questions and limitations remain visible in the blueprint and audits without forcing speculative case rows.

Template rendering and workbook verification are implemented once as a deterministic project service shared by Generation Run export and a thin standalone CLI. The Web application does not shell out to QA Workspace or its `uv run qa` commands, and the CLI does not bypass project AI generation, source-reading permissions, or external-system boundaries.

Each Generation Run automatically renders a short-lived `Generated Test Case Artifact` bundle after coverage and quality auditing. Database rows remain the source of truth; the page selects and previews stored files, downloads read already verified bytes, and artifact retry reruns only deterministic rendering. The bundle contains the canonical xlsx, blueprint Markdown, statistics JSON, coverage JSON, and quality JSON. This hybrid model keeps the immediate-file experience of `qa-case-xlsx` without making filesystem output a second generation state or forcing a new AI call when a user downloads again.
