"""用例生成 V1 共享常量。"""

from __future__ import annotations


STANDARD_CASE_FIELDS: tuple[str, ...] = (
    "case_id",
    "module",
    "feature",
    "scenario",
    "title",
    "preconditions",
    "steps",
    "expected_results",
    "priority",
    "case_type",
    "source_requirement",
    "config_source",
    "planning_answer",
    "initial_status",
    "bug_link",
    "remarks",
)

STANDARD_CASE_FIELD_LABELS: dict[str, str] = {
    "case_id": "用例编号",
    "module": "功能模块",
    "feature": "功能点",
    "scenario": "测试场景",
    "title": "用例标题",
    "preconditions": "前置条件",
    "steps": "操作步骤",
    "expected_results": "预期结果",
    "priority": "优先级",
    "case_type": "用例类型",
    "source_requirement": "来源测试点",
    "config_source": "配置来源",
    "planning_answer": "策划答疑",
    "initial_status": "初始状态",
    "bug_link": "Bug 链接",
    "remarks": "备注",
}

FORBIDDEN_PUBLIC_KNOWLEDGE_FIELDS: frozenset[str] = frozenset(
    {
        "knowledge_context",
        "qa_knowledge_context",
        "project_qa_knowledge",
        "project_qa_knowledge_context",
        "knowledge_library_context",
    }
)

TEST_CASES_NOT_IMPLEMENTED_MESSAGE = (
    "用例生成 V1 后端接口骨架已注册，业务实现尚未接入。"
)

REFERENCE_ALLOWED_SUFFIXES: frozenset[str] = frozenset(
    {
        ".xlsx",
        ".xls",
        ".md",
        ".txt",
    }
)

REFERENCE_MAX_FILE_BYTES = 20 * 1024 * 1024

REFERENCE_DEFAULT_SHEET_NAMES: tuple[str, ...] = ("测试用例", "用例", "TestCases")

REFERENCE_UNCATEGORIZED_NAME = "未分类"


CANONICAL_PRIMARY_MODULES: tuple[str, ...] = (
    "开关/入口",
    "界面",
    "按钮",
    "功能",
    "数值/配置",
    "奖励/消耗",
    "红点/提示",
    "文本/多语言",
    "兼容",
    "特殊操作",
    "常规测试点",
)

CANONICAL_CASE_FIELDS: tuple[str, ...] = (
    "primary_module",
    "secondary_module",
    "checkpoint",
    "preconditions",
    "steps",
    "expected_results",
    "priority",
    "remarks",
)

CANONICAL_CASE_FIELD_LABELS: dict[str, str] = {
    "primary_module": "一级模块",
    "secondary_module": "二级模块",
    "checkpoint": "检查点",
    "preconditions": "前置条件",
    "steps": "操作步骤",
    "expected_results": "预期结果",
    "priority": "优先级",
    "remarks": "备注",
}
