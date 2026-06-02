/**
 * 将工作台步骤 3 的 FixedRuleDefinition 列表映射为引擎 TaskTree 所需的 ValidationRule。
 * 字段形状与后端 fixed_rules/service._build_fixed_rule_params 及 rule_fixed 执行器一致。
 */

import type { FixedRuleDefinition } from '../types/fixedRules'
import type { ValidationRule, VariableTag } from '../types/workbench'

function locationForSingle(variable: VariableTag): string {
  const column = variable.column?.trim() ?? ''
  return `${variable.sheet} -> ${column}`
}

export function orchestrationRulesToValidationRules(
  variables: VariableTag[],
  rules: FixedRuleDefinition[],
): ValidationRule[] {
  const variableMap = new Map(variables.map((v) => [v.tag, v] as const))

  return rules.map((rule) => {
    if (rule.rule_type === 'package_items_compare') {
      return {
        rule_id: rule.rule_id,
        rule_type: 'package_items_compare',
        params: {
          reference_variable_tag: rule.reference_variable_tag?.trim() ?? '',
          right_package_field: rule.right_package_field ?? 'INT_PackageId',
          right_items_field: rule.right_items_field ?? 'STR_Items',
          left_package_field: rule.left_package_field ?? '礼包id',
          left_item_field: rule.left_item_field ?? '道具ID',
          left_count_field: rule.left_count_field ?? '个数',
          package_id_filter: rule.package_id_filter,
          package_parse_config: rule.package_parse_config
            ? JSON.parse(JSON.stringify(rule.package_parse_config))
            : undefined,
          rule_name: rule.rule_name,
          display_field: rule.display_field,
        },
      }
    }

    if (rule.rule_type === 'multi_composite_pipeline_check') {
      const firstNodeTag = rule.pipeline_config?.nodes[0]?.variable_tag.trim() ?? ''
      const variable = variableMap.get(firstNodeTag)
      return {
        rule_id: rule.rule_id,
        rule_type: 'multi_composite_pipeline_check',
        params: variable
          ? {
              target_tag: variable.tag,
              rule_name: rule.rule_name,
              display_field: rule.display_field,
              pipeline_config: rule.pipeline_config
                ? JSON.parse(JSON.stringify(rule.pipeline_config))
                : undefined,
            }
          : {},
      }
    }

    if (rule.rule_type === 'multi_composite_mapping_check') {
      const firstNodeTag = rule.mapping_config?.nodes[0]?.variable_tag.trim() ?? ''
      const variable = variableMap.get(firstNodeTag)
      return {
        rule_id: rule.rule_id,
        rule_type: 'multi_composite_mapping_check',
        params: variable
          ? {
              target_tag: variable.tag,
              rule_name: rule.rule_name,
              display_field: rule.display_field,
              mapping_config: rule.mapping_config
                ? JSON.parse(JSON.stringify(rule.mapping_config))
                : undefined,
            }
          : {},
      }
    }

    const variable = variableMap.get(rule.target_variable_tag.trim())
    if (!variable) {
      return {
        rule_id: rule.rule_id,
        rule_type: rule.rule_type,
        params: {},
      }
    }

    if (rule.rule_type === 'composite_condition_check') {
      return {
        rule_id: rule.rule_id,
        rule_type: 'composite_condition_check',
        params: {
          target_tag: variable.tag,
          rule_name: rule.rule_name,
          display_field: rule.display_field,
          composite_config: rule.composite_config
            ? JSON.parse(JSON.stringify(rule.composite_config))
            : undefined,
        },
      }
    }

    if (rule.rule_type === 'dual_composite_compare') {
      return {
        rule_id: rule.rule_id,
        rule_type: 'dual_composite_compare',
        params: {
          target_tag: variable.tag,
          reference_tag: rule.reference_variable_tag?.trim() ?? '',
          key_check_mode: rule.key_check_mode ?? 'baseline_only',
          left_key_field: rule.left_key_field ?? '__key__',
          right_key_field: rule.right_key_field ?? '__key__',
          display_field: rule.display_field,
          comparisons: (rule.comparisons ?? []).map((comparison) => ({
            comparison_id: comparison.comparison_id,
            left_field: comparison.left_field,
            operator: comparison.operator,
            right_field: comparison.right_field,
          })),
          left_filters: JSON.parse(JSON.stringify(rule.left_filters ?? [])),
          right_filters: JSON.parse(JSON.stringify(rule.right_filters ?? [])),
          rule_name: rule.rule_name,
        },
      }
    }

    if (rule.rule_type === 'fixed_value_compare') {
      return {
        rule_id: rule.rule_id,
        rule_type: 'fixed_value_compare',
        params: {
          target_tag: variable.tag,
          operator: rule.operator ?? 'gt',
          expected_value: rule.expected_value ?? '',
          expected_value_mode: rule.expected_value_mode,
          rule_name: rule.rule_name,
          location: locationForSingle(variable),
          display_field: rule.display_field,
        },
      }
    }

    if (rule.rule_type === 'regex_check') {
      return {
        rule_id: rule.rule_id,
        rule_type: 'regex_check',
        params: {
          target_tag: variable.tag,
          pattern: rule.expected_value ?? '',
          rule_name: rule.rule_name,
          location: locationForSingle(variable),
          display_field: rule.display_field,
        },
      }
    }

    if (rule.rule_type === 'cross_table_mapping') {
      const referenceVariable = variableMap.get(rule.reference_variable_tag?.trim() ?? '')
      return {
        rule_id: rule.rule_id,
        rule_type: 'cross_table_mapping',
        params: {
          dict_tag: referenceVariable?.tag ?? '',
          target_tag: variable.tag,
          rule_name: rule.rule_name,
          location: locationForSingle(variable),
          display_field: rule.display_field,
        },
      }
    }

    if (rule.rule_type === 'sequence_order_check') {
      return {
        rule_id: rule.rule_id,
        rule_type: 'sequence_order_check',
        params: {
          target_tag: variable.tag,
          direction: rule.sequence_direction ?? 'asc',
          step: rule.sequence_step ?? '1',
          start_mode: rule.sequence_start_mode ?? 'auto',
          start_value: rule.sequence_start_value ?? '',
          rule_name: rule.rule_name,
          location: locationForSingle(variable),
          display_field: rule.display_field,
        },
      }
    }

    return {
      rule_id: rule.rule_id,
      rule_type: rule.rule_type,
      params: {
        target_tags: [variable.tag],
        rule_name: rule.rule_name,
        location: locationForSingle(variable),
        display_field: rule.display_field,
      },
    }
  })
}
