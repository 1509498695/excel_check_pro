"""固定规则配置服务门面。

真实加载、保存、归一化、TaskTree 构建、执行和 SVN 更新逻辑分布在同包
模块中；本文件保留历史 import 路径和 monkeypatch 兼容点。
"""
# ruff: noqa: F401

from __future__ import annotations

from backend.app.fixed_rules.config_common import (
    COMPOSITE_KEY_FIELD,
    COMPARE_STYLE_OPERATORS,
    FIXED_RULES_CONFIG_VERSION,
    SET_STYLE_OPERATORS,
    SUPPORTED_COMPOSITE_ASSERTION_OPERATORS,
    SUPPORTED_COMPOSITE_FILTER_OPERATORS,
    SUPPORTED_DUAL_COMPOSITE_KEY_CHECK_MODES,
    SUPPORTED_DUAL_COMPOSITE_OPERATORS,
    SUPPORTED_FIXED_RULE_OPERATORS,
    SUPPORTED_FIXED_RULE_TYPES,
    SUPPORTED_LOCAL_SOURCE_SUFFIXES,
    SUPPORTED_MULTI_PIPELINE_ASSERTION_OPERATORS,
    _append_config_issue,
    _build_default_group,
    _build_single_variable_tag,
    _build_source_id_from_path,
    _collect_composite_available_fields,
    _normalize_columns,
    _normalize_display_field,
    _normalize_expected_value_mode_for_operator,
    _normalize_group_name,
    _normalize_local_path_replacement_presets,
    _normalize_local_source_path,
    _normalize_selected_local_path_replacement_preset,
    _normalize_selected_svn_path_replacement_preset,
    _normalize_sequence_numeric,
    _normalize_svn_path_replacement_presets,
    _resolve_identifier_against_available,
    _resolve_identifiers_against_available,
)
from backend.app.fixed_rules.config_loader import (
    _load_fixed_rules_config_payload,
    build_default_fixed_rules_config,
    load_fixed_rules_config,
    load_fixed_rules_config_with_issues,
    parse_raw_fixed_rules_config,
)
from backend.app.fixed_rules.config_migrator import (
    LEGACY_FIXED_RULE_KEYS,
    _ensure_v4_config,
    _migrate_legacy_payload,
    _parse_fixed_rules_payload,
)
from backend.app.fixed_rules.composite_rule_normalizer import (
    _normalize_composite_conditions,
    _normalize_composite_rule_config,
)
from backend.app.fixed_rules.config_normalizer import (
    _validate_and_normalize_fixed_rules_config,
    validate_and_normalize_fixed_rules_config,
)
from backend.app.fixed_rules.config_saver import save_fixed_rules_config
from backend.app.fixed_rules.dual_composite_normalizer import (
    _normalize_dual_composite_rule,
    _normalize_dual_key_field,
)
from backend.app.fixed_rules.execution import (
    execute_fixed_rules_for_project,
    execute_saved_fixed_rules,
)
from backend.app.fixed_rules.group_normalizer import _normalize_groups
from backend.app.fixed_rules.mapping_rule_normalizer import (
    _has_legacy_mapping_node_content,
    _normalize_multi_composite_mapping_config,
    _normalize_multi_composite_mapping_exclusion_ranges,
    _normalize_multi_composite_mapping_filters,
)
from backend.app.fixed_rules.metadata_loader import _load_sheet_columns
from backend.app.fixed_rules.pipeline_rule_normalizer import (
    _normalize_multi_composite_pipeline_config,
)
from backend.app.fixed_rules.rule_normalizer import _normalize_rules
from backend.app.fixed_rules.source_normalizer import _normalize_sources
from backend.app.fixed_rules.source_runtime_validator import (
    _validate_source_runtime_bindings,
)
from backend.app.fixed_rules.svn_update import (
    _collect_svn_targets,
    _collect_working_copies,
)
from backend.app.fixed_rules.svn_update import (
    run_saved_fixed_rules_svn_update as _run_saved_fixed_rules_svn_update,
)
from backend.app.fixed_rules.task_tree_builder import (
    _build_fixed_rule_params,
    _get_ordered_rules,
    _get_primary_rule_target_tag,
    build_fixed_rules_task_tree,
)
from backend.app.fixed_rules.variable_normalizer import _normalize_variables
from backend.app.loaders.svn_manager import update_svn_working_copy


def run_saved_fixed_rules_svn_update(config=None, *, user_scope=None):
    """兼容门面，允许测试继续 monkeypatch service.update_svn_working_copy。"""
    return _run_saved_fixed_rules_svn_update(
        config,
        user_scope=user_scope,
        update_working_copy=update_svn_working_copy,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
