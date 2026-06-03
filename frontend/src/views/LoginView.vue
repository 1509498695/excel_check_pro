<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '../store/auth'
import { preloadRouteComponent } from '../router/routePreload'

// 保持原有逻辑不变：登录校验、鉴权调用与跳转链路保持现状。
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const isLoading = ref(false)

function getLoginTargetPath(): string {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  return redirect.startsWith('/') ? redirect : '/'
}

onMounted(() => {
  window.setTimeout(() => {
    preloadRouteComponent(getLoginTargetPath())
  }, 0)
})

async function handleLogin(): Promise<void> {
  if (!username.value.trim() || !password.value) {
    ElMessage.warning('用户名与密码均为必填')
    return
  }

  isLoading.value = true
  preloadRouteComponent(getLoginTargetPath())
  try {
    // 保留原有业务逻辑：登录继续调用原 auth store 鉴权链路。
    await auth.login(username.value.trim(), password.value)
    ElMessage.success('登录成功')
    router.push(getLoginTargetPath())
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '登录失败')
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen w-screen flex-col items-center justify-center bg-canvas px-6 font-sans text-ink-700">
    <!-- 品牌：方块 + 表格 SVG（与左边栏同款，强化一致性） -->
    <div class="flex flex-col items-center gap-3 mb-8">
      <div class="flex h-12 w-12 items-center justify-center rounded-md bg-accent text-white">
        <svg viewBox="0 0 24 24" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M4 5h16v14H4z M4 10h16 M9 5v14" />
        </svg>
      </div>
      <div class="text-center">
        <div class="text-[18px] font-semibold tracking-tight text-ink-900">Excel Check</div>
          <div class="text-[12px] text-ink-500">配置表个人校验</div>
      </div>
    </div>

    <!-- 登录卡 -->
    <form
      class="w-[380px] rounded-card border border-line bg-card p-6 shadow-card-2"
      data-testid="login-form"
      @submit.prevent="handleLogin"
    >
      <div class="mb-5">
        <h1 class="text-[15px] font-semibold tracking-tight text-ink-900">登录</h1>
            <p class="mt-1 text-[12px] text-ink-500">使用账户名与密码进入个人校验</p>
      </div>

      <div class="flex flex-col gap-4">
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">用户名</label>
          <el-input v-model="username" placeholder="例如：admin" autofocus data-testid="login-username" />
        </div>
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">密码</label>
          <el-input v-model="password" type="password" placeholder="密码" show-password data-testid="login-password" />
        </div>

        <button
          type="submit"
          class="ec-btn ec-btn-primary mt-2 w-full"
          data-testid="login-submit"
          :disabled="isLoading"
        >
          {{ isLoading ? '登录中…' : '登录' }}
        </button>
      </div>

      <div class="mt-5 text-center text-[12px] text-ink-500">
        还没有账号？
        <router-link to="/register" class="text-accent-ink transition hover:underline">立即注册</router-link>
      </div>
    </form>

    <div class="mt-10 text-[12px] text-ink-500">© Excel Check · 2026</div>
  </div>
</template>
