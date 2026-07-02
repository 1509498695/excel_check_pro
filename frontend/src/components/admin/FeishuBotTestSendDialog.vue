<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { apiTestSendFeishuBot } from '../../api/admin'
import PrimaryButton from '../shell/PrimaryButton.vue'
import SecondaryButton from '../shell/SecondaryButton.vue'

interface Props {
  modelValue: boolean
  projectId: number | null
  defaultChatId: string
  configured: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
}>()

interface DialogForm {
  chatId: string
  text: string
  useCard: boolean
}

const form = reactive<DialogForm>({
  chatId: '',
  text: '',
  useCard: false,
})

const isSending = ref(false)

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

watch(
  () => props.modelValue,
  (next) => {
    if (next) {
      // 每次打开时回填默认 chat_id，并清空文案 / 卡片开关。
      form.chatId = props.defaultChatId ?? ''
      form.text = ''
      form.useCard = false
    }
  },
)

const canSubmit = computed(() => {
  if (!props.projectId || !props.configured) return false
  return Boolean(form.chatId.trim() && form.text.trim())
})

function close(): void {
  if (isSending.value) return
  visible.value = false
}

async function handleSubmit(): Promise<void> {
  if (!props.projectId) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!canSubmit.value) {
    ElMessage.warning('请填写群 chat_id 与测试文案')
    return
  }
  isSending.value = true
  try {
    const response = await apiTestSendFeishuBot(props.projectId, {
      chat_id: form.chatId.trim(),
      text: form.text,
      use_card: form.useCard,
    })
    const messageId = response.data?.message_id || ''
    ElMessage.success(
      messageId ? `测试消息已发送（message_id：${messageId}）` : '测试消息已发送',
    )
    close()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '测试发送失败')
  } finally {
    isSending.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="飞书机器人测试发送"
    width="520px"
    destroy-on-close
    :close-on-click-modal="false"
  >
    <div class="flex flex-col gap-4">
      <div>
        <label class="mb-1.5 block text-[12px] font-medium text-ink-500">
          群 chat_id（必填，形如 oc_xxx）
        </label>
        <el-input
          v-model="form.chatId"
          name="test-send-chat-id"
          autocomplete="off"
          spellcheck="false"
          placeholder="例如：oc_1234567890abcdef…"
          maxlength="128"
          show-word-limit
        />
      </div>
      <div>
        <label class="mb-1.5 block text-[12px] font-medium text-ink-500">
          测试文案（必填，≤ 4000 字符）
        </label>
        <el-input
          v-model="form.text"
          type="textarea"
          :rows="4"
          name="test-send-text"
          autocomplete="off"
          maxlength="4000"
          show-word-limit
          placeholder="例如：来自 Excel-Check 的测试消息…"
        />
      </div>
      <div class="flex items-center gap-2">
        <el-switch v-model="form.useCard" />
        <span class="text-[13px] text-ink-700">使用富文本卡片发送（默认纯文本）</span>
      </div>
      <p v-if="!props.configured" class="text-[12px] text-ink-500">
        当前项目尚未保存 app_secret，请先保存配置后再测试发送。
      </p>
    </div>
    <template #footer>
      <div class="flex justify-end gap-2">
        <SecondaryButton :disabled="isSending" @click="close">取消</SecondaryButton>
        <PrimaryButton
          :disabled="!canSubmit || isSending"
          @click="handleSubmit"
        >
          {{ isSending ? '发送中…' : '发送测试消息' }}
        </PrimaryButton>
      </div>
    </template>
  </el-dialog>
</template>
