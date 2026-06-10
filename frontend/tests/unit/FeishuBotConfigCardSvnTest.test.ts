// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import FeishuBotConfigCard from '../../src/components/admin/FeishuBotConfigCard.vue'
import type { FeishuBotConfig } from '../../src/types/admin'
import type { ProjectAiConfig } from '../../src/types/projectAiConfig'
import {
  apiGetFeishuBotConfig,
  apiTestProjectSvnCredential,
  apiUpsertFeishuBotConfig,
} from '../../src/api/admin'
import { apiGetProjectAiConfig } from '../../src/api/projectAiConfig'

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
  apiDeleteFeishuBotConfig: vi.fn(),
  apiGetFeishuBotConfig: vi.fn(),
  apiTestProjectSvnCredential: vi.fn(),
  apiUpsertFeishuBotConfig: vi.fn(),
}))

vi.mock('../../src/api/projectAiConfig', () => ({
  apiGetProjectAiConfig: vi.fn(),
  apiSaveProjectAiConfig: vi.fn(),
  apiTestProjectAiConfig: vi.fn(),
}))

const apiGetFeishuBotConfigMock = vi.mocked(apiGetFeishuBotConfig)
const apiGetProjectAiConfigMock = vi.mocked(apiGetProjectAiConfig)
const apiTestProjectSvnCredentialMock = vi.mocked(apiTestProjectSvnCredential)
const apiUpsertFeishuBotConfigMock = vi.mocked(apiUpsertFeishuBotConfig)

const feishuConfig: FeishuBotConfig = {
  configured: true,
  app_id: 'cli_demo',
  has_app_secret: true,
  default_chat_id: 'oc_default',
  bound_chat_ids: ['oc_default'],
  allowed_open_ids: [],
  local_download_roots: [],
  svn_download_roots: [],
  allowed_download_suffixes: ['.xls'],
  query_roots: [
    {
      alias: 'game_datas',
      display_name: '游戏配置主目录',
      svn_url: 'https://svn.example.com/game',
      enabled: true,
    },
  ],
  svn_credential: {
    configured: true,
    username_masked: 'svn_admin',
    updated_at: '2026-06-10T06:39:33Z',
  },
  ai_credential: {
    configured: false,
    provider_preset: '',
    base_url: '',
    model: '',
    api_key_masked: '',
    has_extra_headers: false,
    updated_at: null,
  },
  ai_match_params: {
    auto_match_threshold: 0.9,
    candidate_threshold: 0.6,
    max_candidates: 10,
  },
  connection_state: 'inactive',
  updated_at: '2026-06-10T06:39:33Z',
}

const projectAiConfig: ProjectAiConfig = {
  configured: false,
  enabled: false,
  provider: '',
  model: '',
  base_url: '',
  masked_api_key: '',
  has_extra_headers: false,
  auto_match_threshold: 0.9,
  candidate_threshold: 0.6,
  max_candidates: 10,
  last_test_status: '',
  last_test_at: null,
  last_test_error_summary: '',
  updated_by: null,
  updated_at: null,
}

const passthrough = {
  template: '<div><slot /></div>',
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

function createDeferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => {
    resolve = next
  })
  return { promise, resolve }
}

async function mountCard(options: { config?: FeishuBotConfig } = {}) {
  apiGetFeishuBotConfigMock.mockResolvedValue({
    code: 200,
    msg: 'ok',
    data: options.config ?? feishuConfig,
  })
  const wrapper = mount(FeishuBotConfigCard, {
    props: {
      projectId: 12,
      projectName: '默认项目',
    },
    global: {
      stubs: {
        AppCard: passthrough,
        DataTable: passthrough,
        PrimaryButton: buttonStub,
        SecondaryButton: buttonStub,
        SectionHeader: passthrough,
        StatusBadge: {
          props: ['label'],
          template: '<span>{{ label }}</span>',
        },
        FeishuBotTestSendDialog: passthrough,
        'el-input': inputStub,
        'el-select': passthrough,
        'el-option': passthrough,
        'el-switch': {
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template: '<input type="checkbox" :checked="modelValue" />',
        },
      },
    },
  })
  await flushPromises()
  return wrapper
}

function findSvnTestButton(wrapper: ReturnType<typeof mount>) {
  const buttons = wrapper.findAll('button')
  const svnButton = buttons.find((button) => button.text() === '连接测试')
  if (!svnButton) {
    throw new Error('未找到 SVN 连接测试按钮')
  }
  return svnButton
}

