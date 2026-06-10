"""配置表查询核心服务内部数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


ConfigLookupStatus = Literal["hit", "candidates", "not_found", "ai_unavailable"]


@dataclass(frozen=True)
class ConfigLookupRequest:
    """配置表查询服务请求。"""

    project_id: int
    query_type: str
    versioned_config_folder: str
    lookup_input: str


@dataclass(frozen=True)
class ConfigLookupThresholds:
    """项目级 AI 名称匹配阈值。"""

    auto_match_threshold: float = 0.9
    candidate_threshold: float = 0.6
    max_candidates: int = 10


@dataclass(frozen=True)
class ConfigLookupFieldValue:
    """单个输出字段。"""

    field: str
    label: str
    value: str


@dataclass(frozen=True)
class ConfigLookupCandidate:
    """AI 名称匹配候选，候选只能来自主配置文件。"""

    key: str
    page: str
    id_value: str
    name_value: str
    score: float = 0.0
    row: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)
    page_config: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class ConfigLookupAiScore:
    """AI 对候选的排序分数。"""

    candidate_key: str
    score: float


@dataclass(frozen=True)
class ConfigLookupResultItem:
    """查询命中后返回的一条详情结果。"""

    query_type: str
    page: str
    id_value: str
    name_value: str
    fields: list[ConfigLookupFieldValue]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConfigLookupAiInfo:
    """本次查询的 AI 使用情况。"""

    used: bool = False
    unavailable_reason: str | None = None
    thresholds: ConfigLookupThresholds = field(default_factory=ConfigLookupThresholds)


@dataclass(frozen=True)
class ConfigLookupResponse:
    """配置表查询服务响应。"""

    status: ConfigLookupStatus
    message: str
    results: list[ConfigLookupResultItem] = field(default_factory=list)
    candidates: list[ConfigLookupCandidate] = field(default_factory=list)
    ai: ConfigLookupAiInfo = field(default_factory=ConfigLookupAiInfo)


class ConfigLookupAiMatcher(Protocol):
    """AI 名称匹配器协议，便于测试注入 fake。"""

    async def rank(
        self,
        *,
        lookup_input: str,
        candidates: list[ConfigLookupCandidate],
    ) -> list[ConfigLookupAiScore]:
        """对候选打分并按相关性返回。"""


class ConfigLookupFileResolver(Protocol):
    """配置文件解析器协议，后续命令接入时可替换默认 SVN/local 实现。"""

    def resolve(self, *, query_root_url: str, version_folder: str, file_name: str) -> str:
        """返回本地可读取文件路径。"""
