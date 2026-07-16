<script setup lang="ts">
import { CheckCircleFilled, CloudUploadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import type { ModelOption } from '../mock'

defineProps<{
  models: ModelOption[]
  selectedModel: string
  currentModel: ModelOption
  jobState: 'ready' | 'running' | 'done'
  progress: number
}>()

const emit = defineEmits<{
  'update:selectedModel': [value: string]
  upload: []
  run: []
}>()
</script>

<template>
  <section class="control-strip">
    <div class="upload-block" @click="emit('upload')">
      <span class="upload-icon"><CloudUploadOutlined /></span>
      <div><b>QC_Report_0714.pdf</b><small>3 页 · 2.4 MB · PDF</small></div>
      <button class="replace-btn">替换文件</button>
    </div>
    <div class="control-divider"></div>
    <div class="model-control">
      <label>识别模型</label>
      <a-select
        :value="selectedModel"
        style="width: 260px"
        :options="models.map(model => ({ value: model.value, label: model.label }))"
        @update:value="emit('update:selectedModel', $event)"
      />
      <span class="model-note">{{ currentModel.note }} <i></i> {{ currentModel.speed }}</span>
    </div>
    <button class="run-btn" :class="{ running: jobState === 'running' }" @click="emit('run')">
      <span v-if="jobState === 'running'" class="spinner"></span>
      <CheckCircleFilled v-else-if="jobState === 'done'" />
      <SearchOutlined v-else />
      {{ jobState === 'running' ? `识别中 ${progress}%` : jobState === 'done' ? '重新识别' : '开始识别' }}
    </button>
  </section>
</template>
