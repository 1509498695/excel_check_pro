<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAuthStore } from './store/auth'
import { useFixedRulesStore } from './store/fixedRules'
import { useWorkbenchStore } from './store/workbench'

// 保持原有逻辑不变：仅做共享壳层的视觉重构，不调整认证、项目切换或路由跳转行为。
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const showShell = computed(() => auth.isLoggedIn && route.meta.guest !== true)

const currentRoleLabel = computed(() => {
  if (auth.isSuperAdmin) {
    return '超级管理员'
  }
  if (auth.currentRole === 'admin') {
    return '项目管理员'
  }
  return '普通用户'
})

const navItems = computed(() => {
  const items: Array<{
    to: string
    label: string
    routeName: string
    show: boolean
    icon: string
  }> = [
    {
      to: '/',
      label: '个人校验',
      routeName: 'main-board',
      show: true,
      icon: 'M3 12l9-9 9 9 M5 10v10h14V10',
    },
    {
      to: '/fixed-rules',
      label: '项目校验',
      routeName: 'fixed-rules-board',
      show: true,
      icon: 'M5 5h14v14H5z M9 11h6 M9 15h6',
    },
    {
      to: '/rule-configs',
      label: '查询配置',
      routeName: 'rule-configs',
      show: true,
      icon: 'M4 6h16 M4 12h16 M4 18h16 M8 6v12',
    },
    {
      to: '/admin',
      label: '管理后台',
      routeName: 'admin',
      show: auth.isProjectAdmin,
      icon: 'M3 5h18 M3 12h18 M3 19h18',
    },
    {
      to: '/profile',
      label: '个人设置',
      routeName: 'profile',
      show: true,
      icon: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8',
    },
  ]
  return items.filter((item) => item.show)
})

function isActive(routeName: string): boolean {
  return route.name === routeName || route.meta.activeNav === routeName
}

function handleLogout(): void {
  // 保留原有业务逻辑：退出仍走原 auth store 链路。
  auth.logout()
  router.push('/login')
  ElMessage.success('已退出登录')
}

async function handleSwitchProject(projectId: number): Promise<void> {
  try {
    // 保留原有业务逻辑：项目切换仍复用原有鉴权接口与前端状态刷新链路。
    await auth.switchProject(projectId)
    const workbench = useWorkbenchStore()
    const fixedRules = useFixedRulesStore()
    fixedRules.resetState()
    await Promise.all([
      workbench.loadFromServer(),
      fixedRules.loadConfig().catch(() => {}),
    ])
    ElMessage.success('项目已切换')
    router.push('/')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '切换失败')
  }
}
</script>

<template>
  <div
    v-if="showShell"
    class="ec-app-shell"
  >
    <!-- ============= 左侧固定边栏 ============= -->
    <aside class="ec-sidebar">
      <!-- 品牌：主色方块 + 表格 SVG -->
      <div class="ec-sidebar-brand">
        <div class="ec-sidebar-brand__mark">
          <svg viewBox="0 0 24 24" class="ec-sidebar-brand__icon" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 5h16v14H4z M4 10h16 M9 5v14" />
          </svg>
        </div>
        <div class="ec-sidebar-brand__copy">
          <div class="ec-sidebar-brand__title">Excel Check</div>
          <div class="ec-sidebar-brand__subtitle">配置表个人校验</div>
        </div>
      </div>

      <!-- 主导航 -->
      <nav class="ec-sidebar-nav" aria-label="主导航">
        <div class="ec-sidebar-nav__label">主菜单</div>
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="ec-nav-link"
          :data-testid="`nav-${item.routeName}`"
          :class="{ 'ec-nav-link--active': isActive(item.routeName) }"
        >
          <svg
            class="ec-nav-link__icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path :d="item.icon" />
          </svg>
          <span class="ec-nav-link__label">{{ item.label }}</span>
        </RouterLink>
      </nav>

      <!-- 底部项目卡 + 用户菜单 -->
      <div class="ec-sidebar-footer">
        <div class="ec-project-card">
          <div class="ec-project-card__label">当前项目</div>
          <div class="ec-project-card__name">
            {{ auth.currentProjectName || '未选择项目' }}
          </div>
          <div class="ec-project-card__role">{{ currentRoleLabel }}</div>
        </div>

        <div class="ec-user-menu">
          <el-dropdown trigger="click" placement="top-start">
            <button
              type="button"
              class="ec-user-trigger"
            >
              <span class="ec-user-trigger__avatar">
                {{ auth.user?.username?.charAt(0)?.toUpperCase() ?? 'U' }}
              </span>
              <span class="ec-user-trigger__name">
                {{ auth.user?.username ?? '' }}
              </span>
              <svg
                class="ec-user-trigger__arrow"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <path d="m6 9 6 6 6-6" />
              </svg>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="router.push('/profile')">个人设置</el-dropdown-item>
                <!-- // 保留原有业务逻辑：项目列表仍基于 auth.userProjects 遍历，点击继续走原有切换链路 -->
                <el-dropdown-item
                  v-for="project in auth.userProjects"
                  :key="project.project_id"
                  :disabled="project.project_id === auth.currentProjectId"
                  @click="handleSwitchProject(project.project_id)"
                >
                  {{ project.project_name }}
                  {{ project.project_id === auth.currentProjectId ? '（当前）' : '' }}
                </el-dropdown-item>
                <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </aside>

    <!-- ============= 右侧主区：纯 router-view，TopBar 由各页面自己提供 ============= -->
    <main class="ec-app-main">
      <router-view />
    </main>
  </div>

  <router-view v-else />
</template>
