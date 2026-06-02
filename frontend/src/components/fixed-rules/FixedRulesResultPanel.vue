<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheckFilled } from '@element-plus/icons-vue'

import { useFixedRulesStore } from '../../store/fixedRules'

const store = useFixedRulesStore()

const resultStats = computed(() => {
  const total = store.abnormalResults.length
  const errors = store.abnormalResults.filter((item) => item.level === 'error').length
  const warnings = store.abnormalResults.filter((item) => item.level === 'warning').length
  const scanned = store.executionMeta?.total_rows_scanned ?? 0
  const failedSources = store.executionMeta?.failed_sources.length ?? 0
  const passRate = scanned > 0 ? Math.max(0, Math.round(((scanned - total) / scanned) * 100)) : 100

  return {
    total,
    errors,
    warnings,
    scanned,
    failedSources,
    passRate,
  }
})

const resultSummary = computed(() => {
  if (!store.executionMeta) {
    return '保存配置后点击“执行全部规则”，结果会在这里展示。'
  }

  return `本轮共执行 ${store.totalRuleCount} 条项目校验规则，已扫描 ${resultStats.value.scanned} 行数据。`
})

const resultState = computed(() => {
  if (store.isExecuting) {
    return {
      type: 'info' as const,
      title: '正在执行项目校验',
      description: '系统正在读取固定文件、执行全部规则组并刷新结果看板，请稍候。',
    }
  }

  if (store.pageError) {
    return {
      type: 'error' as const,
      title: '本轮执行未完成',
      description: store.pageError,
    }
  }

  if (!store.totalRuleCount) {
    return {
      type: 'info' as const,
      title: '还没有可执行的项目校验规则',
      description: '先完成文件配置、规则组和规则录入，再在这里查看执行结果。',
    }
  }

  if (!store.executionMeta) {
    return {
      type: 'info' as const,
      title: '结果看板已就绪，等待执行',
      description: '点击“执行全部规则”后，这里会展示扫描统计、失败数据源和异常明细。',
    }
  }

  if (!store.abnormalResults.length) {
    return {
      type: 'success' as const,
      title: '本轮项目校验已完成，未发现异常',
      description: `已扫描 ${resultStats.value.scanned} 行数据，可继续补充规则组或调整阈值。`,
    }
  }

  return {
    type: 'warning' as const,
    title: '本轮项目校验已完成，已返回异常明细',
    description: `已扫描 ${resultStats.value.scanned} 行数据，共返回 ${resultStats.value.total} 条异常结果。`,
  }
})

const packageItemsParseSummaries = computed(() =>
  (store.executionMeta?.package_items_parse ?? []).map((item, index) => ({
    key: item.rule_id || `package-items-${index}`,
    ruleId: item.rule_id || '未记录规则 ID',
    parseMode: item.parse_mode === 'ai' ? 'AI 辅助解析' : '规则解析',
    confidence:
      typeof item.confidence === 'number'
        ? `置信度 ${item.confidence}`
        : '置信度 未记录',
    aiUsed: item.ai_used ? '是' : '否',
    detailRowCount: item.detail_row_count ?? 0,
    packageIds: item.package_ids ?? [],
    warnings: item.warnings ?? [],
    errors: item.errors ?? [],
  })),
)

function getLevelType(level: string): 'danger' | 'warning' | 'success' | 'info' {
  if (level === 'error') {
    return 'danger'
  }
  if (level === 'warning') {
    return 'warning'
  }
  if (level === 'success') {
    return 'success'
  }
  return 'info'
}

function displayRawValue(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '空值'
  }

  if (typeof value === 'object') {
    return JSON.stringify(value)
  }

  return String(value)
}
</script>

