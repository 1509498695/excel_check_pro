<script setup lang="ts">
withDefaults(
  defineProps<{
    breadcrumb?: string
    title: string
    description?: string
  }>(),
  {
    breadcrumb: '',
    description: '',
  },
)
</script>

<template>
  <header class="ui-page-header">
    <div class="ui-page-header__copy">
      <div v-if="breadcrumb" class="ui-page-header__breadcrumb">{{ breadcrumb }}</div>
      <h1 class="ui-page-header__title">
        {{ title }}
      </h1>
      <p v-if="description" class="ui-page-header__description">
        {{ description }}
      </p>
    </div>
    <div v-if="$slots.actions" class="ui-page-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.ui-page-header__description {
  max-width: 760px;
  margin: 9px 0 0;
  color: var(--color-text-secondary);
  font-size: 14px;
  font-weight: 500;
  line-height: 1.55;
}
</style>
