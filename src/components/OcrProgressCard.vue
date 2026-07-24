<script setup lang="ts">
import { computed } from 'vue'
import type { OcrTask } from '../types/task'

const props = defineProps<{
  task: OcrTask
  elapsedMs: number
  requestFailed?: boolean
}>()

defineEmits<{ retry: [] }>()

const labels: Record<NonNullable<OcrTask['jobStatus']>, string> = {
  queued: '排队中',
  running: '任务启动中',
  recognizing: '正在识别',
  persisting: '正在保存结果',
  partial_success: '部分成功',
  succeeded: '识别完成',
  failed: '识别失败',
  cancelled: '任务已取消',
}
const status = computed(() => props.task.jobStatus || 'queued')
const failed = computed(() => status.value === 'failed' || status.value === 'cancelled')
const elapsed = computed(() => `${(props.elapsedMs / 1000).toFixed(1)} 秒`)
</script>

<template>
  <section class="ocr-progress-card" :class="{ 'is-failed': failed }">
    <div v-if="!failed" class="ocr-progress-spinner" aria-hidden="true" />
    <div class="ocr-progress-content">
      <p class="ocr-progress-kicker">OCR 任务</p>
      <h2>{{ labels[status] }}</h2>
      <a-progress :percent="task.progress || 0" :status="failed ? 'exception' : 'active'" />
      <div class="ocr-progress-meta">
        <span>状态：{{ task.stage || task.jobStatus }}</span>
        <span>进度：{{ task.progress || 0 }}%</span>
        <span>耗时：{{ elapsed }}</span>
      </div>
      <div v-if="failed" class="ocr-progress-error">
        <strong>{{ task.errorCode || 'OCR_JOB_FAILED' }}</strong>
        <p>{{ task.errorMessage || (task.jobStatus === 'cancelled' ? '任务已取消' : '识别任务执行失败，请重试。') }}</p>
        <a-button type="primary" @click="$emit('retry')">Retry</a-button>
      </div>
      <p v-else-if="requestFailed" class="ocr-progress-warning">状态查询暂时失败，正在自动重试…</p>
      <p v-else class="ocr-progress-tip">识别完成后将自动加载页面与结果。</p>
    </div>
  </section>
</template>
