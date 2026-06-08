"""接口请求模型定义。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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
ExpectedValueMode = Literal["single", "set"]


class CompositeCondition(BaseModel):
    """描述组合变量筛选或断言中的单条条件。"""

    model_config = ConfigDict(extra="forbid")

    condition_id: str
    field: str
    operator: CompositeFilterOperator | CompositeAssertionOperator
    value_source: CompositeValueSource | None = None
    expected_value: str | None = None
    expected_value_mode: ExpectedValueMode | None = None
    expected_field: str | None = None


class DataSource(BaseModel):
    """描述单个数据源的基础配置。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["local_excel", "local_csv", "feishu", "svn"]
    path: str | None = None
    url: str | None = None
    pathOrUrl: str | None = None
    token: str | None = None


class VariableTag(BaseModel):
    """描述变量标签与数据源字段之间的映射关系。"""

    model_config = ConfigDict(extra="forbid")

    tag: str
    source_id: str
    sheet: str
    variable_kind: Literal["single", "composite"] = "single"
    column: str | None = None
    columns: list[str] | None = None
    key_column: str | None = None
    filters: list[CompositeCondition] = Field(default_factory=list)
    append_index_to_key: bool = False
    expected_type: Literal["int", "str", "json"] | None = None


class ValidationRule(BaseModel):
    """描述单条校验规则及其参数。"""

    model_config = ConfigDict(extra="forbid")

    rule_id: str | None = None
    rule_type: str
    params: dict[str, Any] = Field(default_factory=dict)


class TaskTree(BaseModel):
    """描述一次执行请求中包含的数据源、变量和规则集合。"""

    model_config = ConfigDict(extra="forbid")

    sources: list[DataSource] = Field(default_factory=list)
    variables: list[VariableTag] = Field(default_factory=list)
    rules: list[ValidationRule] = Field(default_factory=list)
    selected_rule_ids: list[str] | None = None
    page: int | None = Field(default=None, ge=1)
    size: int | None = Field(default=None, ge=1, le=200)
