import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { userGuideSections } from '../../src/content/userGuide'
import { extractSmartRuleWorkflowHints } from '../../src/utils/aiRuleHintExtractor'

const staleCopyPattern = /飞书.*占位|占位.*飞书|暂为占位|当前 10 类|10 类已有规则/

describe('metadata and current copy contracts', () => {
  it('does not show stale Feishu placeholder or 10-rule copy in current frontend text', () => {
    const fixedRulesBoardSource = readFileSync(
      resolve(process.cwd(), 'src/views/FixedRulesBoard.vue'),
      'utf-8',
    )
    const guideText = JSON.stringify(userGuideSections)

    expect(fixedRulesBoardSource).not.toMatch(staleCopyPattern)
    expect(guideText).not.toMatch(staleCopyPattern)
    expect(guideText).toContain('当前 11 类已有规则')
  })

  it('recognizes package_items_compare and IAP package aliases in AI rule hints', () => {
    expect(
      extractSmartRuleWorkflowHints('规则类型：package_items_compare\n校验规则：礼包规划与 STR_Items 一致')
        .ruleTypeHint,
    ).toBe('package_items_compare')
    expect(extractSmartRuleWorkflowHints('规则类型：IAP礼包校验').ruleTypeHint).toBe(
      'package_items_compare',
    )
  })
})
