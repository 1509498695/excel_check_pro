"""固定规则 handler 包。

导入本包会加载各规则类型子模块，触发 ``@register_rule`` 注册副作用。
"""

from __future__ import annotations

from backend.app.rules.handlers.fixed import basic, composite, dual_composite, event_task, mapping, package_items, pipeline, sequence  # noqa: F401
from backend.app.rules.handlers.fixed.basic import (  # noqa: F401
    check_fixed_value_compare,
    check_not_null,
    check_regex,
    check_regex_check,
    check_unique,
)
from backend.app.rules.handlers.fixed.composite import check_composite_condition_check  # noqa: F401
from backend.app.rules.handlers.fixed.dual_composite import check_dual_composite_compare  # noqa: F401
from backend.app.rules.handlers.fixed.event_task import (  # noqa: F401
    check_event_task_reward,
    check_event_task_validation,
)
from backend.app.rules.handlers.fixed.mapping import check_multi_composite_mapping_check  # noqa: F401
from backend.app.rules.handlers.fixed.package_items import check_package_items_compare  # noqa: F401
from backend.app.rules.handlers.fixed.pipeline import check_multi_composite_pipeline_check  # noqa: F401
from backend.app.rules.handlers.fixed.sequence import check_sequence_order  # noqa: F401

__all__ = [name for name in globals() if not name.startswith("_")]
