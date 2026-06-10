<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { apiChangePassword } from '../api/auth'
import { useAuthStore } from '../store/auth'
import { useFixedRulesStore } from '../store/fixedRules'
import { useWorkbenchStore } from '../store/workbench'
import AppCard from '../components/shell/AppCard.vue'
import DataTable from '../components/shell/DataTable.vue'
import EmptyState from '../components/shell/EmptyState.vue'
import PageHeader from '../components/shell/PageHeader.vue'
import PrimaryButton from '../components/shell/PrimaryButton.vue'
import SectionHeader from '../components/shell/SectionHeader.vue'
import StatusBadge from '../components/shell/StatusBadge.vue'

type StepIndex = 1 | 2 | 3

// 保持原有逻辑不变：密码修改与项目切换行为维持原实现。
const auth = useAuthStore()
const router = useRouter()

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const isChanging = ref(false)

const roleLabel = computed(() => {
  if (auth.isSuperAdmin) {
    return '超级管理员'
  }
  if (auth.currentRole === 'admin') {
    return '项目管理员'
  }
  return '普通用户'
})

function getProjectRoleLabel(role: string): string {
  return role === 'admin' ? '项目管理员' : '普通用户'
}

function getSectionStatusLabel(step: StepIndex): string {
  if (step === 1) {
    return auth.user ? '正常' : '待登录'
  }
  if (step === 2) {
    return '待操作'
  }
  if (step === 3) {
    return auth.userProjects.length ? '已就绪' : '待加入'
  }
  return '待操作'
}

function getSectionStatusTone(step: StepIndex): 'pending' | 'done' {
  if (step === 1) {
    return auth.user ? 'done' : 'pending'
  }
  if (step === 2) {
    return 'pending'
  }
  if (step === 3) {
    return auth.userProjects.length ? 'done' : 'pending'
  }
  return 'pending'
}

async function handleChangePassword(): Promise<void> {
  if (!oldPassword.value) {
    ElMessage.warning('请输入原密码')
    return
  }
  if (newPassword.value.length < 4) {
    ElMessage.warning('新密码至少 4 个字符')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }

  isChanging.value = true
  try {
    // 保留原有业务逻辑：密码修改继续走原有认证接口。
    await apiChangePassword(oldPassword.value, newPassword.value)
    ElMessage.success('密码修改成功')
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '修改失败')
  } finally {
    isChanging.value = false
  }
}

