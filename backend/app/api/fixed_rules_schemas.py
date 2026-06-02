"""固定规则模块接口模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from backend.app.api.schemas import DataSource, VariableTag


FixedRuleType = Literal[
    "fixed_value_compare",
    "regex_check",
    "not_null",
    "unique",
    "sequence_order_check",
    "cross_table_mapping",
    "composite_condition_check",
    "dual_composite_compare",
    "multi_composite_pipeline_check",
    "multi_composite_mapping_check",
    "package_items_compare",
]
FixedRuleOperator = Literal["eq", "ne", "gt", "lt"]
ExpectedValueMode = Literal["single", "set"]
SequenceDirection = Literal["asc", "desc"]
SequenceStartMode = Literal["auto", "manual"]
CompositeFilterOperator = Literal[
    "eq",
    "ne",
    "gt",
    "lt",
    "not_null",
    "contains",
    "not_contains",
]
CompositeAssertionOperator = Literal[
    "eq",
    "ne",
    "gt",
    "lt",
    "not_null",
    "regex",
    "unique",
    "duplicate_required",
]
CompositeValueSource = Literal["literal", "field"]
DualCompositeKeyCheckMode = Literal["baseline_only", "bidirectional"]
DualCompositeOperator = Literal["eq", "ne", "gt", "lt", "not_null"]
FixedRulesConfigIssueLevel = Literal["warning", "error"]
PackageParseStrategy = Literal["auto", "rule", "ai"]
PackageAiParseMode = Literal["auto", "enabled", "disabled"]
PackageValidationScope = Literal["all", "specified"]
PackageParseStatus = Literal["success", "failed"]
PackageParseMode = Literal["rule", "ai"]
PackagePreviewStrategyUsed = Literal["manual", "ai"]
PackageItemsParseStrategy = PackageParseStrategy
PackageItemsAiParseMode = PackageAiParseMode
PackageItemsValidationScope = PackageValidationScope


UNGROUPED_GROUP_ID = "ungrouped"
UNGROUPED_GROUP_NAME = "未分组"


class FixedRuleBinding(BaseModel):
    """兼容旧版固定规则配置中的文件级绑定结构。"""

    model_config = ConfigDict(extra="forbid")

    file_path: str
    sheet: str
    column: str


class FixedRuleGroup(BaseModel):
    """描述一组固定规则的分组信息。"""

    model_config = ConfigDict(extra="forbid")

    group_id: str
    group_name: str
    builtin: bool = False


class CompositeCondition(BaseModel):
    """描述组合变量条件分支校验中的单条条件。"""

    model_config = ConfigDict(extra="forbid")

    condition_id: str
    field: str
    operator: CompositeFilterOperator | CompositeAssertionOperator
    value_source: CompositeValueSource | None = None
    expected_value: str | None = None
    expected_value_mode: ExpectedValueMode | None = None
    expected_field: str | None = None


class CompositeBranch(BaseModel):
    """描述组合变量规则中的单个条件分支。"""

    model_config = ConfigDict(extra="forbid")

    branch_id: str
    filters: list[CompositeCondition] = Field(default_factory=list)
    assertions: list[CompositeCondition] = Field(default_factory=list)


class CompositeRuleConfig(BaseModel):
    """描述组合变量条件分支校验的完整配置。"""

    model_config = ConfigDict(extra="forbid")

    global_filters: list[CompositeCondition] = Field(default_factory=list)
    branches: list[CompositeBranch] = Field(default_factory=list)


class MultiCompositePipelineNode(BaseModel):
    """描述多组合变量串行校验中的单个变量节点。"""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    variable_tag: str
    display_field: str | None = None
    filters: list[CompositeCondition] = Field(default_factory=list)
    assertions: list[CompositeCondition] = Field(default_factory=list)


class MultiCompositePipelineConfig(BaseModel):
    """描述多组合变量串行校验的完整节点队列。"""

    model_config = ConfigDict(extra="forbid")

    nodes: list[MultiCompositePipelineNode] = Field(default_factory=list)


class MultiCompositeMappingRange(BaseModel):
    """描述旧版多组映射字段检查中的单段 Excel 行号范围。"""

    model_config = ConfigDict(extra="forbid")

    range_id: str
    start_row: int
    end_row: int
    expected_value: str


class MultiCompositeMappingFieldCheck(BaseModel):
    """描述旧版多组映射校验中某一列字段的默认值与例外范围。"""

    model_config = ConfigDict(extra="forbid")

    check_id: str
    field: str
    default_expected_value: str
    filters: list[CompositeCondition] = Field(default_factory=list)
    ranges: list[MultiCompositeMappingRange] = Field(default_factory=list)


class MultiCompositeMappingExclusionRange(BaseModel):
    """描述多组映射筛选失败后可排除的 Excel 行号范围。"""

    model_config = ConfigDict(extra="forbid")

    range_id: str
    start_row: int
    end_row: int
    expected_value: str | None = None


class MultiCompositeMappingFilter(CompositeCondition):
    """描述多组映射校验中的单条筛选检查。"""

    exclusion_ranges: list[MultiCompositeMappingExclusionRange] = Field(default_factory=list)


class MultiCompositeMappingNode(BaseModel):
    """描述多组映射校验中的单个组合变量节点。"""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    variable_tag: str
    display_field: str | None = None
    filters: list[MultiCompositeMappingFilter] = Field(default_factory=list)
    field_checks: list[MultiCompositeMappingFieldCheck] = Field(default_factory=list, exclude=True)
    field: str | None = Field(default=None, exclude=True)
    ranges: list[MultiCompositeMappingRange] | None = Field(default=None, exclude=True)


class MultiCompositeMappingConfig(BaseModel):
    """描述多组映射校验的完整节点队列。"""

    model_config = ConfigDict(extra="forbid")

    nodes: list[MultiCompositeMappingNode] = Field(default_factory=list)


class DualCompositeComparison(BaseModel):
    """描述双组合变量比对中的单条字段比较规则。"""

    model_config = ConfigDict(extra="forbid")

    comparison_id: str
    left_field: str
    operator: DualCompositeOperator
    right_field: str


def _normalize_package_parse_strategy(value: object) -> object:
    """兼容外部 manual 命名，内部继续使用现有 parser 的 rule。"""
    if isinstance(value, str):
        normalized = value.strip()
        return "rule" if normalized == "manual" else normalized
    return value


def _normalize_package_ai_parse_mode(value: object) -> object:
    """兼容外部 on/off 命名，内部继续使用 enabled/disabled。"""
    if isinstance(value, str):
        normalized = value.strip()
        if normalized == "on":
            return "enabled"
        if normalized == "off":
            return "disabled"
        return normalized
    return value


def _strip_optional_string(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


class PackageItemsParseConfig(BaseModel):
    """描述礼包规划表预解析配置。"""

    model_config = ConfigDict(extra="forbid")

    feishu_source_id: str
    feishu_sheet_id: str
    feishu_sheet_name: str | None = None
    parse_strategy: PackageParseStrategy = "auto"
    ai_parse_mode: PackageAiParseMode = "auto"
    validation_scope: PackageValidationScope | None = None
    package_id_filter: str | None = None

    @field_validator("feishu_source_id", "feishu_sheet_id", mode="before")
    @classmethod
    def _strip_required_string(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("feishu_sheet_name", "package_id_filter", mode="before")
    @classmethod
    def _strip_optional_text(cls, value: object) -> object:
        return _strip_optional_string(value)

    @field_validator("parse_strategy", mode="before")
    @classmethod
    def _normalize_parse_strategy(cls, value: object) -> object:
        return _normalize_package_parse_strategy(value)

    @field_validator("ai_parse_mode", mode="before")
    @classmethod
    def _normalize_ai_parse_mode(cls, value: object) -> object:
        return _normalize_package_ai_parse_mode(value)


class PackageFieldMapping(BaseModel):
    """parser 内部使用的礼包明细字段名映射。"""

    model_config = ConfigDict(extra="forbid")

    package_id: str = ""
    item_id: str = ""
    count: str = ""


class PackageDetailRange(BaseModel):
    """描述礼包明细区域的 Sheet 行号范围。"""

    model_config = ConfigDict(extra="forbid")

    header_row: int
    start_row: int
    end_row: int


class PackagePlanItemRow(BaseModel):
    """描述从礼包规划 Sheet 中抽取出的单条道具明细。"""

    model_config = ConfigDict(extra="forbid")

    row_index: int
    package_id: str
    item_id: str
    count: int
    raw_row: list[Any] = Field(default_factory=list)


class PackageItemsPreviewDetailRow(BaseModel):
    """描述礼包规划解析预览中的单条明细。"""

    model_config = ConfigDict(extra="forbid")

    row_index: int
    package_id: str
    item_id: str
    count: str

    @field_validator("count", mode="before")
    @classmethod
    def _stringify_count(cls, value: object) -> str:
        return "" if value is None else str(value)


class _PackageSheetParseBase(BaseModel):
    """礼包 Sheet 解析结果的 parser 内部基础结构。"""

    model_config = ConfigDict(extra="forbid")

    parse_status: PackageParseStatus = "failed"
    parse_mode: PackageParseMode = "rule"
    ai_used: bool = False
    cache_hit: bool = False
    confidence: float = 0.0
    header_rows: list[int] = Field(default_factory=list)
    detail_ranges: list[PackageDetailRange] = Field(default_factory=list)
    field_mapping: PackageFieldMapping = Field(default_factory=PackageFieldMapping)
    package_ids: list[str] = Field(default_factory=list)
    package_count: int = 0
    detail_row_count: int = 0
    rows: list[PackagePlanItemRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PackageSheetParseResult(_PackageSheetParseBase):
    """描述规则或 AI 结构识别后的确定性抽取结果。"""


class PackageItemsPreviewResult(_PackageSheetParseBase):
    """描述礼包规划表预解析结果，保留 parser 既有字段名。"""

    detail_rows: list[PackageItemsPreviewDetailRow] = Field(default_factory=list)
    raw_sheet_name: str | None = None


class PackageItemsPreviewFieldMapping(BaseModel):
    """面向个人礼包弹窗预览接口的字段映射结构。"""

    model_config = ConfigDict(extra="forbid")

    package_id_column: str | None = Field(
        default=None,
        validation_alias=AliasChoices("package_id_column", "package_id"),
    )
    item_id_column: str | None = Field(
        default=None,
        validation_alias=AliasChoices("item_id_column", "item_id"),
    )
    count_column: str | None = Field(
        default=None,
        validation_alias=AliasChoices("count_column", "count"),
    )
    header_row_index: int | None = None
    detail_start_row_index: int | None = None
    detail_end_row_index: int | None = None

    @field_validator("package_id_column", "item_id_column", "count_column", mode="before")
    @classmethod
    def _strip_optional_column(cls, value: object) -> object:
        return _strip_optional_string(value)


class PackageItemsPreviewRequest(BaseModel):
    """面向个人礼包弹窗的预览请求。"""

    model_config = ConfigDict(extra="forbid")

    feishu_source_id: str
    sheet_id: str = Field(validation_alias=AliasChoices("sheet_id", "feishu_sheet_id"))
    feishu_sheet_name: str | None = None
    parse_strategy: PackageParseStrategy = "auto"
    ai_parse_mode: PackageAiParseMode = "auto"
    validation_scope: PackageValidationScope = "all"
    package_id_filter: str | None = None

    @field_validator("feishu_source_id", "sheet_id", mode="before")
    @classmethod
    def _strip_required_string(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("feishu_sheet_name", "package_id_filter", mode="before")
    @classmethod
    def _strip_optional_text(cls, value: object) -> object:
        return _strip_optional_string(value)

    @field_validator("parse_strategy", mode="before")
    @classmethod
    def _normalize_parse_strategy(cls, value: object) -> object:
        return _normalize_package_parse_strategy(value)

    @field_validator("ai_parse_mode", mode="before")
    @classmethod
    def _normalize_ai_parse_mode(cls, value: object) -> object:
        return _normalize_package_ai_parse_mode(value)


class PackageItemsPreviewResponse(BaseModel):
    """面向个人礼包弹窗的预览响应。"""

    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    field_mapping: PackageItemsPreviewFieldMapping | None = None
    package_ids: list[str] = Field(default_factory=list)
    detail_row_count: int = 0
    preview_rows: list[PackageItemsPreviewDetailRow] = Field(default_factory=list)
    raw_sheet_name: str | None = None
    parse_strategy_used: PackagePreviewStrategyUsed | None = None
    ai_used: bool = False

    @field_validator("parse_strategy_used", mode="before")
    @classmethod
    def _normalize_parse_strategy_used(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return "manual" if normalized == "rule" else normalized
        return value


class FixedRuleDefinition(BaseModel):
    """描述一条固定规则定义。"""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    group_id: str
    rule_name: str
    target_variable_tag: str | None = None
    display_field: str | None = None
    binding: FixedRuleBinding | None = None
    rule_type: FixedRuleType = "fixed_value_compare"
    operator: FixedRuleOperator | None = None
    expected_value: str | None = None
    expected_value_mode: ExpectedValueMode | None = None
    reference_variable_tag: str | None = None
    sequence_direction: SequenceDirection | None = None
    sequence_step: str | None = None
    sequence_start_mode: SequenceStartMode | None = None
    sequence_start_value: str | None = None
    composite_config: CompositeRuleConfig | None = None
    key_check_mode: DualCompositeKeyCheckMode | None = None
    left_key_field: str | None = None
    right_key_field: str | None = None
    comparisons: list[DualCompositeComparison] = Field(default_factory=list)
    left_filters: list[CompositeCondition] = Field(default_factory=list)
    right_filters: list[CompositeCondition] = Field(default_factory=list)
    pipeline_config: MultiCompositePipelineConfig | None = None
    mapping_config: MultiCompositeMappingConfig | None = None
    package_parse_config: PackageItemsParseConfig | None = None
    left_package_field: str | None = None
    left_item_field: str | None = None
    left_count_field: str | None = None
    right_package_field: str | None = None
    right_items_field: str | None = None
    package_id_filter: str | None = None

    @field_validator(
        "left_package_field",
        "left_item_field",
        "left_count_field",
        "right_package_field",
        "right_items_field",
        "package_id_filter",
        mode="before",
    )
    @classmethod
    def _strip_optional_package_string(cls, value: object) -> object:
        return _strip_optional_string(value)


class FixedRulesConfigIssue(BaseModel):
    """描述固定规则配置中可修复、但不阻断页面读取的问题。"""

    model_config = ConfigDict(extra="forbid")

    level: FixedRulesConfigIssueLevel = "warning"
    source_id: str | None = None
    variable_tag: str | None = None
    rule_id: str | None = None
    message: str


class FixedRulesConfig(BaseModel):
    """描述固定规则页的完整持久化配置。"""

    model_config = ConfigDict(extra="forbid")

    version: int = 6
    configured: bool = False
    sources: list[DataSource] = Field(default_factory=list)
    variables: list[VariableTag] = Field(default_factory=list)
    groups: list[FixedRuleGroup] = Field(default_factory=list)
    rules: list[FixedRuleDefinition] = Field(default_factory=list)
    local_path_replacement_presets: list[str] = Field(default_factory=list)
    selected_local_path_replacement_preset: str | None = None
    svn_path_replacement_presets: list[str] = Field(default_factory=list)
    selected_svn_path_replacement_preset: str | None = None
    path_replacement_presets: list[str] = Field(default_factory=list)
    selected_path_replacement_preset: str | None = None


class FixedRulesExecuteRequest(BaseModel):
    """描述固定规则执行时允许传入的可选规则筛选参数。"""

    model_config = ConfigDict(extra="forbid")

    selected_rule_ids: list[str] | None = None
    page: int | None = Field(default=None, ge=1)
    size: int | None = Field(default=None, ge=1, le=200)


class FixedRulesImportRequest(BaseModel):
    """描述从个人校验导入项目校验的请求。"""

    model_config = ConfigDict(extra="forbid")

    selected_rule_ids: list[str] = Field(default_factory=list)
    source_overrides: dict[str, DataSource] = Field(default_factory=dict)
    variable_tag_overrides: dict[str, str] = Field(default_factory=dict)
    preview_token: str | None = None
