"""用例生成 V1 内置 QA Case Method。"""

from __future__ import annotations

from backend.app.test_cases.schemas import QaCaseMethodContext


METHOD_NAME = "QA Case Method"
METHOD_VERSION = "v1"
KNOWLEDGE_LIBRARY_NOTE = "V1 未接入项目级 QA 知识库"

BLUEPRINT_DIMENSIONS: tuple[str, ...] = (
    "模块树",
    "核心流程",
    "状态或生命周期",
    "配置/数据来源",
    "角色关系",
    "时间刷新点",
    "外部耦合",
    "变更影响范围",
    "风险点",
    "待确认问题",
)

COMPLETENESS_MATRIX: tuple[str, ...] = (
    "生命周期",
    "时间刷新",
    "权限关系",
    "地图/服务器",
    "配置数值",
    "UI 通用",
    "输入",
    "历史记录",
    "外部耦合",
)

SCENARIO_LIBRARY: tuple[str, ...] = (
    "弹窗/面板",
    "红点",
    "分享/拜访",
    "售卖/兑换",
    "每日任务",
    "产出/收取/偷取",
    "账单/邮件",
    "移民/活动下线",
    "性能/稳定性",
)

SELF_CHECK_RULES: tuple[str, ...] = (
    "检查未映射需求",
    "检查无需求依据测试点",
    "检查待确认问题",
    "检查未读图片/附件限制",
    "检查环境限制",
    "统计只能由代码计算",
)

WARNING_TEMPLATES: tuple[str, ...] = (
    "未读取图片/附件语义时必须提示人工确认。",
    "无法从策划案定位来源时必须写入 warning 或 remarks。",
    "不得把模型输出的统计作为最终统计。",
)


def build_method_context() -> QaCaseMethodContext:
    """返回 V1 生成响应和 prompt 共用的方法说明。"""
    return QaCaseMethodContext(
        method_name=METHOD_NAME,
        method_version=METHOD_VERSION,
        knowledge_library_note=KNOWLEDGE_LIBRARY_NOTE,
        dimensions=list(COMPLETENESS_MATRIX),
    )


def get_internal_knowledge_context() -> dict[str, object]:
    """V1 预留内部知识库扩展点，但不读取项目级可维护知识库。"""
    return {
        "enabled": False,
        "note": KNOWLEDGE_LIBRARY_NOTE,
        "items": [],
    }
