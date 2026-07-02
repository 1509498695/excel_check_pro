<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'

import AppCard from '../components/shell/AppCard.vue'
import {
  apiCreateProject,
  apiDeleteProject,
  apiListProjectMembers,
  apiListProjects,
  apiMoveMemberProject,
  apiRemoveMember,
  apiResetUserPassword,
  apiSetMemberRole,
  apiUpdateProject,
} from '../api/admin'
import FeishuBotConfigCard from '../components/admin/FeishuBotConfigCard.vue'
import SourceEvidenceAdminConfigCard from '../components/admin/SourceEvidenceAdminConfigCard.vue'
import { useAuthStore } from '../store/auth'
import type { ProjectDetail, ProjectMember } from '../types/auth'
import DataTable from '../components/shell/DataTable.vue'
import EmptyState from '../components/shell/EmptyState.vue'
import MetricCard from '../components/shell/MetricCard.vue'
import PageHeader from '../components/shell/PageHeader.vue'
import PrimaryButton from '../components/shell/PrimaryButton.vue'
import SectionHeader from '../components/shell/SectionHeader.vue'
import SecondaryButton from '../components/shell/SecondaryButton.vue'
import StatusBadge from '../components/shell/StatusBadge.vue'

const DEFAULT_PROJECT_NAME = '默认项目'

type StepIndex = 1 | 2 | 3
type StatTone = 'pending' | 'active' | 'done' | 'warn' | 'error'

// 保持原有逻辑不变：项目管理、成员治理与弹窗交互仅做视觉重构，不改权限与接口调用。
const auth = useAuthStore()
const projects = ref<ProjectDetail[]>([])
const selectedProject = ref<ProjectDetail | null>(null)
const members = ref<ProjectMember[]>([])
const isLoadingProjects = ref(false)
const isLoadingMembers = ref(false)
const isProjectDialogVisible = ref(false)
const isSavingProject = ref(false)
const isMoveProjectDialogVisible = ref(false)
const isMovingMemberProject = ref(false)
const projectDialogMode = ref<'create' | 'edit'>('create')
const projectKeyword = ref('')
const projectForm = reactive({
  name: '',
  description: '',
})
const moveProjectForm = reactive({
  userId: null as number | null,
  username: '',
  targetProjectId: null as number | null,
})
let membersLoadRequestId = 0

onMounted(async () => {
  // 保留原有业务逻辑：页面进入后仍先加载项目列表，再按原规则加载成员。
  await loadProjects()
})

const projectDialogTitle = computed(() =>
  projectDialogMode.value === 'create' ? '创建项目' : '编辑项目',
)

const canCreateProject = computed(() => auth.isSuperAdmin)
const canManageFeishuBot = computed(
  () => auth.isProjectAdmin && selectedProject.value !== null,
)
const canSubmitProject = computed(() => Boolean(projectForm.name.trim()))
const moveTargetProjects = computed(() =>
  projects.value.filter((project) => project.id !== selectedProject.value?.id),
)
const canSubmitMoveProject = computed(() => moveProjectForm.targetProjectId !== null)

const filteredProjects = computed(() => {
  const keyword = projectKeyword.value.trim().toLowerCase()
  if (!keyword) return projects.value
  return projects.value.filter((project) => project.name.toLowerCase().includes(keyword))
})

const superAdminCount = computed(() => members.value.filter((m) => m.is_super_admin).length)

const overviewItems = computed<
  Array<{
    label: string
    value: number | string
    pendingHint: string
    readyHint: string
    pendingTone: StatTone
    readyTone: StatTone
    isReady: boolean
  }>
