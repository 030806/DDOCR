<script setup lang="ts">
import type { IlluminationMode } from '../types/ocr'

defineProps<{ modelValue: IlluminationMode; disabled?: boolean; compact?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: IlluminationMode] }>()
</script>

<template>
  <label class="illumination-control" :class="{ compact }">
    <span>光照处理</span>
    <select :value="modelValue" :disabled="disabled" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value as IlluminationMode)">
      <option value="none">原图</option>
      <option value="he">全局 HE</option>
      <option value="clahe">CLAHE</option>
    </select>
  </label>
</template>

<style scoped>
.illumination-control { display: flex; flex-direction: column; gap: 8px; color: #64776a; font-size: 12px; }
.illumination-control select { width: 100%; min-width: 0; padding: 9px 12px; border: 1px solid #dce5de; border-radius: 7px; background: #fff; color: #334d3e; font: inherit; cursor: pointer; }
.illumination-control select:focus-visible { outline: 2px solid #168b6c; outline-offset: 2px; }
.illumination-control select:disabled { background: #f6f8f6; color: #8b9a8f; cursor: default; }
.illumination-control.compact { flex: 0 0 auto; flex-direction: row; align-items: center; gap: 12px; }
.compact span { white-space: nowrap; font-weight: 600; }
.compact select { width: 120px; }
</style>
