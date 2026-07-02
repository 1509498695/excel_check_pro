<script setup lang="ts">
import { computed } from 'vue'

type ButtonSize = 'sm' | 'md'

const props = withDefaults(
  defineProps<{
    size?: ButtonSize
    disabled?: boolean
    loading?: boolean
    nativeType?: 'button' | 'submit' | 'reset'
  }>(),
  {
    size: 'md',
    disabled: false,
    loading: false,
    nativeType: 'button',
  },
)

const sizeClass = computed(() => `ui-button--${props.size}`)
</script>

<template>
  <button
    :type="nativeType"
    class="ui-button ui-button--primary"
    :class="sizeClass"
    :disabled="disabled || loading"
    :aria-busy="loading ? 'true' : undefined"
  >
    <span v-if="loading" class="ui-button__spinner" aria-hidden="true"></span>
    <span v-else-if="$slots.icon" class="ui-button__icon" aria-hidden="true">
      <slot name="icon" />
    </span>
    <span class="ui-button__label">
      <slot />
    </span>
  </button>
</template>
