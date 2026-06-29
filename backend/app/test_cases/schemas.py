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
