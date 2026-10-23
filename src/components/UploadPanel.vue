<script setup lang="ts">
import { CheckCircleFilled, CloudUploadOutlined, EyeOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { ref } from 'vue'
import type { IlluminationMode, ModelOption } from '../types/ocr'

defineProps<{
  models: ModelOption[]
  selectedModel: string
  currentModel?: ModelOption
  jobState: 'ready' | 'running' | 'done'
  progress: number
  fileName: string
  fileMeta: string
  hasFile: boolean
  regionCount: number
  illumination: IlluminationMode
}>()

const emit = defineEmits<{
  'update:selectedModel': [value: string]
  'update:illumination': [value: IlluminationMode]
  upload: [file: File]
  preview: []
  run: []
}>()

const fileInput = ref<HTMLInputElement>()

function chooseFile() {
  fileInput.value?.click()
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('upload', file)
  input.value = ''
}
</script>

<template>
  <section class="control-strip">
    <div class="upload-block" @click="chooseFile">
      <input ref="fileInput" type="file" accept=".pdf,.png,.jpg,.jpeg" hidden @click.stop @change="handleFileChange" />
      <span class="upload-icon"><CloudUploadOutlined /></span>
      <div><b>{{ fileName }}</b><small>{{ fileMeta }}</small></div>
      <div class="upload-file-actions">
        <button v-if="hasFile" class="preview-file-btn" @click.stop="emit('preview')"><EyeOutlined />预览文件</button>
        <button class="replace-btn">替换文件</button>
      </div>
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
    </div>
    <div class="model-control">
      <label>光照处理</label>
      <a-select
        :value="illumination"
        style="width: 150px"
        :options="[
          { value: 'none', label: '原图' },
          { value: 'he', label: '全局 HE' },
          { value: 'clahe', label: 'CLAHE' },
        ]"
        @update:value="emit('update:illumination', $event as IlluminationMode)"
      />
    </div>
    <button class="run-btn" :class="{ running: jobState === 'running' }" :disabled="!currentModel" @click="emit('run')">
      <span v-if="jobState === 'running'" class="spinner"></span>
      <CheckCircleFilled v-else-if="jobState === 'done'" />
      <SearchOutlined v-else />
      {{ jobState === 'running' ? `识别中 ${progress}%` : jobState === 'done' && !hasFile ? '重新识别' : regionCount ? `开始识别 · ${regionCount} 个区域` : '开始识别' }}
    </button>
  </section>
</template>
