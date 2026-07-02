// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SourceEvidenceAdminConfigCard from '../../src/components/admin/SourceEvidenceAdminConfigCard.vue'
import {
  apiGetProjectVisionAiConfig,
  apiGetSourceEvidenceSvnRoots,
  apiSaveProjectVisionAiConfig,
  apiSaveSourceEvidenceSvnRoots,
  apiTestProjectVisionAiConfig,
} from '../../src/api/admin'
import type {
  ProjectVisionAiConfig,
  SourceEvidenceSvnRootsConfig,
} from '../../src/types/admin'
import { ApiRequestError } from '../../src/utils/apiFetch'

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
  ElMessageBox: {
    confirm: vi.fn(),
  },
}))

vi.mock('../../src/api/admin', () => ({
  apiDeleteProjectVisionAiConfig: vi.fn(),
  apiGetProjectVisionAiConfig: vi.fn(),
  apiGetSourceEvidenceSvnRoots: vi.fn(),
  apiSaveProjectVisionAiConfig: vi.fn(),
  apiSaveSourceEvidenceSvnRoots: vi.fn(),
  apiTestProjectVisionAiConfig: vi.fn(),
}))

const apiGetSourceEvidenceSvnRootsMock = vi.mocked(apiGetSourceEvidenceSvnRoots)
const apiGetProjectVisionAiConfigMock = vi.mocked(apiGetProjectVisionAiConfig)
const apiSaveSourceEvidenceSvnRootsMock = vi.mocked(apiSaveSourceEvidenceSvnRoots)
const apiSaveProjectVisionAiConfigMock = vi.mocked(apiSaveProjectVisionAiConfig)
const apiTestProjectVisionAiConfigMock = vi.mocked(apiTestProjectVisionAiConfig)

const rootsConfig: SourceEvidenceSvnRootsConfig = {
  items: [
    {
      alias: 'game_datas',
      display_name: '游戏配置主目录',
      svn_url: 'https://svn.example.com/game/',
      enabled: true,
    },
  ],
}

const visionConfig: ProjectVisionAiConfig = {
  configured: true,
  enabled: true,
  provider: 'openai',
  model: 'gpt-4o-mini',
  base_url: 'https://api.openai.com/v1',
  masked_api_key: 'sk-***abcd',
  has_extra_headers: false,
  last_test_status: 'success',
  last_test_at: '2026-07-02T01:00:00Z',
  last_test_error_summary: '',
  updated_by: 1,
  updated_at: '2026-07-02T01:00:00Z',
}

const passthrough = {
  template: '<div><slot /><slot name="actions" /></div>',
}

const buttonStub = {
  props: ['disabled'],
  emits: ['click'],
  template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
}

const inputStub = {
  props: ['modelValue'],
  emits: ['update:modelValue', 'change'],
  template:
    '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" @change="$emit(\'change\', $event.target.value)" />',
}

async function mountCard(options: { visionConfig?: ProjectVisionAiConfig } = {}) {
  const currentVisionConfig = options.visionConfig ?? visionConfig
  apiGetSourceEvidenceSvnRootsMock.mockResolvedValue({
    code: 200,
    msg: 'ok',
    data: rootsConfig,
  })
  apiGetProjectVisionAiConfigMock.mockResolvedValue({
    code: 200,
    msg: 'ok',
    data: currentVisionConfig,
  })
  apiSaveSourceEvidenceSvnRootsMock.mockResolvedValue({
    code: 200,
    msg: 'ok',
    data: rootsConfig,
  })
  apiSaveProjectVisionAiConfigMock.mockResolvedValue({
    code: 200,
    msg: 'ok',
    data: visionConfig,
  })
  apiTestProjectVisionAiConfigMock.mockResolvedValue({
    code: 200,
    msg: 'ok',
    data: currentVisionConfig,
  })

  const wrapper = mount(SourceEvidenceAdminConfigCard, {
    props: {
      projectId: 12,
      projectName: '默认项目',
    },
    global: {
      directives: {
        loading: {},
      },
      stubs: {
        AppCard: passthrough,
        PrimaryButton: buttonStub,
        SecondaryButton: buttonStub,
        SectionHeader: passthrough,
        StatusBadge: {
          props: ['label'],
          template: '<span>{{ label }}</span>',
        },
        'el-input': inputStub,
        'el-select': {
          props: ['modelValue'],
          emits: ['update:modelValue', 'change'],
          template: `
            <select
              :value="modelValue"
              @change="$emit('update:modelValue', $event.target.value); $emit('change', $event.target.value)"
            >
              <slot />
            </select>
          `,
        },
        'el-option': {
          props: ['label', 'value'],
          template: '<option :value="value">{{ label }}</option>',
        },
        'el-switch': {
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template: '<input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
        },
      },
    },
  })
  await flushPromises()
  return wrapper
}

function findButtonByText(wrapper: Awaited<ReturnType<typeof mountCard>>, text: string) {
  const button = wrapper.findAll('button').find((item) => item.text() === text)
  if (!button) {
    throw new Error(`未找到按钮：${text}`)
  }
  return button
}

describe('SourceEvidenceAdminConfigCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads and renders Source Evidence SVN Root and Vision AI settings', async () => {
    const wrapper = await mountCard()

    expect(apiGetSourceEvidenceSvnRootsMock).toHaveBeenCalledWith(12)
    expect(apiGetProjectVisionAiConfigMock).toHaveBeenCalledWith(12)
    expect(wrapper.text()).toContain('Source Evidence SVN Root')
    expect(wrapper.text()).toContain('Project Vision AI Credential')
    expect((wrapper.find('input[name="source-evidence-root-alias"]').element as HTMLInputElement).value).toBe(
      'game_datas',
    )
    expect(wrapper.text()).toContain('sk-***abcd')
  })

  it('saves Source Evidence SVN Roots through the dedicated API', async () => {
    const wrapper = await mountCard()

    await findButtonByText(wrapper, '保存 SVN Root').trigger('click')
    await flushPromises()

    expect(apiSaveSourceEvidenceSvnRootsMock).toHaveBeenCalledWith(12, {
      items: rootsConfig.items,
    })
  })

  it('saves and tests Vision AI config through dedicated APIs', async () => {
    const wrapper = await mountCard()

    await findButtonByText(wrapper, '保存 Vision AI').trigger('click')
    await flushPromises()
    await findButtonByText(wrapper, '连接测试').trigger('click')
    await flushPromises()

    expect(apiSaveProjectVisionAiConfigMock).toHaveBeenCalledWith(12, {
      provider: 'openai',
      model: 'gpt-4o-mini',
      base_url: 'https://api.openai.com/v1',
      api_key: null,
      enabled: true,
    })
    expect(apiTestProjectVisionAiConfigMock).toHaveBeenCalledWith(12)
  })

  it('uses explicit vision model defaults instead of text AI defaults', async () => {
    const wrapper = await mountCard()

    const providerSelect = wrapper.find('select[name="source-evidence-vision-provider"]')
    const optionValues = wrapper.findAll('option').map((option) => option.attributes('value'))

    expect(optionValues).toContain('qwen')
    expect(optionValues).not.toContain('deepseek')

    await providerSelect.setValue('qwen')
    await flushPromises()

    expect(
      (wrapper.find('input[name="source-evidence-vision-model"]').element as HTMLInputElement)
        .value,
    ).toBe('qwen3.7-plus')
    expect(
      (wrapper.find('input[name="source-evidence-vision-base-url"]').element as HTMLInputElement)
        .value,
    ).toBe('https://dashscope.aliyuncs.com/compatible-mode/v1')
    expect(wrapper.text()).toContain(
      'qwen-plus/qwen3.6-plus 等文本模型不能用于 Source Evidence 图片 observation',
    )
  })

  it('offers Zhipu GLM-V as a Vision AI provider', async () => {
    const wrapper = await mountCard()

    const providerSelect = wrapper.find('select[name="source-evidence-vision-provider"]')
    await providerSelect.setValue('zhipu')
    await flushPromises()

    expect(
      (wrapper.find('input[name="source-evidence-vision-model"]').element as HTMLInputElement)
        .value,
    ).toBe('glm-5v-turbo')
    expect(
      (wrapper.find('input[name="source-evidence-vision-base-url"]').element as HTMLInputElement)
        .value,
    ).toBe('https://open.bigmodel.cn/api/paas/v4')
    expect(wrapper.text()).toContain('GLM-5V-Turbo')
  })

  it('warns when a saved text provider is used for Vision AI', async () => {
    const wrapper = await mountCard({
      visionConfig: {
        ...visionConfig,
        provider: 'deepseek',
        model: 'deepseek-v4-flash',
        base_url: 'https://api.deepseek.com',
        last_test_status: 'failed',
        last_test_error_summary: 'Vision AI 配置未保存',
      },
    })

    expect(wrapper.text()).toContain('DeepSeek 来自项目级文本 AI provider 列表')
    expect(wrapper.text()).toContain('当前没有明确作为 Source Evidence 视觉模型推荐')
  })

  it('shows connection test failure without saying the config is unsaved', async () => {
    const failedVisionConfig: ProjectVisionAiConfig = {
      ...visionConfig,
      last_test_status: 'failed',
      last_test_at: '2026-07-02T04:05:04Z',
      last_test_error_summary: '模型名或接口地址不存在。',
    }
    const wrapper = await mountCard()
    apiTestProjectVisionAiConfigMock.mockRejectedValueOnce(
      new ApiRequestError('连接测试失败', 400, null, {
        code: 400,
        msg: '连接测试失败',
        data: failedVisionConfig,
      }),
    )

    await findButtonByText(wrapper, '连接测试').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Vision AI 连接测试失败')
    expect(wrapper.text()).toContain('模型名或接口地址不存在。')
    expect(wrapper.text()).toContain('最后测试：failed')
    expect(wrapper.text()).not.toContain('Vision AI 配置未保存')
  })
})
