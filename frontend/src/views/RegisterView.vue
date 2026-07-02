<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { apiListProjectsPublic } from '../api/auth'
import { useAuthStore } from '../store/auth'
import type { ProjectPublic } from '../types/auth'

// 保持原有逻辑不变：注册校验、项目列表加载与成功后的登录态处理不做改动。
const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const selectedProjectId = ref<number | null>(null)
const projects = ref<ProjectPublic[]>([])
const isLoading = ref(false)

onMounted(async () => {
  try {
    // 保留原有业务逻辑：注册页项目列表继续通过原公开接口加载。
    const response = await apiListProjectsPublic()
    projects.value = response.data
    if (projects.value.length) {
      selectedProjectId.value = projects.value[0].id
    }
  } catch {
    ElMessage.warning('暂无可用项目，请联系管理员创建项目后再注册')
  }
})

async function handleRegister(): Promise<void> {
  if (!username.value.trim()) {
    ElMessage.warning('请填写用户名')
    return
  }
  if (username.value.trim().length < 2) {
    ElMessage.warning('用户名至少 2 个字符')
    return
  }
  if (!password.value || password.value.length < 4) {
    ElMessage.warning('密码至少 4 个字符')
    return
  }
  if (password.value !== confirmPassword.value) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }
  if (selectedProjectId.value === null) {
    ElMessage.warning('请选择归属项目')
    return
  }

  isLoading.value = true
  try {
    // 保留原有业务逻辑：注册成功后的登录态建立与跳转仍复用原有 store 行为。
    await auth.register(username.value.trim(), password.value, selectedProjectId.value)
    ElMessage.success('注册成功')
    router.push('/')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '注册失败')
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen w-screen flex-col items-center justify-center bg-canvas px-6 py-10 font-sans text-ink-700">
    <!-- 品牌 -->
    <div class="flex flex-col items-center gap-3 mb-8">
      <div class="flex h-12 w-12 items-center justify-center rounded-md bg-accent text-white">
        <svg viewBox="0 0 24 24" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M4 5h16v14H4z M4 10h16 M9 5v14" />
        </svg>
      </div>
      <div class="text-center">
        <div class="text-[18px] font-semibold tracking-tight text-ink-900">Excel Check</div>
          <div class="text-[12px] text-ink-500">配置表个人校验</div>
      </div>
    </div>

    <!-- 注册卡 -->
    <form
      class="w-[380px] rounded-card border border-line bg-card p-6 shadow-card-2"
      @submit.prevent="handleRegister"
    >
      <div class="mb-5">
        <h1 class="text-[15px] font-semibold tracking-tight text-ink-900">注册</h1>
        <p class="mt-1 text-[12px] text-ink-500">创建账号并加入项目</p>
      </div>

      <div class="flex flex-col gap-4">
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">用户名</label>
          <el-input
            v-model="username"
            name="username"
            autocomplete="username"
            :spellcheck="false"
            placeholder="至少 2 个字符…"
          />
        </div>
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">密码</label>
          <el-input
            v-model="password"
            name="new-password"
            type="password"
            autocomplete="new-password"
            placeholder="至少 4 个字符…"
            show-password
          />
        </div>
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">确认密码</label>
          <el-input
            v-model="confirmPassword"
            name="confirm-password"
            type="password"
            autocomplete="new-password"
            placeholder="再次输入密码…"
            show-password
          />
        </div>
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">归属项目</label>
          <el-select v-model="selectedProjectId" name="project" autocomplete="off" placeholder="选择归属项目…" class="w-full">
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </div>

        <button
          type="submit"
          class="ec-btn ec-btn-primary mt-2 w-full"
          :disabled="isLoading || !projects.length"
        >
          {{ isLoading ? '注册中…' : '注册' }}
        </button>
      </div>

      <div class="mt-5 text-center text-[12px] text-ink-500">
        已有账号？
        <router-link to="/login" class="text-accent-ink transition hover:underline">返回登录</router-link>
      </div>
    </form>

    <div class="mt-10 text-[12px] text-ink-500">© Excel Check · 2026</div>
  </div>
</template>
