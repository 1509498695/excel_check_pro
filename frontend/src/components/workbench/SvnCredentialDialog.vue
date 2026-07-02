<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import {
  SvnApiError,
  ensureTrailingSlash,
  getDefaultSvnCredentialTestDirUrl,
  isHttpDirUrl,
  listSvnDirectory,
  saveSvnCredentials,
} from '../../api/svn'

const props = defineProps<{
  visible: boolean
  host: string
  /** 已保存或默认回填的 SVN 测试目录 URL。 */
  defaultTestDirUrl?: string
  /** 已保存的用户名，回填表单。 */
  defaultUsername?: string
  /** 已保存的密码，回填表单。 */
  defaultPassword?: string
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  saved: [host: string]
  cancel: []
}>()

const form = reactive({
  username: props.defaultUsername ?? '',
  password: props.defaultPassword ?? '',
  testDirUrl: props.defaultTestDirUrl ?? '',
  showPassword: false,
})

const isSaving = ref(false)
const isTesting = ref(false)

const dialogTitle = computed(() => `配置 SVN 凭据 — ${props.host || '未知 host'}`)

watch(
  () => props.visible,
  (next) => {
    if (next) {
      form.username = props.defaultUsername ?? ''
      form.password = props.defaultPassword ?? ''
      form.testDirUrl =
        props.defaultTestDirUrl?.trim() ||
        getDefaultSvnCredentialTestDirUrl(props.host)
      form.showPassword = false
    }
  },
)

const canSubmit = computed(
  () => !!props.host && form.username.trim().length > 0 && form.password.length > 0,
)

const canTestConnection = computed(() => {
  return canSubmit.value && isHttpDirUrl(form.testDirUrl)
})

function getNormalizedTestDirUrl(): string {
  const normalized = ensureTrailingSlash(form.testDirUrl)
  if (!isHttpDirUrl(normalized)) {
    throw new Error('请输入合法的 SVN 测试目录 URL。')
  }
  return normalized
}

function close(): void {
  emit('update:visible', false)
}

async function handleTestConnection(): Promise<void> {
  if (!canSubmit.value) {
    ElMessage.warning('请先填写用户名/密码后再测试连接。')
    return
  }
  isTesting.value = true
  try {
    const normalizedTestDirUrl = getNormalizedTestDirUrl()
    form.testDirUrl = normalizedTestDirUrl
    // 先保存当前凭据与测试目录，再对该目录执行一次 svn list。
    await saveSvnCredentials(
      props.host,
      form.username.trim(),
      form.password,
      normalizedTestDirUrl,
    )
    await listSvnDirectory(normalizedTestDirUrl)
    ElMessage.success('连接成功，凭据已保存。')
    emit('saved', props.host)
    close()
  } catch (error) {
    if (error instanceof Error && error.message === '请输入合法的 SVN 测试目录 URL。') {
      ElMessage.warning(error.message)
      return
    }
    if (error instanceof SvnApiError) {
      const tipByCategory: Record<string, string> = {
        auth_failed: '当前账号无权访问测试目录，请检查 SVN 用户权限或重新输入凭据。',
        not_found: '测试目录不存在或当前账号无权访问。',
        network: '无法连接到 SVN 服务器，请检查网络。',
        timeout: 'SVN 列表请求超时，请稍后重试。',
        allowlist: 'SVN 主机不在允许列表中。',
        invalid_url: '测试目录 URL 不合法。',
        unknown: '连接测试失败，请稍后重试。',
      }
      ElMessage.error(error.message || tipByCategory[error.category] || '连接测试失败，请稍后重试。')
    } else if (error instanceof Error) {
      ElMessage.error(error.message)
    } else {
      ElMessage.error('连接测试失败。')
    }
  } finally {
    isTesting.value = false
  }
}

async function handleSubmit(): Promise<void> {
  if (!canSubmit.value) {
    return
  }
  isSaving.value = true
  try {
    const normalizedTestDirUrl = getNormalizedTestDirUrl()
    form.testDirUrl = normalizedTestDirUrl
    await saveSvnCredentials(
      props.host,
      form.username.trim(),
      form.password,
      normalizedTestDirUrl,
    )
    ElMessage.success('SVN 凭据已保存。')
    emit('saved', props.host)
    close()
  } catch (error) {
    if (error instanceof Error && error.message === '请输入合法的 SVN 测试目录 URL。') {
      ElMessage.warning(error.message)
    } else {
      ElMessage.error(error instanceof Error ? error.message : '保存凭据失败。')
    }
  } finally {
    isSaving.value = false
  }
}

function handleCancel(): void {
  emit('cancel')
  close()
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="dialogTitle"
    width="460px"
    destroy-on-close
    @update:model-value="(value: boolean) => emit('update:visible', value)"
  >
    <div class="flex flex-col gap-4">
      <div class="text-[12px] text-ink-500">
        凭据按当前登录用户与 SVN host 维度保存，仅在本机加密后落盘，不会出现在配置接口中。
      </div>

      <div>
        <label class="mb-1.5 block text-[12px] font-medium text-ink-500">SVN host</label>
        <el-input :model-value="host" disabled />
      </div>

      <div>
        <label class="mb-1.5 block text-[12px] font-medium text-ink-500">测试目录 URL</label>
        <el-input
          v-model="form.testDirUrl"
          name="svn-test-dir-url"
          type="url"
          autocomplete="off"
          spellcheck="false"
          placeholder="例如：https://samosvn/data/project/samo/GameDatas/…"
        />
        <div class="mt-1 text-[12px] text-ink-500">
          保存后会按当前登录用户与 host 记住该目录；“测试连接”会先保存凭据，再对这个目录执行一次 SVN 列表请求。
        </div>
      </div>

      <div>
        <label class="mb-1.5 block text-[12px] font-medium text-ink-500">用户名</label>
        <el-input
          v-model="form.username"
          name="svn-credential-username"
          placeholder="例如：alice…"
          spellcheck="false"
          autocomplete="off"
        />
      </div>

      <div>
        <label class="mb-1.5 block text-[12px] font-medium text-ink-500">密码</label>
        <el-input
          v-model="form.password"
          :type="form.showPassword ? 'text' : 'password'"
          name="svn-credential-password"
          show-password
          placeholder="登录 SVN 的密码…"
          autocomplete="new-password"
        />
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <button
          type="button"
          class="ec-btn ec-btn-secondary"
          :disabled="isSaving || isTesting"
          @click="handleCancel"
        >
          取消
        </button>
        <button
          type="button"
          class="ec-btn ec-btn-secondary"
          :disabled="!canTestConnection || isTesting || isSaving"
          @click="handleTestConnection"
        >
          {{ isTesting ? '测试中…' : '测试连接' }}
        </button>
        <button
          type="button"
          class="ec-btn ec-btn-primary"
          :disabled="!canSubmit || isSaving"
          @click="handleSubmit"
        >
          {{ isSaving ? '保存中…' : '保存' }}
        </button>
      </div>
    </template>
  </el-dialog>
</template>