async function handleSwitchProject(projectId: number): Promise<void> {
  try {
    // 保留原有业务逻辑：项目切换与相关 store 重载保持原链路不变。
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

function openUserGuide(): void {
  const guideUrl = router.resolve({ name: 'user-guide' }).href
  window.open(guideUrl, '_blank', 'noopener,noreferrer')
}
</script>

<template>
  <div class="profile-settings-page flex h-full flex-col bg-canvas font-sans text-ink-700">
    <PageHeader breadcrumb="主页 / 个人设置" title="个人设置">
      <template #actions>
        <PrimaryButton @click="openUserGuide">
          <template #icon>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M4 19.5V5a2 2 0 0 1 2-2h10.5L20 6.5V19a2 2 0 0 1-2 2H6a2 2 0 0 1-2-1.5Z" />
              <path d="M15 3v5h5" />
              <path d="M8 12h8" />
              <path d="M8 16h6" />
            </svg>
          </template>
          系统使用说明
        </PrimaryButton>
      </template>
    </PageHeader>

    <div class="profile-settings-content flex flex-1 flex-col gap-6 overflow-y-auto px-8 py-8">
      <div class="profile-settings-stack flex w-full flex-col gap-6">
        <AppCard as="section" padding="none" class="profile-settings-card">
          <div class="profile-settings-card__inner">
            <div class="profile-settings-card__header">
              <SectionHeader
                variant="workbench"
                step="01"
                title="账号信息"
                description="账户基础信息与当前登录态"
                :status-label="getSectionStatusLabel(1)"
                :status-tone="getSectionStatusTone(1)"
              />
            </div>

            <div class="profile-settings-card__body">
              <DataTable aria-label="账号信息">
                <template #head>
                  <tr>
                    <th class="w-1/4">用户名</th>
                    <th class="w-1/4">角色</th>
                    <th class="w-1/4">当前项目</th>
                    <th class="w-1/4">可访问项目</th>
                  </tr>
                </template>
                <template #body>
                  <tr class="bg-white transition hover:bg-gray-50">
                    <td>
                      <span class="text-[14px] font-semibold text-ink-900">
                        {{ auth.user?.username ?? '—' }}
                      </span>
                    </td>
                    <td>
                      <StatusBadge
                        :type="auth.isSuperAdmin ? 'danger' : auth.currentRole === 'admin' ? 'warning' : 'neutral'"
                        :label="roleLabel"
                      />
                    </td>
                    <td>
                      <span class="text-[14px] font-semibold text-ink-900">
                        {{ auth.currentProjectName || '未选择' }}
                      </span>
                    </td>
                    <td>
                      <span class="text-[14px] text-ink-900">
                        <span class="font-mono font-semibold">{{ auth.userProjects.length }}</span>
                        <span class="ml-1 text-[13px] font-normal text-ink-500">个</span>
                      </span>
                    </td>
                  </tr>
                </template>
              </DataTable>
            </div>
          </div>
        </AppCard>

        <AppCard as="section" padding="none" class="profile-settings-card">
          <div class="profile-settings-card__inner">
            <div class="profile-settings-card__header">
              <SectionHeader
                variant="workbench"
                step="02"
                title="修改密码"
                description="新密码需为 4 个字符；保存后立即生效，下一次登录将使用新密码"
                :status-label="getSectionStatusLabel(2)"
                :status-tone="getSectionStatusTone(2)"
              />
            </div>

            <form
              class="profile-password-form profile-settings-card__body"
              @submit.prevent="handleChangePassword"
            >
              <div class="profile-password-grid">
                <div class="profile-form-field">
                  <label class="mb-1.5 block text-[12px] font-medium text-ink-500">原密码</label>
                  <el-input
                    v-model="oldPassword"
                    type="password"
                    placeholder="请输入原密码"
                    show-password
                  />
                </div>
                <div class="profile-form-field">
                  <label class="mb-1.5 block text-[12px] font-medium text-ink-500">新密码</label>
                  <el-input
                    v-model="newPassword"
                    type="password"
                    placeholder="请输入新密码（至少 4 个字符）"
                    show-password
                  />
                </div>
                <div class="profile-form-field">
                  <label class="mb-1.5 block text-[12px] font-medium text-ink-500">确认新密码</label>
                  <el-input
                    v-model="confirmPassword"
                    type="password"
                    placeholder="请再次输入新密码"
                    show-password
                  />
                </div>
              </div>

              <div class="profile-password-actions">
                <PrimaryButton
                  native-type="submit"
                  :disabled="isChanging"
                >
                  {{ isChanging ? '保存中…' : '保存新密码' }}
                </PrimaryButton>
              </div>
            </form>
          </div>
        </AppCard>

        <AppCard as="section" padding="none" class="profile-settings-card">
          <div class="profile-settings-card__inner">
            <div class="profile-settings-card__header">
              <SectionHeader
                variant="workbench"
                step="03"
                title="我的项目"
                :description="auth.userProjects.length
                  ? `共 ${auth.userProjects.length} 个项目；点击项目可切换当前项目`
                  : '当前账号未加入任何项目'"
                :status-label="getSectionStatusLabel(3)"
                :status-tone="getSectionStatusTone(3)"
              />
            </div>

            <div
              v-if="!auth.userProjects.length"
              class="profile-empty-panel profile-settings-card__body"
            >
              <EmptyState title="暂未加入任何项目" />
            </div>

            <div v-else class="profile-settings-card__body">
              <DataTable aria-label="我的项目">
                <template #head>
                  <tr>
                    <th class="w-1/4">项目名称</th>
                    <th class="w-1/4">角色</th>
                    <th class="w-1/4">状态</th>
                    <th class="w-1/4">操作</th>
                  </tr>
                </template>
                <template #body>
                  <!-- 保留原有业务逻辑：项目列表仍基于 auth.userProjects 遍历并继续调用原切换逻辑 -->
                  <tr
                    v-for="project in auth.userProjects"
                    :key="project.project_id"
                    class="bg-white transition hover:bg-gray-50"
                  >
                    <td>
                      <div class="flex items-center gap-2">
                        <span
                          class="truncate text-[14px] font-semibold"
                          :class="
                            project.project_id === auth.currentProjectId
                              ? 'text-accent-ink'
                              : 'text-ink-900'
                          "
                        >
                          {{ project.project_name }}
                        </span>
                        <span
                          v-if="project.project_id === auth.currentProjectId"
                          class="profile-current-badge"
                        >
                          当前
                        </span>
                      </div>
                    </td>
                    <td>
                      <StatusBadge
                        :type="project.role === 'admin' ? 'warning' : 'neutral'"
                        :label="getProjectRoleLabel(project.role)"
                      />
                    </td>
                    <td>
                      <StatusBadge
                        v-if="project.project_id === auth.currentProjectId"
                        type="success"
                        label="当前使用"
                      />
                      <StatusBadge v-else type="neutral" label="未启用" />
                    </td>
                    <td>
                      <button
                        v-if="project.project_id !== auth.currentProjectId"
                        type="button"
                        class="ec-action-link"
                        @click="handleSwitchProject(project.project_id)"
                      >
                        切换到此项目
                      </button>
                      <span
                        v-else
                        class="text-[12px] text-ink-500"
                      >
                        使用中
                      </span>
                    </td>
                  </tr>
                </template>
              </DataTable>
            </div>
          </div>
        </AppCard>
      </div>
    </div>
  </div>
</template>