<template>
  <div class="result-layout">
    <el-alert
      :title="resultState.title"
      :description="resultState.description"
      :type="resultState.type"
      :closable="false"
      show-icon
    />

    <div class="result-kpi-bar">
      <div class="result-kpi-main">
        <div class="result-kpi-icon">
          <CircleCheckFilled />
        </div>
        <div>
          <strong>项目校验结果总览</strong>
          <p>{{ resultSummary }}</p>
        </div>
      </div>

      <div class="result-kpi-progress">
        <div class="progress-caption">
          <span>通过率</span>
          <strong>{{ resultStats.passRate }}%</strong>
        </div>
        <el-progress :percentage="resultStats.passRate" :show-text="false" :stroke-width="8" color="#22c55e" />
      </div>

      <div class="toolbar-actions">
        <el-button class="result-export-button" plain :disabled="!store.executionMeta">导出 Excel 报告</el-button>
      </div>
    </div>

    <div class="result-summary">
      <div class="summary-tile">
        <span>扫描总行数</span>
        <strong>{{ resultStats.scanned }}</strong>
      </div>
      <div class="summary-tile">
        <span>异常总数</span>
        <strong>{{ resultStats.total }}</strong>
      </div>
      <div class="summary-tile">
        <span>错误 / 警告</span>
        <strong>{{ resultStats.errors }} / {{ resultStats.warnings }}</strong>
      </div>
      <div class="summary-tile">
        <span>失败数据源</span>
        <strong>{{ resultStats.failedSources }}</strong>
      </div>
    </div>

    <el-alert
      v-if="store.pageError"
      :title="store.pageError"
      type="error"
      :closable="false"
      show-icon
      class="result-alert"
    />

    <el-alert
      v-if="store.executionMeta?.failed_sources.length"
      type="warning"
      :closable="false"
      show-icon
      class="result-alert"
    >
      <template #title>
        这些数据源本次加载失败，但其他规则已继续执行：
        {{ store.executionMeta.failed_sources.join('、') }}
      </template>
    </el-alert>

    <section v-if="packageItemsParseSummaries.length" class="package-parse-summary">
      <div class="panel-toolbar result-toolbar">
        <div class="toolbar-copy">
          <strong>礼包规划解析概览</strong>
          <span>展示本轮礼包校验执行前的飞书规划表解析结果。</span>
        </div>
      </div>
      <div class="package-parse-summary__list">
        <article
          v-for="summary in packageItemsParseSummaries"
          :key="summary.key"
          class="package-parse-summary__item"
        >
          <strong>{{ summary.ruleId }}</strong>
          <p>
            {{ summary.parseMode }} · {{ summary.confidence }} · AI 参与 {{ summary.aiUsed }} ·
            明细 {{ summary.detailRowCount }} 行
          </p>
          <p v-if="summary.packageIds.length">礼包 {{ summary.packageIds.join('、') }}</p>
          <p v-if="summary.warnings.length" class="package-parse-summary__warning">
            {{ summary.warnings.join('；') }}
          </p>
          <p v-if="summary.errors.length" class="package-parse-summary__error">
            {{ summary.errors.join('；') }}
          </p>
        </article>
      </div>
    </section>

    <div class="panel-toolbar result-toolbar">
      <div class="toolbar-copy">
        <strong>异常结果明细</strong>
        <span>结果字段和后端返回结构保持一致，可直接用于联调定位。</span>
      </div>
    </div>

    <el-table
      :data="store.abnormalResults"
      class="workbench-table"
      empty-text="执行完成后，异常结果会在这里展示。"
    >
      <el-table-column label="级别" width="110">
        <template #default="{ row }">
          <el-tag :type="getLevelType(row.level)" effect="light" round>
            {{ row.level }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="rule_name" label="规则名称" min-width="220" />
      <el-table-column prop="location" label="字段定位" min-width="220" />
      <el-table-column prop="row_index" label="行号" width="90" />
      <el-table-column label="触发值" min-width="150">
        <template #default="{ row }">
          <span class="mono-inline">{{ displayRawValue(row.raw_value) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="message" label="说明" min-width="240" />
    </el-table>
  </div>
</template>