>(() => [
  {
    label: '项目总数',
    value: projects.value.length,
    pendingHint: '未加载',
    readyHint: '已就绪',
    pendingTone: 'pending',
    readyTone: 'done',
    isReady: projects.value.length > 0,
  },
  {
    label: '当前项目成员',
    value: members.value.length,
    pendingHint: '待选择项目',
    readyHint: '已加载',
    pendingTone: 'pending',
    readyTone: 'done',
    isReady: members.value.length > 0,
  },
  {
    label: '超级管理员',
    value: superAdminCount.value,
    pendingHint: '当前项目无',
    readyHint: '已配置',
    pendingTone: 'pending',
    readyTone: 'done',
    isReady: superAdminCount.value > 0,
  },
  {
    label: '我的项目范围',
    value: auth.currentProjectName || '未设置',
    pendingHint: '已就绪',
    readyHint: '已就绪',
    pendingTone: 'pending',
    readyTone: 'done',
    isReady: Boolean(auth.currentProjectName),
  },
])

function getSectionStatusLabel(step: StepIndex): string {
  if (step === 1) {
    return projects.value.length ? '已就绪' : '待配置'
  }
  if (step === 2) {
    return selectedProject.value ? '已就绪' : '待配置'
  }
  return selectedProject.value ? '已就绪' : '待配置'
}

function getSectionStatusTone(step: StepIndex): 'pending' | 'done' {
  return getSectionStatusLabel(step) === '已就绪' ? 'done' : 'pending'
}

const metricIconTones = ['primary', 'success', 'purple', 'warning'] as const

function getMetricIconTone(index: number): (typeof metricIconTones)[number] {
  return metricIconTones[index] ?? 'primary'
}

async function loadProjects(): Promise<void> {
  isLoadingProjects.value = true
  try {
    // 保留原有业务逻辑：项目列表继续通过原有 admin API 获取。
    const response = await apiListProjects()
    projects.value = response.data

    const nextSelectedProject =
      projects.value.find((item) => item.id === selectedProject.value?.id) ?? projects.value[0] ?? null

    if (!nextSelectedProject) {
      selectedProject.value = null
      members.value = []
      return
    }

    selectedProject.value = nextSelectedProject
    void loadMembers(nextSelectedProject)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载项目列表失败')
    projects.value = []
    selectedProject.value = null
    members.value = []
  } finally {
    isLoadingProjects.value = false
  }
}

async function loadMembers(project: ProjectDetail): Promise<void> {
  const requestId = ++membersLoadRequestId
  selectedProject.value = project
  isLoadingMembers.value = true
  try {
    // 保留原有业务逻辑：成员列表继续消费原有项目成员接口。
    const response = await apiListProjectMembers(project.id)
    if (requestId === membersLoadRequestId && selectedProject.value?.id === project.id) {
      members.value = response.data
    }
  } catch (error) {
    if (requestId === membersLoadRequestId && selectedProject.value?.id === project.id) {
      ElMessage.error(error instanceof Error ? error.message : '加载成员列表失败')
      members.value = []
    }
  } finally {
    if (requestId === membersLoadRequestId) {
      isLoadingMembers.value = false
    }
  }
}

async function selectProject(project: ProjectDetail): Promise<void> {
  await loadMembers(project)
}

function openCreateProjectDialog(): void {
  projectDialogMode.value = 'create'
  projectForm.name = ''
  projectForm.description = ''
  isProjectDialogVisible.value = true
}

function openEditProjectDialog(project: ProjectDetail): void {
  projectDialogMode.value = 'edit'
  projectForm.name = project.name
  projectForm.description = project.description ?? ''
  selectedProject.value = project
  isProjectDialogVisible.value = true
}

function closeProjectDialog(): void {
  isProjectDialogVisible.value = false
}

function openMoveProjectDialog(member: ProjectMember): void {
  moveProjectForm.userId = member.user_id
  moveProjectForm.username = member.username
  moveProjectForm.targetProjectId = moveTargetProjects.value[0]?.id ?? null
  isMoveProjectDialogVisible.value = true
}

function closeMoveProjectDialog(): void {
  isMoveProjectDialogVisible.value = false
  moveProjectForm.userId = null
  moveProjectForm.username = ''
  moveProjectForm.targetProjectId = null
}

