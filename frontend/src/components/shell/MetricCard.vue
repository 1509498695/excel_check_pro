<script setup lang="ts">
import StatusBadge from './StatusBadge.vue'
import type { StatusBadgeType } from './types'

withDefaults(
  defineProps<{
    label: string
    value: number | string
    statusLabel: string
    statusType?: StatusBadgeType
    iconTone?: 'primary' | 'success' | 'warning' | 'danger' | 'purple'
  }>(),
  {
    statusType: 'neutral',
    iconTone: 'primary',
  },
)
</script>

<template>
  <article class="ui-metric-card">
    <div class="ui-metric-card__icon" :class="`ui-metric-card__icon--${iconTone}`" aria-hidden="true">
      <slot name="icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M4 7h16M4 12h16M4 17h10" />
        </svg>
      </slot>
    </div>
    <div class="ui-metric-card__body">
      <div class="ui-metric-card__label">{{ label }}</div>
      <div class="ui-metric-card__value">{{ value }}</div>
      <StatusBadge :type="statusType" :label="statusLabel" />
    </div>
  </article>
</template>
