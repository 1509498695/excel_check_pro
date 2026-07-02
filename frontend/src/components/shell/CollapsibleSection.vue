<script setup lang="ts">
import SectionHeader from './SectionHeader.vue'
import AppCard from './AppCard.vue'

type SectionHeaderTone = 'pending' | 'active' | 'done' | 'warn' | 'error'

withDefaults(
  defineProps<{
    step: string
    title: string
    description?: string
    statusLabel?: string
    statusTone?: SectionHeaderTone
    active?: boolean
    collapsed?: boolean
    headerClass?: string
    contentClass?: string
  }>(),
  {
    description: '',
    statusLabel: '',
    statusTone: 'done',
    active: false,
    collapsed: false,
    headerClass: 'border-b border-line pb-3',
    contentClass: 'pt-1',
  },
)

const emit = defineEmits<{
  (event: 'toggle'): void
}>()
</script>

<template>
  <AppCard
    as="section"
    padding="none"
    class="ui-collapsible-section"
    :class="{ 'is-active': active }"
  >
    <div class="ui-collapsible-section__inner">
      <div :class="collapsed ? '' : headerClass">
        <SectionHeader
          variant="workbench"
          :step="step"
          :title="title"
          :description="description"
          :status-label="statusLabel"
          :status-tone="statusTone"
        >
          <template #actions>
            <div class="workbench-section-toolbar__actions shrink-0">
              <slot name="actions" />
              <button
                type="button"
                class="ec-btn-text-collapse"
                :aria-expanded="!collapsed"
                @click="emit('toggle')"
              >
                {{ collapsed ? '展开' : '收起' }}
                <svg
                  class="ec-btn-icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  aria-hidden="true"
                >
                  <path v-if="collapsed" d="m6 9 6 6 6-6" />
                  <path v-else d="m18 15-6-6-6 6" />
                </svg>
              </button>
            </div>
          </template>
        </SectionHeader>
      </div>

      <div v-show="!collapsed" :class="contentClass">
        <slot />
      </div>
    </div>
  </AppCard>
</template>