async function handleSubmitProject(): Promise<void> {
  if (!canSubmitProject.value) {
    ElMessage.warning('项目名称不能为空')
    return
  }

  isSavingProject.value = true
  const payload = {
    name: projectForm.name.trim(),
    description: projectForm.description.trim(),
  }

  try {
    if (projectDialogMode.value === 'create') {
      const response = await apiCreateProject(payload.name, payload.description)
      ElMessage.success('项目创建成功')
      await loadProjects()
      const createdProject = projects.value.find((item) => item.id === response.data.id)
      if (createdProject) {
        await selectProject(createdProject)
      }
    } else {
      if (!selectedProject.value) {
        throw new Error('未找到要编辑的项目')
      }
      await apiUpdateProject(selectedProject.value.id, payload)
      ElMessage.success('项目更新成功')
      await loadProjects()
    }
    closeProjectDialog()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '保存项目失败')
  } finally {
    isSavingProject.value = false
  }
}

async function handleDeleteProject(project: ProjectDetail): Promise<void> {
  if (project.name === DEFAULT_PROJECT_NAME) {
    ElMessage.warning('默认项目不可删除')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确认永久删除项目「${project.name}」？该项目下的成员关系、项目校验配置和个人校验配置都会一并清理，且无法恢复。`,
      '删除项目',
      {
        confirmButtonText: '永久删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      },
    )
    await apiDeleteProject(project.id)
    ElMessage.success('项目已删除，正在刷新页面')
    window.setTimeout(() => {
      window.location.reload()
    }, 300)
  } catch (error) {
    if (error === 'cancel' || error === 'close') {
      return
    }
    ElMessage.error(error instanceof Error ? error.message : '删除项目失败')
  }
}

async function handleSetRole(member: ProjectMember, role: string): Promise<void> {
  if (!selectedProject.value) return
  try {
    await apiSetMemberRole(selectedProject.value.id, member.user_id, role)
    ElMessage.success(`已将 ${member.username} 设为${role === 'admin' ? '管理员' : '普通用户'}`)
    await loadMembers(selectedProject.value)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '操作失败')
  }
}

async function handleSubmitMoveProject(): Promise<void> {
  if (!selectedProject.value || moveProjectForm.userId === null || moveProjectForm.targetProjectId === null) {
    return
  }

  isMovingMemberProject.value = true
  const targetProjectId = moveProjectForm.targetProjectId
  const shouldSyncCurrentProject =
    auth.isSuperAdmin &&
    moveProjectForm.userId === auth.user?.id &&
    auth.currentProjectId !== targetProjectId
  try {
    await apiMoveMemberProject(
      selectedProject.value.id,
      moveProjectForm.userId,
      targetProjectId,
    )
    if (shouldSyncCurrentProject) {
      // 保留原有业务逻辑：仅在超级管理员调整自己的归属项目后，同步当前登录态项目上下文。
      await auth.switchProject(targetProjectId)
    }
    ElMessage.success('归属项目已更新')
    closeMoveProjectDialog()
    await loadProjects()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '调整归属项目失败')
  } finally {
    isMovingMemberProject.value = false
  }
}

async function handleRemoveMember(member: ProjectMember): Promise<void> {
  if (!selectedProject.value) return
  try {
    const isDefaultProjectSelected = isDefaultProject(selectedProject.value)
    const confirmMessage = isDefaultProjectSelected
      ? `确认删除用户「${member.username}」？删除后将永久移除该账号及其项目关系，且不可恢复。`
      : `确认删除成员「${member.username}」？删除后将把该成员移入默认项目，并从当前项目中移除。`

    await ElMessageBox.confirm(
      confirmMessage,
      '删除成员',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
    await apiRemoveMember(selectedProject.value.id, member.user_id)
    ElMessage.success(
      isDefaultProjectSelected ? '用户账号已删除' : '成员已移入默认项目',
    )
    await loadProjects()
  } catch {
    // 取消
  }
}

async function handleResetPassword(member: ProjectMember): Promise<void> {
  try {
    const result = await ElMessageBox.prompt(
      `为用户「${member.username}」设置新密码（至少 4 个字符）`,
      '重置密码',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputType: 'password',
        inputValidator: (value) =>
          Boolean(value && value.length >= 4) || '密码至少 4 个字符',
      },
    )
    await apiResetUserPassword(member.user_id, result.value)
    ElMessage.success('密码已重置，请通知用户使用新密码登录')
  } catch {
    // 取消
  }
}

function canMoveMemberProject(member: ProjectMember): boolean {
  if (member.is_super_admin) {
    return auth.isSuperAdmin && member.user_id === auth.user?.id && moveTargetProjects.value.length > 0
  }
  if (member.role !== 'user') {
    return false
  }
  return moveTargetProjects.value.length > 0
}

function canRemoveMember(member: ProjectMember): boolean {
  if (!selectedProject.value) {
    return false
  }
  if (member.user_id === auth.user?.id) {
    return false
  }
  if (isDefaultProject(selectedProject.value) && !auth.isSuperAdmin) {
    return false
  }
  return true
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

function isDefaultProject(project: ProjectDetail): boolean {
  return project.name === DEFAULT_PROJECT_NAME
}

function getMemberRoleLabel(member: ProjectMember): string {
  if (member.is_super_admin) {
    return '超级管理员'
  }
  return member.role === 'admin' ? '项目管理员' : '普通用户'
}
</script>

<template>
  <div class="admin-dashboard-page flex h-full flex-col bg-canvas font-sans text-ink-700">
    <PageHeader breadcrumb="主页 / 管理后台" title="管理后台">
      <template #actions>
        <el-input
          v-model="projectKeyword"
          name="project-search"
          autocomplete="off"
          placeholder="搜索项目…"
          :prefix-icon="Search"
          clearable
          size="default"
          class="admin-dashboard-search"
        />
        <PrimaryButton
          v-if="canCreateProject"
          @click="openCreateProjectDialog"
        >
          <template #icon><Plus /></template>
          新建项目
        </PrimaryButton>
      </template>
    </PageHeader>

    <div class="admin-dashboard-content flex flex-1 flex-col gap-6 overflow-y-auto px-8 py-8">
      <!-- KPI -->
      <section aria-label="概览" class="grid grid-cols-4 gap-4">
        <!-- 保留原有业务逻辑：概览卡仍基于 overviewItems 计算结果遍历渲染 -->
        <MetricCard
          v-for="(item, index) in overviewItems"
          :key="item.label"
          :label="item.label"
          :value="item.value"
          status-label="已就绪"
          status-type="success"
          :icon-tone="getMetricIconTone(index)"
        >
          <template #icon>
            <svg v-if="item.label === '项目总数'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4H10l2 2h5.5A2.5 2.5 0 0 1 20 8.5v8A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5z" />
            </svg>
            <svg v-else-if="item.label === '当前项目成员'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M12 5a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z" />
              <path d="M5 20a7 7 0 0 1 14 0" />
              <path d="M4 11.5a2.5 2.5 0 1 0 0-5" />
              <path d="M20 6.5a2.5 2.5 0 1 0 0 5" />
            </svg>
            <svg v-else-if="item.label === '超级管理员'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M16 11a4 4 0 1 0-8 0 4 4 0 0 0 8 0Z" />
              <path d="M4 21a8 8 0 0 1 16 0" />
              <path d="M19 4v4M21 6h-4" />
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M12 3 14.7 8.7 21 9.6 16.5 14 17.6 20.2 12 17.2 6.4 20.2 7.5 14 3 9.6 9.3 8.7z" />
            </svg>
          </template>
        </MetricCard>
      </section>

      <!-- 单列全宽通栏：01 项目列表 / 02 项目详情 / 03 项目成员 依次堆叠 -->
      <!-- 01 项目列表 -->
      <AppCard
        v-loading="isLoadingProjects"
        as="article"
        padding="none"
        class="admin-dashboard-card"
      >
        <div class="admin-dashboard-card__inner">
          <div class="admin-dashboard-card__header">
            <SectionHeader
              variant="workbench"
              step="01"
              title="项目列表"
              :description="auth.isSuperAdmin ? '全部项目，可创建、编辑或删除' : '仅展示你可管理的项目'"
              :status-label="getSectionStatusLabel(1)"
              :status-tone="getSectionStatusTone(1)"
            />
          </div>

          <div class="admin-dashboard-card__body">
            <div
              v-if="!projects.length"
              class="admin-empty-panel"
            >
              <EmptyState title="暂无可管理项目" />
            </div>

            <div
              v-else-if="!filteredProjects.length"
              class="admin-empty-panel"
            >
              <EmptyState title="没有匹配的项目" :description="`没有匹配「${projectKeyword}」的项目`" />
            </div>

            <nav v-else class="admin-project-grid">
              <!-- 保留原有业务逻辑：项目列表仍基于 filteredProjects 遍历，点击继续走原有选中与加载成员逻辑 -->
              <article
                v-for="project in filteredProjects"
                :key="project.id"
                class="admin-project-card"
                :class="selectedProject?.id === project.id ? 'is-active' : ''"
                @click="selectProject(project)"
              >
                <div>
                  <div class="flex items-start justify-between gap-2">
                    <div class="admin-project-card__name">
                      {{ project.name }}
                    </div>
                    <div class="flex shrink-0 items-center gap-1">
                      <span
                        v-if="selectedProject?.id === project.id"
                        class="admin-current-badge"
                      >
                        当前
                      </span>
                      <StatusBadge
                        v-if="isDefaultProject(project)"
                        type="neutral"
                        label="默认"
                      />
                    </div>
                  </div>
                  <div class="admin-project-card__meta">
                    成员 {{ project.member_count ?? 0 }} · {{ formatDate(project.created_at) }}
                  </div>
                </div>
                <div class="admin-project-card__actions">
                  <button
                    type="button"
                    class="ec-action-link"
                    @click.stop="openEditProjectDialog(project)"
                  >
                    编辑
                  </button>
                  <button
                    v-if="auth.isSuperAdmin && !isDefaultProject(project)"
                    type="button"
                    class="ec-action-link-danger"
                    @click.stop="handleDeleteProject(project)"
                  >
                    删除
                  </button>
                </div>
              </article>
            </nav>
          </div>
        </div>
      </AppCard>

      <!-- 02 项目详情 -->
      <AppCard as="article" padding="none" class="admin-dashboard-card">
        <div class="admin-dashboard-card__inner">
          <div class="admin-dashboard-card__header">
            <SectionHeader
              variant="workbench"
              step="02"
              title="项目详情"
              :description="selectedProject ? (selectedProject.description || '无项目描述') : '请在左侧选择项目'"
              :status-label="getSectionStatusLabel(2)"
              :status-tone="getSectionStatusTone(2)"
            />
            <div class="admin-dashboard-card__actions">
              <SecondaryButton
                v-if="selectedProject && auth.isSuperAdmin && !isDefaultProject(selectedProject)"
                size="sm"
                @click="handleDeleteProject(selectedProject)"
              >
                删除项目
              </SecondaryButton>
              <PrimaryButton
                v-if="selectedProject"
                size="sm"
                @click="openEditProjectDialog(selectedProject)"
              >
                编辑项目
              </PrimaryButton>
            </div>
          </div>

          <div class="admin-dashboard-card__body">
            <div
              v-if="!selectedProject"
              class="admin-empty-panel"
            >
              <EmptyState title="当前没有可管理项目">
                <template #icon>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M4 4h16v16H4z M4 9h16" />
                  </svg>
                </template>
              </EmptyState>
            </div>

            <div
              v-else-if="selectedProject"
              class="min-w-0"
            >
              <DataTable aria-label="项目详情">
                <template #head>
                  <tr>
                    <th class="w-1/5">项目名称</th>
                    <th class="w-1/5">归属类型</th>
                    <th class="w-1/5">成员数</th>
                    <th class="w-1/5">创建时间</th>
                    <th class="w-1/5">项目描述</th>
                  </tr>
                </template>
                <template #body>
                  <tr class="bg-white transition hover:bg-gray-50">
                    <td>
                      <span class="text-[14px] font-semibold text-ink-900">
                        {{ selectedProject.name }}
                      </span>
                    </td>
                    <td class="text-[13px] text-ink-900">
                      {{ isDefaultProject(selectedProject) ? '系统保留' : '自定义项目' }}
                    </td>
                    <td>
                      <span class="font-mono text-[14px] text-ink-900">
                        {{ selectedProject.member_count ?? members.length }}
                      </span>
                    </td>
                    <td>
                      <span class="font-mono text-[13px] text-ink-700">
                        {{ formatDate(selectedProject.created_at) }}
                      </span>
                    </td>
                    <td>
                      <div class="whitespace-pre-wrap text-[13px] leading-relaxed text-ink-700">
                        {{ selectedProject.description || '无项目描述' }}
                      </div>
                    </td>
                  </tr>
                </template>
              </DataTable>
            </div>
          </div>
        </div>
      </AppCard>

      <!-- 03 项目成员 -->
      <AppCard
        v-loading="isLoadingMembers"
        as="article"
        padding="none"
        class="admin-dashboard-card"
      >
        <div class="admin-dashboard-card__inner">
          <div class="admin-dashboard-card__header">
            <SectionHeader
              variant="workbench"
              step="03"
              title="项目成员"
              :description="selectedProject ? `共 ${members.length} 位成员，可调整角色或归属项目` : '请先选择项目'"
              :status-label="getSectionStatusLabel(3)"
              :status-tone="getSectionStatusTone(3)"
            />
          </div>

          <div class="admin-dashboard-card__body">
            <!-- 未选择项目 -->
            <div
              v-if="!selectedProject"
              class="admin-empty-panel"
            >
              <EmptyState title="请选择项目" description="请在上方项目列表中选择一个项目，即可查看成员。" />
            </div>

            <!-- 已选项目但成员为空 -->
            <div
              v-else-if="!members.length"
              class="admin-empty-panel"
            >
              <EmptyState title="暂无项目成员" description="该项目尚未邀请任何成员加入。" />
            </div>

            <!-- 成员表（极浅完整网格线） -->
            <div v-else>
              <DataTable aria-label="项目成员">
                <template #head>
                  <tr>
                    <th class="w-1/5">用户名</th>
                    <th class="w-1/5">角色</th>
                    <th class="w-1/5">归属项目</th>
                    <th class="w-1/5">加入时间</th>
                    <th class="w-1/5">操作</th>
                  </tr>
                </template>
                <template #body>
                  <!-- 保留原有业务逻辑：成员表行级操作仍走原有链路 -->
                  <tr
                    v-for="row in members"
                    :key="row.user_id"
                    class="bg-white transition hover:bg-gray-50"
                  >
                    <td class="truncate font-medium text-ink-900">
                      {{ row.username }}
                    </td>
                    <td>
                      <StatusBadge
                        :type="row.is_super_admin ? 'danger' : row.role === 'admin' ? 'warning' : 'neutral'"
                        :label="getMemberRoleLabel(row)"
                      />
                    </td>
                    <td class="truncate text-ink-700">
                      {{ row.primary_project_name ?? '-' }}
                    </td>
                    <td class="font-mono text-[12px] text-ink-500">
                      {{ formatDate(row.joined_at) }}
                    </td>
                    <td>
                      <div class="table-actions">
                        <button
                          v-if="auth.isSuperAdmin && row.user_id !== auth.user?.id"
                          type="button"
                          class="ec-action-link"
                          @click="handleResetPassword(row)"
                        >
                          重置密码
                        </button>
                        <button
                          v-if="row.is_super_admin && canMoveMemberProject(row)"
                          type="button"
                          class="ec-action-link"
                          @click="openMoveProjectDialog(row)"
                        >
                          调整归属
                        </button>
                        <template v-if="!row.is_super_admin">
                          <button
                            v-if="row.role !== 'admin'"
                            type="button"
                            class="ec-action-link"
                            @click="handleSetRole(row, 'admin')"
                          >
                            设为管理员
                          </button>
                          <button
                            v-else
                            type="button"
                            class="ec-action-link"
                            @click="handleSetRole(row, 'user')"
                          >
                            设为普通用户
                          </button>
                          <button
                            v-if="canMoveMemberProject(row)"
                            type="button"
                            class="ec-action-link"
                            @click="openMoveProjectDialog(row)"
                          >
                            调整归属
                          </button>
                          <button
                            v-if="canRemoveMember(row)"
                            type="button"
                            class="ec-action-link-danger"
                            @click="handleRemoveMember(row)"
                          >
                            删除
                          </button>
                        </template>
                        <span
                          v-if="
                            row.is_super_admin &&
                            !(auth.isSuperAdmin && row.user_id !== auth.user?.id) &&
                            !canMoveMemberProject(row)
                          "
                          class="text-ink-500"
                        >
                          —
                        </span>
                      </div>
                    </td>
                  </tr>
                </template>
              </DataTable>
            </div>
          </div>
        </div>
      </AppCard>

      <!-- 04 飞书机器人 -->
      <FeishuBotConfigCard
        v-if="canManageFeishuBot && selectedProject"
        :project-id="selectedProject.id"
        :project-name="selectedProject.name"
      />

      <!-- 05 Source Evidence -->
      <SourceEvidenceAdminConfigCard
        v-if="canManageFeishuBot && selectedProject"
        :project-id="selectedProject.id"
        :project-name="selectedProject.name"
      />
    </div>

    <!-- 项目编辑弹窗 -->
    <el-dialog
      v-model="isProjectDialogVisible"
      :title="projectDialogTitle"
      width="520px"
      destroy-on-close
    >
      <div class="flex flex-col gap-4">
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">项目名称</label>
          <el-input
            v-model="projectForm.name"
            name="project-name"
            autocomplete="off"
            placeholder="请输入项目名称…"
            maxlength="128"
            show-word-limit
          />
        </div>
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">项目描述</label>
          <el-input
            v-model="projectForm.description"
            type="textarea"
            :rows="4"
            maxlength="500"
            show-word-limit
            name="project-description"
            autocomplete="off"
            placeholder="可选…"
          />
        </div>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <SecondaryButton
            @click="closeProjectDialog"
          >
            取消
          </SecondaryButton>
          <PrimaryButton
            :disabled="!canSubmitProject || isSavingProject"
            @click="handleSubmitProject"
          >
            {{ isSavingProject ? '保存中…' : projectDialogMode === 'create' ? '创建项目' : '保存修改' }}
          </PrimaryButton>
        </div>
      </template>
    </el-dialog>

    <!-- 调整归属项目弹窗 -->
    <el-dialog
      v-model="isMoveProjectDialogVisible"
      title="调整归属项目"
      width="480px"
      destroy-on-close
    >
      <div class="flex flex-col gap-4">
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">成员</label>
          <el-input :model-value="moveProjectForm.username" disabled />
        </div>
        <div>
          <label class="mb-1.5 block text-[12px] font-medium text-ink-500">目标归属项目</label>
          <el-select
            v-model="moveProjectForm.targetProjectId"
            name="target-project"
            autocomplete="off"
            placeholder="请选择目标项目…"
            class="w-full"
          >
            <el-option
              v-for="project in moveTargetProjects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </div>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <SecondaryButton
            @click="closeMoveProjectDialog"
          >
            取消
          </SecondaryButton>
          <PrimaryButton
            :disabled="!canSubmitMoveProject || isMovingMemberProject"
            @click="handleSubmitMoveProject"
          >
            {{ isMovingMemberProject ? '保存中…' : '保存' }}
          </PrimaryButton>
        </div>
      </template>
    </el-dialog>
  </div>
</template>
