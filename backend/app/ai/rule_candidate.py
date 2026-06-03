"""AI 规则候选识别与批判收窄。

该模块只做纯算法判断：把用户输入拆成候选规则，给当前规则库打分，
并输出是否可继续编译、需要补充或应拒绝。不读写数据库，也不生成最终规则。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Literal

from backend.app.ai.hint_extractor import extract_workflow_hints_from_text
from backend.app.ai.workflow_hints import AiRuleWorkflowHints, MissingItem, has_complete_dual_hints
from backend.app.api.fixed_rules_schemas import FixedRuleType


RuleCritiqueVerdict = Literal["ready", "needs_input", "rejected"]

CONFIDENT_SCORE_THRESHOLD = 0.75
AMBIGUOUS_SCORE_THRESHOLD = 0.45
MIN_SCORE_GAP = 0.15

SUPPORTED_RULE_TYPES: tuple[FixedRuleType, ...] = (
    "not_null",
    "unique",
    "regex_check",
    "sequence_order_check",
    "fixed_value_compare",
    "cross_table_mapping",
    "composite_condition_check",
    "dual_composite_compare",
    "multi_composite_pipeline_check",
    "multi_composite_mapping_check",
    "package_items_compare",
)

UNSUPPORTED_KEYWORDS = ("公式", "聚合", "平均", "求和", "脚本", "计算后", "跨行统计")


@dataclass(frozen=True)
class RuleTypeSpec:
    """当前规则库中某一类规则的识别规格。"""

    rule_type: FixedRuleType
    keywords: tuple[str, ...]
    required_slots: tuple[str, ...]
    positive_slots: tuple[str, ...] = ()
    negative_slots: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuleCandidate:
    """从用户输入中拆出的一个候选规则片段。"""

    candidate_id: str
    text: str
    hints: AiRuleWorkflowHints


@dataclass(frozen=True)
class RuleCandidateScore:
    """候选规则对某个 rule_type 的可解释评分。"""

    rule_type: FixedRuleType
    score: float
    matched_signals: list[str] = field(default_factory=list)
    missing_slots: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RuleCritiqueResult:
    """候选批判结果，供 rule-draft 链路决定下一步。"""

    verdict: RuleCritiqueVerdict
    candidate: RuleCandidate
    scores: list[RuleCandidateScore]
    workflow_hints: AiRuleWorkflowHints
    confidence: float
    rule_type: FixedRuleType | None
    missing: list[MissingItem] = field(default_factory=list)
    rejection_reason: str | None = None
    reasoning_summary: str = ""
    should_stop: bool = False

    def prompt_summary(self) -> str:
        top_scores = "；".join(
            f"{item.rule_type}:{item.score:.2f}" for item in self.scores[:3]
        )
        missing_text = "；".join(item.message for item in self.missing)
        return "\n".join(
            item
            for item in (
                "规则候选批判：",
                f"候选文本：{self.candidate.text}",
                f"候选评分：{top_scores}",
                f"批判结论：{self.reasoning_summary}",
                f"缺口：{missing_text}" if missing_text else "",
            )
            if item
        )


RULE_TYPE_SPECS: tuple[RuleTypeSpec, ...] = (
    RuleTypeSpec("not_null", ("不能为空", "非空", "必填", "not null", "not_null"), ("target_field",)),
    RuleTypeSpec("unique", ("唯一", "不能重复", "不可重复", "unique"), ("target_field",)),
    RuleTypeSpec(
        "fixed_value_compare",
        ("只能是", "必须是", "等于", "不等于", "大于", "小于", "=", "!=", ">", "<"),
        ("target_field", "expected_value"),
    ),
    RuleTypeSpec("regex_check", ("正则", "格式", "匹配", "regex"), ("target_field", "regex")),
    RuleTypeSpec(
        "sequence_order_check",
        ("升序", "降序", "递增", "递减", "连续", "步长", "顺序", "sequence"),
        ("target_field", "sequence"),
    ),
    RuleTypeSpec(
        "cross_table_mapping",
        ("存在于", "引用表", "字典表", "字典变量", "包含(in)", " in "),
        ("target_field", "reference"),
    ),
    RuleTypeSpec(
        "composite_condition_check",
        ("筛选", "过滤", "当", "如果", "命中筛选", "组合分支"),
        ("filter", "assertion"),
        positive_slots=("composite_signal",),
    ),
    RuleTypeSpec(
        "dual_composite_compare",
        ("两组", "两个配置", "两份配置", "相等", "一致", "按 key", "以key", "以 key"),
        ("dual_filters", "key", "compare_fields"),
    ),
    RuleTypeSpec(
        "multi_composite_pipeline_check",
        ("多组串行", "多节点串行", "多级链路", "链路", "pipeline"),
        ("multi_node",),
    ),
    RuleTypeSpec(
        "multi_composite_mapping_check",
        ("多组映射", "多节点映射", "映射校验", "mapping"),
        ("multi_node",),
    ),
    RuleTypeSpec(
        "package_items_compare",
        ("IAP礼包", "IAP 礼包", "礼包校验", "礼包道具", "STR_Items", "package_items_compare"),
        ("package_items",),
    ),
)


def build_rule_candidates(
    description: str,
    workflow_hints: AiRuleWorkflowHints | None = None,
) -> list[RuleCandidate]:
    """根据固定模板和常见规则分隔符拆出候选规则。"""
    text = description.strip()
    base_hints = workflow_hints or AiRuleWorkflowHints()
    if not text:
        return [
            RuleCandidate(
                candidate_id="candidate-1",
                text="",
                hints=base_hints,
            )
        ]

    sections = _parse_template_sections(text)
    candidates: list[str] = []
    if sections:
        validation = (
            sections.get("校验规则")
            or sections.get("判定")
            or sections.get("最终判定")
            or sections.get("校验判定")
            or sections.get("断言")
            or ""
        )
        if validation or sections.get("规则类型") or sections.get("目标字段"):
            candidates.append(
                "\n".join(
                    [
                        f"数据源：{sections.get('数据源', '')}".strip(),
                        f"sheet分页：{sections.get('sheet分页', '')}".strip(),
                        f"变量选择：{sections.get('变量选择', '')}".strip(),
                        "",
                        f"规则类型：{sections.get('规则类型') or sections.get('rule_type') or _leading_rule_type(text) or ''}".strip(),
                        "",
                        f"目标字段：{sections.get('目标字段') or sections.get('目标') or sections.get('目标列名') or sections.get('校验字段') or ''}".strip(),
                        f"筛选条件：{sections.get('筛选') or sections.get('筛选条件') or _join_legacy_filters(sections)}".strip(),
                        f"左侧筛选：{sections.get('左侧筛选') or ''}".strip(),
                        f"右侧筛选：{sections.get('右侧筛选') or ''}".strip(),
                        f"Key字段：{sections.get('Key') or sections.get('Key字段') or sections.get('Key 字段') or sections.get('Key值选择') or sections.get('Key选择') or sections.get('Key值') or sections.get('选择Key') or sections.get('关联Key') or _legacy_key_from_filters(sections)}".strip(),
                        f"引用对象：{sections.get('引用对象', '')}".strip(),
                        f"比较字段：{sections.get('比较字段', '')}".strip(),
                        "",
                        f"校验规则：{validation}",
                        f"规则参数：{sections.get('规则参数', '')}".strip(),
                    ]
                )
            )
        rule_sections = [
            value
            for label, value in sections.items()
            if re.match(r"规则\d+", label) and value.strip()
        ]
        candidates.extend(rule_sections)

    if not candidates:
        candidates = _split_free_text_candidates(text)
    if not candidates:
        candidates = [text]

    result: list[RuleCandidate] = []
    for index, candidate_text in enumerate(_dedupe_texts(candidates), start=1):
        merged_hints = _merge_hints(base_hints, extract_workflow_hints_from_text(candidate_text))
        result.append(
            RuleCandidate(
                candidate_id=f"candidate-{index}",
                text=candidate_text.strip(),
                hints=merged_hints,
            )
        )
    return result


def rank_rule_candidates(candidate: RuleCandidate) -> list[RuleCandidateScore]:
    """为一个候选片段计算当前规则库的评分。"""
    slots = _collect_slots(candidate)
    return sorted(
        (_score_rule_type(candidate, spec, slots) for spec in RULE_TYPE_SPECS),
        key=lambda item: item.score,
        reverse=True,
    )


def critique_rule_candidate(
    description: str,
    *,
    workflow_hints: AiRuleWorkflowHints | None = None,
) -> RuleCritiqueResult:
    """批判用户输入，返回是否可收窄到明确规则类型。"""
    candidates = build_rule_candidates(description, workflow_hints)
    ranked_candidates = [
        (candidate, rank_rule_candidates(candidate)) for candidate in candidates
    ]
    candidate, scores = max(ranked_candidates, key=lambda item: item[1][0].score)
    best = scores[0]
    second = scores[1] if len(scores) > 1 else None
    gap = best.score - (second.score if second else 0)

    if _looks_like_unsupported(candidate.text):
        return RuleCritiqueResult(
            verdict="rejected",
            candidate=candidate,
            scores=scores,
            workflow_hints=candidate.hints,
            confidence=max(best.score, 0.4),
            rule_type=best.rule_type if best.score >= AMBIGUOUS_SCORE_THRESHOLD else None,
            rejection_reason="当前输入包含聚合、平均值、公式、求和或跨行统计等语义，现有 11 类规则暂不能稳定表达。",
            reasoning_summary="规则批判发现当前需求超出现有规则库能力，已阻止误添加。",
            should_stop=True,
        )

    multi_assertions = _detect_final_assertion_conflicts(candidate.text)
    if len(multi_assertions) >= 2:
        return RuleCritiqueResult(
            verdict="needs_input",
            candidate=candidate,
            scores=scores,
            workflow_hints=candidate.hints,
            confidence=best.score,
            rule_type=best.rule_type,
            missing=[
                MissingItem(
                    kind="rule",
                    message=(
                        "当前校验规则同时包含多个最终断言："
                        f"{'、'.join(multi_assertions)}。请拆成多条规则，或只保留一个最终校验规则。"
                    ),
                    suggested_action="edit_description",
                )
            ],
            reasoning_summary="规则批判发现多个最终断言混在同一条规则中，暂不自动添加，避免误判规则类型。",
            should_stop=True,
        )

    if best.score < AMBIGUOUS_SCORE_THRESHOLD:
        return RuleCritiqueResult(
            verdict="needs_input",
            candidate=candidate,
            scores=scores,
            workflow_hints=candidate.hints,
            confidence=best.score,
            rule_type=None,
            missing=[
                MissingItem(
                    kind="rule",
                    message="当前描述无法稳定匹配现有规则类型，请补充非空、唯一、固定值、正则、引用表或按 Key 对比等明确口径。",
                    suggested_action="edit_description",
                )
            ],
            reasoning_summary="规则批判未找到足够强的规则类型信号。",
            should_stop=False,
        )

    if best.score < CONFIDENT_SCORE_THRESHOLD or gap < MIN_SCORE_GAP:
        conflict_text = f"{best.rule_type} 与 {second.rule_type} 接近" if second else str(best.rule_type)
        missing_slots = "、".join(_slot_label(slot) for slot in best.missing_slots)
        return RuleCritiqueResult(
            verdict="needs_input",
            candidate=candidate,
            scores=scores,
            workflow_hints=candidate.hints,
            confidence=best.score,
            rule_type=best.rule_type,
            missing=[
                MissingItem(
                    kind="rule" if not best.missing_slots else "parameter",
                    message=(
                        f"当前规则候选仍有歧义：{conflict_text}。"
                        f"{'缺少：' + missing_slots + '。' if missing_slots else ''}"
                        "请补充筛选条件、目标字段、Key、比较字段或期望值后重试。"
                    ),
                    suggested_action="edit_description",
                )
            ],
            reasoning_summary="规则批判已缩小范围，但候选分数不足或与第二候选过近。",
            should_stop=False,
        )

    narrowed_hints = candidate.hints.model_copy(update={"rule_type_hint": best.rule_type})
    return RuleCritiqueResult(
        verdict="ready",
        candidate=candidate,
        scores=scores,
        workflow_hints=narrowed_hints,
        confidence=best.score,
        rule_type=best.rule_type,
        reasoning_summary=(
            f"规则批判已将候选收窄为 {best.rule_type}，"
            f"评分 {best.score:.2f}，领先第二候选 {gap:.2f}。"
        ),
        should_stop=False,
    )


def _score_rule_type(
    candidate: RuleCandidate,
    spec: RuleTypeSpec,
    slots: dict[str, bool],
) -> RuleCandidateScore:
    text = candidate.text.lower()
    matched_signals: list[str] = []
    missing_slots: list[str] = []
    conflicts: list[str] = []
    score = 0.0

    if candidate.hints.rule_type_hint == spec.rule_type:
        if _has_explicit_rule_type_signal(candidate.text, spec.rule_type):
            score += 0.45
            matched_signals.append(f"显式规则类型 {spec.rule_type}")
        else:
            score += 0.25
            matched_signals.append(f"推断规则类型 {spec.rule_type}")

    matched_keywords = [
        keyword for keyword in spec.keywords if keyword.lower() in text or keyword in candidate.text
    ]
    if matched_keywords:
        score += min(0.3, 0.1 + len(matched_keywords) * 0.08)
        matched_signals.append(f"关键词：{', '.join(matched_keywords[:4])}")

    required_slots = list(spec.required_slots)
    if required_slots:
        matched_required = [slot for slot in required_slots if slots.get(slot)]
        missing_slots = [slot for slot in required_slots if not slots.get(slot)]
        score += 0.35 * (len(matched_required) / len(required_slots))
        if matched_required:
            matched_signals.append(f"槽位：{', '.join(_slot_label(slot) for slot in matched_required)}")

    positive_slots = [slot for slot in spec.positive_slots if slots.get(slot)]
    score += min(0.1, len(positive_slots) * 0.05)
    for slot in spec.negative_slots:
        if slots.get(slot):
            score -= 0.1
            conflicts.append(f"存在不适合 {spec.rule_type} 的 {_slot_label(slot)}")

    if slots.get("source") and slots.get("sheet"):
        score += 0.05
    if spec.rule_type in {"not_null", "unique"} and slots.get("filter"):
        score -= 0.12
        conflicts.append("单变量规则不应混入筛选条件")
    if spec.rule_type == "regex_check" and slots.get("filter"):
        score -= 0.08
        conflicts.append("带筛选的格式校验更像组合分支校验")
    if (
        spec.rule_type == "composite_condition_check"
        and slots.get("filter")
        and slots.get("assertion")
        and candidate.hints.assertion_value_source == "field"
        and candidate.hints.assertion_expected_field
    ):
        score += 0.1
        matched_signals.append("字段对字段断言")

    return RuleCandidateScore(
        rule_type=spec.rule_type,
        score=round(max(0.0, min(score, 0.98)), 4),
        matched_signals=matched_signals,
        missing_slots=missing_slots,
        conflicts=conflicts,
    )


def _collect_slots(candidate: RuleCandidate) -> dict[str, bool]:
    hints = candidate.hints
    text = candidate.text
    return {
        "source": bool(hints.source_id or hints.source_url),
        "sheet": bool(hints.sheet),
        "target_field": bool(hints.target_field or hints.assertion_field or hints.composite_columns),
        "expected_value": bool(
            hints.expected_value
            or hints.assertion_value
            or re.search(r"(只能是|必须是|等于|不等于|大于|小于|=|!=|>|<)", text)
        ),
        "regex": bool(hints.regex_pattern or re.search(r"(正则|格式|匹配|regex)", text, re.IGNORECASE)),
        "sequence": bool(hints.sequence_direction or re.search(r"(升序|降序|递增|递减|连续|步长|顺序)", text)),
        "reference": bool(
            hints.reference_field
            or hints.reference_sheet
            or hints.reference_variable_tag
            or re.search(r"(存在于|引用表|字典表|字典变量|包含\(in\))", text)
        ),
        "filter": bool(
            hints.filters
            or
            (hints.filter_field and hints.filter_value)
            or (hints.left_filter_field and hints.left_filter_value)
            or re.search(r"(筛选|过滤|当|如果)", text)
        ),
        "assertion": bool(
            hints.assertion_field
            or hints.assertion_value
            or hints.target_field
            or re.search(r"(校验|检查|判断|不能为空|不能重复|只能是|必须|格式|正则)", text)
        ),
        "dual_filters": bool(
            hints.left_filter_field
            and hints.left_filter_value
            and hints.right_filter_field
            and hints.right_filter_value
        ),
        "key": bool(hints.key_column or hints.left_key_field or hints.right_key_field),
        "compare_fields": bool(hints.compare_fields),
        "multi_node": bool(hints.pipeline_nodes or hints.mapping_nodes or re.search(r"(多组|多节点|链路)", text)),
        "package_items": bool(re.search(r"(IAP\s*礼包|礼包校验|礼包道具|STR_Items)", text, re.IGNORECASE)),
        "composite_signal": bool(
            hints.filters
            or hints.filter_field
            or hints.key_column
            or hints.display_field
            or len(hints.composite_columns) >= 2
        ),
    }


def _parse_template_sections(text: str) -> dict[str, str]:
    labels = (
        "数据源",
        "sheet分页",
        "变量选择",
        "规则类型",
        "rule_type",
        "目标字段",
        "目标",
        "目标列名",
        "校验字段",
        "筛选条件",
        "筛选",
        "左侧筛选",
        "右侧筛选",
        "Key字段",
        "Key 字段",
        "Key值选择",
        "Key选择",
        "Key值",
        "选择Key",
        "Key",
        "关联Key",
        "引用对象",
        "比较字段",
        "筛选规则1",
        "筛选规则2",
        "校验规则",
        "最终判定",
        "校验判定",
        "判定",
        "断言",
        "规则参数",
        "规则是",
        "规则1",
        "规则2",
        "规则3",
    )
    text = _normalize_inline_template_labels(text, labels)
    label_pattern = "|".join(re.escape(label) for label in labels)
    sections: dict[str, list[str]] = {}
    current_label: str | None = None
    for raw_line in text.replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(rf"^({label_pattern})\s*[：:]\s*(.*)$", line)
        if match:
            current_label = match.group(1)
            sections.setdefault(current_label, []).append(match.group(2).strip())
        elif current_label:
            sections[current_label].append(line)
    return {
        label: "\n".join(item for item in values if item).strip()
        for label, values in sections.items()
        if any(item.strip() for item in values)
    }


def _normalize_inline_template_labels(text: str, labels: tuple[str, ...]) -> str:
    label_pattern = "|".join(re.escape(label) for label in labels)
    return re.sub(
        rf"([,，；;]\s*)({label_pattern})\s*[：:=]",
        lambda match: f"\n{match.group(2)}：",
        text,
        flags=re.IGNORECASE,
    )


def _leading_rule_type(text: str) -> str:
    first_line = next((line.strip() for line in text.replace("\r", "\n").split("\n") if line.strip()), "")
    return first_line if first_line in SUPPORTED_RULE_TYPES else ""


def _join_legacy_filters(sections: dict[str, str]) -> str:
    values = [
        sections.get("筛选"),
        sections.get("筛选条件"),
        sections.get("筛选规则1"),
        sections.get("筛选规则2"),
    ]
    return "；".join(
        item
        for item in values
        if item and item != "无" and not re.search(r"(?:唯一|不能重复|不可重复|必须重复|需要重复|至少一组重复|unique|duplicate_required)", item, re.IGNORECASE)
    ) or "无"


def _legacy_key_from_filters(sections: dict[str, str]) -> str:
    for value in (sections.get("筛选"), sections.get("筛选条件"), sections.get("筛选规则1"), sections.get("筛选规则2")):
        if not value:
            continue
        match = re.search(r"([A-Za-z][A-Za-z0-9_]*)\s*(?:字段)?\s*(?:唯一|不能重复|不可重复|unique)", value, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _split_free_text_candidates(text: str) -> list[str]:
    lines = [line.strip() for line in re.split(r"[\r\n]+", text) if line.strip()]
    labeled = [
        re.sub(r"^(?:规则\d+|校验规则)\s*[：:]\s*", "", line).strip()
        for line in lines
        if re.match(r"^(?:规则\d+|校验规则)\s*[：:]", line)
    ]
    if labeled:
        return labeled
    if len(lines) > 1 and all(_looks_like_standalone_rule(line) for line in lines):
        return lines
    parts = [
        part.strip()
        for part in re.split(r"[；;]+", text)
        if _looks_like_standalone_rule(part.strip())
    ]
    return parts if len(parts) > 1 else [text]


def _looks_like_standalone_rule(text: str) -> bool:
    if len(text) < 4:
        return False
    return bool(
        re.search(
            r"(不能为空|非空|唯一|不能重复|只能是|必须是|正则|格式|存在于|筛选|过滤|相等|一致|升序|降序)",
            text,
        )
    )


def _merge_hints(base: AiRuleWorkflowHints, override: AiRuleWorkflowHints) -> AiRuleWorkflowHints:
    updates = {}
    base_payload = base.model_dump(exclude_none=True)
    for key, value in override.model_dump(exclude_none=True).items():
        base_value = base_payload.get(key)
        if isinstance(value, list):
            merged = []
            for item in [*(base_value or []), *value]:
                if item and item not in merged:
                    merged.append(item)
            if merged:
                updates[key] = merged
        elif (
            key == "rule_type_hint"
            and base_value == "fixed_value_compare"
            and value == "dual_composite_compare"
            and has_complete_dual_hints(override)
        ):
            updates[key] = value
        elif value not in ("", None) and not base_value:
            updates[key] = value
    if not updates:
        return base
    payload = base.model_dump()
    payload.update(updates)
    return AiRuleWorkflowHints.model_validate(payload)


def _has_explicit_rule_type_signal(text: str, rule_type: str) -> bool:
    first_line = next((line.strip() for line in text.replace("\r", "\n").split("\n") if line.strip()), "")
    if first_line == rule_type:
        return True
    return bool(
        re.search(
            rf"(?:规则类型|rule_type)\s*[：:=]\s*(?:[^\n\r。；;]*\b)?{re.escape(rule_type)}\b",
            text,
            re.IGNORECASE,
        )
    )


def _detect_final_assertion_conflicts(text: str) -> list[str]:
    sections = _parse_template_sections(text)
    assertion_text = "\n".join(
        item
        for item in (
            sections.get("断言"),
            sections.get("校验规则"),
            sections.get("判定"),
            sections.get("最终判定"),
            sections.get("校验判定"),
            sections.get("规则是"),
        )
        if item
    ).strip()
    if assertion_text:
        text = assertion_text
    categories: list[tuple[str, tuple[str, ...]]] = [
        ("非空", ("不能为空", "非空", "必填", "not null")),
        ("唯一", ("唯一", "不能重复", "不可重复")),
        ("必须重复", ("必须重复", "需要重复", "至少一组重复", "duplicate_required")),
        ("固定值比较", ("只能是", "必须是", "等于", "不等于", "大于", "小于")),
        ("正则格式", ("正则", "格式", "匹配")),
        ("引用存在", ("存在于", "引用表", "字典表", "包含(in)")),
        ("顺序", ("升序", "降序", "递增", "递减", "连续", "步长")),
    ]
    result = [
        label
        for label, keywords in categories
        if any(keyword in text for keyword in keywords)
    ]
    if "筛选" in text or "过滤" in text:
        result = [item for item in result if item != "固定值比较" or re.search(r"(只能是|必须是|不等于|大于|小于)", text)]
    return result


def _looks_like_unsupported(text: str) -> bool:
    return any(keyword in text for keyword in UNSUPPORTED_KEYWORDS)


def _slot_label(slot: str) -> str:
    labels = {
        "target_field": "目标字段",
        "expected_value": "期望值或比较值",
        "regex": "正则或格式口径",
        "sequence": "顺序方向或步长",
        "reference": "引用表或引用字段",
        "filter": "筛选条件",
        "assertion": "最终断言",
        "dual_filters": "左右筛选条件",
        "key": "Key 字段",
        "compare_fields": "比较字段",
        "multi_node": "多组节点",
        "composite_signal": "组合变量线索",
    }
    return labels.get(slot, slot)


def _dedupe_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = re.sub(r"\s+", " ", value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(value)
    return result
