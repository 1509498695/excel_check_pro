"""用例生成 V1 API 契约模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.schemas import DataSource


class TestCaseBaseModel(BaseModel):
    """用例生成请求默认拒绝未知字段，避免把 V2 输入误接进 V1。"""

    model_config = ConfigDict(extra="forbid")


class GenerationWarning(TestCaseBaseModel):
    """页面、生成和导出共享的用户可见警告。"""

    source: str = "system"
    level: Literal["info", "warning", "error"] = "warning"
    message: str


class ParsedSourceCell(TestCaseBaseModel):
    """富来源中的稀疏单元格。"""

    coord: str
    row: int = Field(ge=1)
    col: int = Field(ge=1)
    text: str = ""
    raw: Any | None = None


class ParsedSourceResource(TestCaseBaseModel):
    """富来源中的图片、附件或其它资源引用。"""

    ref: str
    type: str
    source_id: str
    position: str
    filename: str = ""
    file_token: str = ""
    mime_type: str = ""
    status: str = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)


class UnsupportedResourceCandidate(TestCaseBaseModel):
    """无法直接作为视觉/附件证据使用的资源候选。"""

    kind: str
    token: str = ""
    block_id: str = ""
    position: str = ""
    source: str = ""
    status: str = "unsupported"
    supported: bool = False
    pointer_block_id: str | None = None
    cell_block_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedSourceUnit(TestCaseBaseModel):
    """富来源中的一个可追踪片段。"""

    unit_id: str
    kind: str
    title: str = ""
    path: str = ""
    cells: list[ParsedSourceCell] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedSource(TestCaseBaseModel):
    """Source Evidence reader 的通用 Parsed Source 输出。"""

    source_type: str = ""
    title: str
    doc_type: str
    token: str
    url: str
    markdown: str = ""
    source_units: list[ParsedSourceUnit] = Field(default_factory=list)
    resources: list[ParsedSourceResource] = Field(default_factory=list)
    unsupported_resource_candidates: list[UnsupportedResourceCandidate] = Field(
        default_factory=list
    )
    raw_manifest: dict[str, Any] = Field(default_factory=dict)
    warnings: list[GenerationWarning] = Field(default_factory=list)


class ParsedFeishuSource(ParsedSource):
    """飞书富读取 adapter 的 Parsed Source 兼容类型。"""


class SourceEvidenceRunCreateRequest(TestCaseBaseModel):
    """创建 Source Evidence Run 的请求。"""

    source_type: Literal["feishu", "svn_file"]
    source_url: str = Field(min_length=1)


class SourceEvidenceRunResponse(TestCaseBaseModel):
    """Source Evidence Run 摘要响应，不返回原文或本地路径。"""

    id: int
    status: str
    source_type: str
    source_summary: str = ""
    source_title: str = ""
    source_identifier: str = ""
    created_at: str | None = None
    expires_at: str | None = None
    warnings: list[GenerationWarning] = Field(default_factory=list)
    resource_count: int = Field(default=0, ge=0)


class SourceEvidenceCapabilityItem(TestCaseBaseModel):
    """Source Evidence 运行能力单项状态。"""

    key: str
    label: str
    configured: bool = False
    available: bool = False
    status: str = "missing"
    message: str = ""
    action: str = ""
    level: Literal["info", "warning", "error"] = "warning"


class SourceEvidenceCapabilityStatusResponse(TestCaseBaseModel):
    """当前项目 Source Evidence 运行能力状态。"""

    svn_credential_configured: bool = False
    source_evidence_svn_roots_configured: bool = False
    vision_ai_configured: bool = False
    soffice_configured: bool = False
    soffice_available: bool = False
    is_project_admin: bool = False
    items: list[SourceEvidenceCapabilityItem] = Field(default_factory=list)
    warnings: list[GenerationWarning] = Field(default_factory=list)
    admin_details: dict[str, Any] | None = None


class SourceEvidenceAuthorizationRequestResponse(TestCaseBaseModel):
    """Source Evidence 飞书授权请求结果。"""

    status: str
    message: str = ""
    authorization_id: int | None = None
    target_mode: str = "not_sent"
    sent_targets_count: int = Field(default=0, ge=0)
    failed_targets_count: int = Field(default=0, ge=0)
    fallback_to_default_chat: bool = False
    owner_candidates_truncated: bool = False
    expires_at: str | None = None
    can_retry_read: bool = False


class SourceEvidenceAuthorizationAuditItem(TestCaseBaseModel):
    """Source Evidence 授权复用审计摘要，不含源 token/URL。"""

    id: int
    project_id: int
    app_id: str = ""
    doc_type: str = ""
    permission: str = "edit"
    status: str = ""
    source_fingerprint: str = ""
    source_alias_fingerprints: list[str] = Field(default_factory=list)
    originating_run_id: int | None = None
    target_mode: str = "not_sent"
    sent_targets_count: int = Field(default=0, ge=0)
    failed_targets_count: int = Field(default=0, ge=0)
    owner_candidates_truncated: bool = False
    authorized_by_open_id: str = ""
    authorized_by_display_name_masked: str = ""
    state_expires_at: str | None = None
    authorized_at: str | None = None
    expires_at: str | None = None
    invalidated_at: str | None = None
    invalidated_by: int | None = None
    last_error_summary: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class SourceEvidenceAuthorizationAuditListResponse(TestCaseBaseModel):
    """Source Evidence 授权审计列表。"""

    items: list[SourceEvidenceAuthorizationAuditItem] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1)
    offset: int = Field(default=0, ge=0)


class SourceEvidenceResourceResponse(TestCaseBaseModel):
    """Source Evidence 资源清单响应。"""

    id: int
    ref: str
    type: str
    position: str = ""
    filename: str = ""
    download_status: str = "pending"
    adoption_status: str = "unobserved"
    mime_type: str = ""


class SourceEvidenceResourceListResponse(TestCaseBaseModel):
    """Source Evidence Run 资源列表响应。"""

    items: list[SourceEvidenceResourceResponse] = Field(default_factory=list)
    run_status: str | None = None
    warnings: list[GenerationWarning] = Field(default_factory=list)


class SourceEvidenceVisualCandidateResponse(TestCaseBaseModel):
    """Source Evidence 视觉候选安全响应，不返回本地路径或 token。"""

    ref: str
    type: str
    position: str = ""
    filename: str = ""
    status: str = ""
    selectable: bool = False
    recommended: bool = False
    selected: bool = False
    recommendation_reasons: list[str] = Field(default_factory=list)
    download_status: str = "pending"
    adoption_status: str = "unobserved"
    dimensions: dict[str, int] = Field(default_factory=dict)


class SourceEvidenceVisualCandidatesResponse(TestCaseBaseModel):
    """Source Evidence 视觉候选列表响应。"""

    items: list[SourceEvidenceVisualCandidateResponse] = Field(default_factory=list)
    recommended_refs: list[str] = Field(default_factory=list)
    selected_refs: list[str] = Field(default_factory=list)
    warnings: list[GenerationWarning] = Field(default_factory=list)
    run_status: str | None = None


class SourceEvidenceVisualSelectionRequest(TestCaseBaseModel):
    """替换式保存用户选择的视觉候选 ref。"""

    selected_refs: list[str] = Field(default_factory=list)


class SourceEvidenceObservationResponse(TestCaseBaseModel):
    """Source Evidence 视觉观察安全响应。"""

    id: int
    ref: str
    resource_id: int | None = None
    type: str = ""
    position: str = ""
    filename: str = ""
    status: str = "observed"
    summary: str = ""
    visible_text: str = ""
    confidence: float | None = Field(default=None, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)
    created_by: int | None = None
    created_at: str | None = None
    adopted_by: int | None = None
    adopted_at: str | None = None
    revoked_at: str | None = None


class SourceEvidenceObservationListResponse(TestCaseBaseModel):
    """Source Evidence 视觉观察列表响应。"""

    items: list[SourceEvidenceObservationResponse] = Field(default_factory=list)
    warnings: list[GenerationWarning] = Field(default_factory=list)
    run_status: str | None = None


class SourceEvidenceAdoptVisualEvidenceRequest(TestCaseBaseModel):
    """批量采纳已观察视觉证据。"""

    observation_ids: list[int] = Field(default_factory=list)


class SourceEvidenceCleanupAuditResource(TestCaseBaseModel):
    """Source Evidence 清理审计中的资源摘要。"""

    resource_id: int | None = None
    run_id: int | None = None
    project_id: int | None = None
    ref: str = ""
    type: str = ""
    filename: str = ""
    status: str = ""
    download_status: str = ""
    created_at: str | None = None
    cleaned_at: str | None = None


class SourceEvidenceCleanupAuditItem(TestCaseBaseModel):
    """Source Evidence Cleanup Audit Summary，不含已清理内容。"""

    run_id: int
    project_id: int
    source_type: str = ""
    source_identifier: str = ""
    source_title: str = ""
    status_before: str = ""
    status_after: str = "cleaned"
    created_by: int | None = None
    cleaned_by: int | None = None
    created_at: str | None = None
    expires_at: str | None = None
    cleaned_at: str | None = None
    error_summary: str = ""
    counts: dict[str, int] = Field(default_factory=dict)
    resources: list[SourceEvidenceCleanupAuditResource] = Field(default_factory=list)


class SourceEvidenceCleanupAuditListResponse(TestCaseBaseModel):
    """Source Evidence 清理审计列表响应。"""

    items: list[SourceEvidenceCleanupAuditItem] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1)
    offset: int = Field(default=0, ge=0)


class PlanningSnapshotLimits(TestCaseBaseModel):
    """策划案快照预算限制。"""

    max_chars: int = Field(default=80_000, ge=1)
    max_rows: int = Field(default=800, ge=1)
    max_columns: int = Field(default=80, ge=1)
    max_cell_chars: int = Field(default=300, ge=1)
    max_non_empty_cells: int = Field(default=12_000, ge=1)


class PlanningSnapshotCell(TestCaseBaseModel):
    """策划案快照中的单个单元格。"""

    row_index: int = Field(ge=1)
    column_index: int = Field(ge=1)
    column_name: str | None = None
    value: str = ""
    truncated: bool = False


class PlanningSnapshotRow(TestCaseBaseModel):
    """策划案快照中的一行。"""

    row_index: int = Field(ge=1)
    cells: list[PlanningSnapshotCell] = Field(default_factory=list)


class PlanningSnapshotRequest(TestCaseBaseModel):
    """读取一个 Planning Sheet 快照的请求。"""

    source_type: Literal["feishu", "uploaded_excel"]
    source: DataSource
    sheet_name: str = Field(min_length=1)
    limits: PlanningSnapshotLimits = Field(default_factory=PlanningSnapshotLimits)


class PlanningSnapshotResponse(TestCaseBaseModel):
    """读取后返回给页面和生成接口复用的受控快照。"""

    source_summary: str = ""
    sheet_name: str
    rows: list[PlanningSnapshotRow] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    non_empty_cell_count: int = Field(default=0, ge=0)
    truncated: bool = False
    warnings: list[GenerationWarning] = Field(default_factory=list)


class PlanningSnapshotBriefRequest(TestCaseBaseModel):
    """根据当前页面持有的 Planning Sheet Snapshot 生成 AI 整理稿。"""

    planning_snapshot: PlanningSnapshotResponse


class PlanningSnapshotBriefResponse(TestCaseBaseModel):
    """AI-Assisted Snapshot Brief 响应，不包含原始 prompt 或 provider 原文。"""

    brief_markdown: str = ""
    warnings: list[GenerationWarning] = Field(default_factory=list)


class TestCaseBlueprint(TestCaseBaseModel):
    """AI 生成用例前的只读测试设计蓝图。"""

    modules: list[dict[str, Any] | str] = Field(default_factory=list)
    flows: list[dict[str, Any] | str] = Field(default_factory=list)
    requirement_traces: list[dict[str, Any]] = Field(default_factory=list)
    coverage_dimensions: list[dict[str, Any] | str] = Field(default_factory=list)
    risks: list[dict[str, Any] | str] = Field(default_factory=list)
    unmapped_requirements: list[dict[str, Any] | str] = Field(default_factory=list)
    unsupported_or_unfounded_test_points: list[dict[str, Any] | str] = Field(
        default_factory=list
    )
    open_questions: list[dict[str, Any] | str] = Field(default_factory=list)
    warnings: list[GenerationWarning] = Field(default_factory=list)


class GeneratedTestCase(TestCaseBaseModel):
    """标准测试用例行。"""

    case_id: str = ""
    module: str = ""
    feature: str = ""
    scenario: str = ""
    title: str = ""
    preconditions: str = ""
    steps: str = ""
    expected_results: str = ""
    priority: str = "P2"
    case_type: str = ""
    source_requirement: str = ""
    config_source: str = ""
    planning_answer: str = ""
    initial_status: str = "未执行"
    bug_link: str = ""
    remarks: str = ""


class GeneratedCaseStats(TestCaseBaseModel):
    """由代码计算的生成结果统计。"""

    total: int = Field(default=0, ge=0)
    priority_counts: dict[str, int] = Field(default_factory=dict)
    module_counts: dict[str, int] = Field(default_factory=dict)
    case_type_counts: dict[str, int] = Field(default_factory=dict)
    warning_count: int = Field(default=0, ge=0)


class QaCaseMethodContext(TestCaseBaseModel):
    """V1 内置 QA Case Method 上下文说明。"""

    method_name: str = "QA Case Method"
    method_version: str = "v1"
    knowledge_library_note: str = "V1 未接入项目级 QA 知识库"
    dimensions: list[str] = Field(default_factory=list)


class RequirementTrace(TestCaseBaseModel):
    """需求来源与蓝图、用例之间的追踪关系。"""

    source_row_index: int | None = None
    source_fragment: str = ""
    blueprint_node: str = ""
    case_id: str = ""


class TestCaseGenerationRequest(TestCaseBaseModel):
    """根据策划案快照生成蓝图和用例的请求。"""

    planning_snapshot: PlanningSnapshotResponse
    source_evidence_run_id: int | None = Field(default=None, ge=1)
    adopted_visual_evidence_ids: list[int] = Field(default_factory=list)
    snapshot_brief_markdown: str | None = None
    reference_ids: list[int] = Field(default_factory=list)
    primary_reference_id: int | None = None
    primary_reference_sheet_name: str | None = None
    generation_options: dict[str, Any] = Field(default_factory=dict)


class TestCaseGenerationResponse(TestCaseBaseModel):
    """生成接口成功后的结构化响应。"""

    blueprint: TestCaseBlueprint
    cases: list[GeneratedTestCase] = Field(default_factory=list)
    warnings: list[GenerationWarning] = Field(default_factory=list)
    stats: GeneratedCaseStats
    export_columns: list[str] = Field(default_factory=list)
    requirement_trace: list[RequirementTrace] = Field(default_factory=list)
    method_context: QaCaseMethodContext = Field(default_factory=QaCaseMethodContext)
    primary_reference_profile: dict[str, Any] | None = None
    reference_context: dict[str, Any] = Field(default_factory=dict)


class TestCaseExportRequest(TestCaseBaseModel):
    """基于当前页面结果 stateless 导出 Excel 的请求。"""

    blueprint: TestCaseBlueprint
    cases: list[GeneratedTestCase] = Field(default_factory=list)
    warnings: list[GenerationWarning] = Field(default_factory=list)
    stats: GeneratedCaseStats
    export_columns: list[str] = Field(default_factory=list)
    primary_reference_profile: dict[str, Any] | None = None
    source_summary: str = ""
    source_evidence_run_id: int | None = Field(default=None, ge=1)
    adopted_visual_evidence_ids: list[int] = Field(default_factory=list)
    source_evidence_summary: str = ""
    evidence_summary: str = ""


class ReferenceProfileColumn(TestCaseBaseModel):
    """参考案例中的原始列与标准字段映射。"""

    index: int = Field(ge=1)
    original_name: str
    standard_field: str | None = None
    standard_label: str | None = None


class ReferenceSheetOption(TestCaseBaseModel):
    """Excel 参考案例中可用于画像的 Sheet。"""

    name: str
    reference_case_count: int = Field(ge=0)
    is_default: bool = False
    header_row_index: int = Field(ge=1)
    columns: list[ReferenceProfileColumn] = Field(default_factory=list)
    warnings: list[GenerationWarning] = Field(default_factory=list)


class ReferenceProfile(TestCaseBaseModel):
    """参考案例确定性画像，不包含 AI prompt 或 provider 原始响应。"""

    source_type: Literal["excel", "markdown", "text"]
    source_name: str
    default_sheet_name: str | None = None
    reference_case_count: int | None = Field(default=None, ge=0)
    columns: list[ReferenceProfileColumn] = Field(default_factory=list)
    sheet_options: list[ReferenceSheetOption] = Field(default_factory=list)
    warnings: list[GenerationWarning] = Field(default_factory=list)


class ReferenceCategoryCreateRequest(TestCaseBaseModel):
    """创建参考案例分类。"""

    name: str = Field(min_length=1, max_length=80)


class ReferenceCategoryUpdateRequest(TestCaseBaseModel):
    """重命名参考案例分类。"""

    name: str = Field(min_length=1, max_length=80)


class ReferenceCategoryResponse(TestCaseBaseModel):
    """参考案例分类响应。"""

    id: int
    name: str
    reference_count: int = Field(default=0, ge=0)


class ReferenceFileResponse(TestCaseBaseModel):
    """参考案例文件响应。"""

    id: int
    category_id: int | None = None
    category_name: str
    original_filename: str
    suffix: str
    size_bytes: int = Field(ge=0)
    profile: ReferenceProfile | None = None
    reference_case_count: int | None = Field(default=None, ge=0)
    default_sheet_name: str | None = None
    is_recommended_primary: bool = False
    created_at: str
    updated_at: str


class ReferenceCategoryListResponse(TestCaseBaseModel):
    """参考案例分类列表响应。"""

    items: list[ReferenceCategoryResponse] = Field(default_factory=list)


class ReferenceFileListResponse(TestCaseBaseModel):
    """参考案例文件列表响应。"""

    items: list[ReferenceFileResponse] = Field(default_factory=list)
