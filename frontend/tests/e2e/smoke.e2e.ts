import { expect, test, type Page } from '@playwright/test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const e2eRoot = dirname(fileURLToPath(import.meta.url))
const fixturePath = resolve(e2eRoot, 'fixtures', 'smoke-not-null.xlsx')
const sourceId = 'e2e_items'
const sheetName = 'Items'
const columnName = 'Name'
const variableTag = `[${sourceId}-${sheetName}-${columnName}]`
const ruleName = 'E2E Name Not Null'

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function elementInput(page: Page, testId: string) {
  const root = page.getByTestId(testId)
  return root
    .locator('input, textarea')
    .or(page.locator(`input[data-testid="${testId}"], textarea[data-testid="${testId}"]`))
    .first()
}

function elementButton(page: Page, testId: string) {
  const root = page.getByTestId(testId)
  return root.locator('button').or(root).first()
}

async function fillElementInput(page: Page, testId: string, value: string): Promise<void> {
  await elementInput(page, testId).fill(value)
}

async function selectElementOption(page: Page, testId: string, label: string): Promise<void> {
  await page.getByTestId(testId).click()
  const option = page.getByRole('option', {
    name: new RegExp(escapeRegExp(label)),
  }).last()
  await expect(option).toBeVisible()
  await option.click()
}

async function maybeClickPreview(page: Page): Promise<void> {
  const confirmButton = page.getByTestId('import-confirm-button')
  const previewButton = page.getByTestId('import-preview-button')
  const visibleImportAction = async () => {
    if (await confirmButton.isVisible().catch(() => false)) {
      return 'confirm'
    }
    if (await previewButton.isVisible().catch(() => false)) {
      return 'preview'
    }
    return 'none'
  }

  await expect.poll(visibleImportAction, { timeout: 15_000 }).not.toBe('none')
  if ((await visibleImportAction()) === 'confirm') {
    return
  }

  await expect(elementButton(page, 'import-preview-button')).toBeEnabled()
  await elementButton(page, 'import-preview-button').click()
}

test('core Excel validation flow works from personal workbench to fixed rules', async ({ page }) => {
  await page.goto('/login')

  await fillElementInput(page, 'login-username', 'admin')
  await fillElementInput(page, 'login-password', '123456')
  await page.getByTestId('login-submit').click()
  await expect(page.getByTestId('nav-main-board')).toBeVisible()

  await page.getByTestId('personal-add-source-button').click()
  await expect(page.getByTestId('source-dialog')).toBeVisible()
  await fillElementInput(page, 'source-id-input', sourceId)
  await selectElementOption(page, 'source-type-select', '本地 Excel')
  await page.getByTestId('source-upload-input').setInputFiles(fixturePath)
  await expect(elementInput(page, 'source-path-input')).toHaveValue(/smoke-not-null\.xlsx/i)
  await page.getByTestId('source-save-button').click()
  await expect(page.getByText(sourceId).first()).toBeVisible()

  await page.getByTestId('personal-add-variable-button').click()
  await expect(page.getByTestId('single-variable-dialog')).toBeVisible()
  await selectElementOption(page, 'single-variable-source-select', sourceId)
  await selectElementOption(page, 'single-variable-sheet-select', sheetName)
  await selectElementOption(page, 'single-variable-column-select', columnName)
  await expect(elementInput(page, 'single-variable-tag-input')).toHaveValue(variableTag)
  await page.getByTestId('single-variable-save-button').click()
  await expect(page.getByText(variableTag).first()).toBeVisible()

  await page.getByTestId('rule-create-button').click()
  await expect(page.getByTestId('rule-dialog')).toBeVisible()
  await fillElementInput(page, 'rule-name-input', ruleName)
  await selectElementOption(page, 'rule-target-variable-select', variableTag)
  await selectElementOption(page, 'rule-selection-select', '非空校验')
  await page.getByTestId('rule-save-button').click()
  await expect(page.getByText(ruleName).first()).toBeVisible()

  const personalRuleCheckbox = page
    .locator(`input[data-rule-name="${ruleName}"], [data-rule-name="${ruleName}"] input[type="checkbox"]`)
    .first()
  await personalRuleCheckbox.check({ force: true })
  await expect(personalRuleCheckbox).toBeChecked()
  await page.getByTestId('personal-execute-button').click()
  await expect(page.getByTestId('personal-result-section')).toContainText('异常结果')
  await expect(page.getByTestId('personal-result-section')).toContainText('空值')

  await page.getByTestId('personal-import-button').click()
  await expect(page.getByTestId('import-personal-rules-dialog')).toBeVisible()
  await maybeClickPreview(page)
  await expect(page.getByTestId('import-confirm-button')).toBeVisible()
  await elementButton(page, 'import-confirm-button').click()
  await expect(page.getByTestId('import-personal-rules-dialog')).toBeHidden()

  await page.getByTestId('nav-fixed-rules-board').click()
  await expect(page).toHaveURL(/\/fixed-rules/)
  await expect(page.getByText(ruleName).first()).toBeVisible()

  await page.getByTestId('fixed-execute-button').click()
  await expect(page.getByTestId('fixed-result-section')).toContainText('异常结果')
  await expect(page.getByTestId('fixed-result-section')).toContainText('空值')
})