describe('FeishuBotConfigCard project SVN credential test', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiGetProjectAiConfigMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: projectAiConfig,
    })
    apiUpsertFeishuBotConfigMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: feishuConfig,
    })
  })

  it('saves base config from the local section action', async () => {
    const wrapper = await mountCard()

    const saveButton = wrapper.findAll('button').find((button) => button.text() === '保存基础配置')
    expect(saveButton).toBeTruthy()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(apiUpsertFeishuBotConfigMock).toHaveBeenCalledWith(
      12,
      expect.objectContaining({
        app_id: 'cli_demo',
        default_chat_id: 'oc_default',
      }),
    )
  })

  it('adds default chat id to bound chat preview after input change', async () => {
    const wrapper = await mountCard({
      config: {
        ...feishuConfig,
        default_chat_id: '',
        bound_chat_ids: [],
      },
    })
    const defaultChatInput = wrapper.find('[data-testid="feishu-default-chat-id-input"]')
    expect(defaultChatInput.exists()).toBe(true)

    await defaultChatInput.setValue('oc_auto')
    await defaultChatInput.trigger('change')
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('oc_auto')
  })

  it('saves base config with default chat id merged into empty bound chats', async () => {
    const wrapper = await mountCard({
      config: {
        ...feishuConfig,
        default_chat_id: 'oc_auto',
        bound_chat_ids: [],
      },
    })

    const saveButton = wrapper.findAll('button').find((button) => button.text() === '保存基础配置')
    await saveButton!.trigger('click')
    await flushPromises()

    expect(apiUpsertFeishuBotConfigMock).toHaveBeenCalledWith(
      12,
      expect.objectContaining({
        default_chat_id: 'oc_auto',
        bound_chat_ids: ['oc_auto'],
      }),
    )
  })

  it('shows query roots validation errors near query roots section', async () => {
    const invalidConfig: FeishuBotConfig = {
      ...feishuConfig,
      query_roots: [
        {
          alias: 'game_datas',
          display_name: '游戏配置主目录',
          svn_url: '',
          enabled: true,
        },
      ],
    }
    const wrapper = await mountCard({ config: invalidConfig })

    const saveButton = wrapper.findAll('button').find((button) => button.text() === '保存数据根')
    expect(saveButton).toBeTruthy()
    await saveButton!.trigger('click')
    await flushPromises()

    const queryRootsSection = wrapper.find('[data-testid="feishu-query-roots-section"]')
    expect(queryRootsSection.text()).toContain('配置未保存')
    expect(queryRootsSection.text()).toContain('query_roots.svn_url 不能为空：game_datas')
    expect(apiUpsertFeishuBotConfigMock).not.toHaveBeenCalled()
  })

  it('saves SVN credential from the credential section and keeps blank password unchanged', async () => {
    const wrapper = await mountCard()

    await wrapper.findAll('button').find((button) => button.text() === '更新凭据')!.trigger('click')
    await wrapper.vm.$nextTick()
    const saveButton = wrapper.findAll('button').find((button) => button.text() === '保存 SVN 凭据')
    expect(saveButton).toBeTruthy()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(apiUpsertFeishuBotConfigMock).toHaveBeenCalledWith(
      12,
      expect.objectContaining({
        svn_credential: {
          username: 'svn_admin',
          password: null,
        },
      }),
    )
  })

  it('renders backend save error inside the section that triggered save', async () => {
    apiUpsertFeishuBotConfigMock.mockRejectedValue(
      new Error('该 App ID 已在其他项目配置，请使用相同 App Secret 或联系管理员确认'),
    )
    const wrapper = await mountCard()

    const saveButton = wrapper.findAll('button').find((button) => button.text() === '保存基础配置')
    await saveButton!.trigger('click')
    await flushPromises()

    const basicSection = wrapper.find('[data-testid="feishu-basic-section"]')
    expect(basicSection.text()).toContain('配置未保存')
    expect(basicSection.text()).toContain(
      '该 App ID 已在其他项目配置，请使用相同 App Secret 或联系管理员确认',
    )
  })

  it('calls the real project SVN credential test API and renders success items', async () => {
    apiTestProjectSvnCredentialMock.mockResolvedValue({
      code: 200,
      msg: 'ok',
      data: {
        status: 'success',
        items: [
          {
            alias: 'game_datas',
            display_name: '游戏配置主目录',
            svn_url: 'https://svn.example.com/game',
            status: 'success',
            message: '连接成功',
            entry_count: 3,
          },
        ],
      },
    })
    const wrapper = await mountCard()

    await findSvnTestButton(wrapper).trigger('click')
    await flushPromises()

    expect(apiTestProjectSvnCredentialMock).toHaveBeenCalledWith(12)
    expect(wrapper.text()).toContain('连接测试成功')
    expect(wrapper.text()).toContain('game_datas')
    expect(wrapper.text()).toContain('3 项')
  })

  it('shows loading state while project SVN credential test is pending', async () => {
    const deferred = createDeferred<Awaited<ReturnType<typeof apiTestProjectSvnCredential>>>()
    apiTestProjectSvnCredentialMock.mockReturnValue(deferred.promise)
    const wrapper = await mountCard()

    await findSvnTestButton(wrapper).trigger('click')
    await wrapper.vm.$nextTick()

    const testingButton = wrapper.findAll('button').find((button) => button.text() === '测试中…')
    expect(testingButton?.attributes('disabled')).toBeDefined()

    deferred.resolve({
      code: 200,
      msg: 'ok',
      data: { status: 'success', items: [] },
    })
    await flushPromises()
  })

  it('renders backend Chinese error when project SVN credential test fails', async () => {
    apiTestProjectSvnCredentialMock.mockRejectedValue(
      new Error('请先保存项目级 SVN 凭据后再测试连接'),
    )
    const wrapper = await mountCard()

    await findSvnTestButton(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('连接测试失败')
    expect(wrapper.text()).toContain('请先保存项目级 SVN 凭据后再测试连接')
  })
})
