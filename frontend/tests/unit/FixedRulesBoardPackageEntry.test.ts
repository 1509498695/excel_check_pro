import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const fixedRulesBoardSource = readFileSync(
  resolve(process.cwd(), 'src/views/FixedRulesBoard.vue'),
  'utf-8',
)
const personalRulePanelSource = readFileSync(
  resolve(process.cwd(), 'src/components/workbench/WorkbenchRuleOrchestrationPanel.vue'),
  'utf-8',
)
const ruleConstantsSource = readFileSync(resolve(process.cwd(), 'src/rules/constants.ts'), 'utf-8')

describe('personal rule package items entry', () => {
  it('keeps package items out of the standard rule type selector', () => {
    expect(ruleConstantsSource).toContain('RULE_ENTRY_TYPE_OPTIONS')
    expect(ruleConstantsSource).not.toContain("value: 'package_items_compare'")
    expect(ruleConstantsSource).not.toContain("value: 'package_compare'")
  })

  it('opens package items through the dedicated personal 03 rule entry', () => {
    expect(personalRulePanelSource).toContain(':show-package-items-rule-button="true"')
    expect(personalRulePanelSource).toContain(':show-event-task-rule-button="true"')
    expect(personalRulePanelSource).toContain(
      '@create-package-items-rule="openPackageItemsRuleDialog"',
    )
    expect(personalRulePanelSource).toContain(
      '@create-event-task-rule="openEventTaskRuleDialog"',
    )
    expect(personalRulePanelSource).toContain('PackageItemsRuleDialog')
    expect(personalRulePanelSource).toContain('EventTaskRuleDialog')
    expect(personalRulePanelSource).toContain(':backend-ready="true"')
    expect(personalRulePanelSource).toContain('@preview="handlePreviewPackageItemsRule"')
    expect(personalRulePanelSource).toContain('@save="handleSavePackageItemsRule"')
    expect(personalRulePanelSource).toContain('previewWorkbenchPackageItems')
  })

  it('does not add the IAP package entry to the project rule board', () => {
    expect(fixedRulesBoardSource).not.toContain(':show-package-items-rule-button="true"')
    expect(fixedRulesBoardSource).not.toContain(':show-event-task-rule-button="true"')
    expect(fixedRulesBoardSource).not.toContain('@create-package-items-rule')
    expect(fixedRulesBoardSource).not.toContain('@create-event-task-rule')
  })
})
