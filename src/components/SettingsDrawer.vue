<script setup lang="ts">
import { reactive, watch } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { models } from '../mock'
import { useAppSettings } from '../composables/useAppSettings'
import type { AppSettings } from '../types/settings'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [open: boolean] }>()
const { settings, updateSettings, resetSettings } = useAppSettings()
const draft = reactive<AppSettings>({ ...settings.value })

watch(() => props.open, (open) => { if (open) Object.assign(draft, settings.value) })

function save() {
  updateSettings({ ...draft })
  emit('update:open', false)
  message.success('设置已保存')
}

function reset() {
  Modal.confirm({
    title: '恢复默认设置？',
    content: '所有本地偏好将恢复为系统默认值。',
    okText: '恢复默认',
    cancelText: '取消',
    onOk: () => { resetSettings(); Object.assign(draft, settings.value); message.success('已恢复默认设置') },
  })
}
</script>

<template>
  <a-drawer :open="open" title="工作台设置" placement="right" :width="420" @update:open="emit('update:open', $event)">
    <div class="settings-intro"><b>本地偏好设置</b><p>设置保存在当前浏览器中，不会上传至服务器。</p></div>
    <a-form layout="vertical" class="settings-form">
      <a-form-item label="默认 OCR 模型"><a-select v-model:value="draft.defaultModelId" :options="models.map(model => ({ value: model.value, label: model.label }))" /></a-form-item>
      <a-form-item label="低置信度阈值"><a-input-number v-model:value="draft.lowConfidenceThreshold" :min="0.5" :max="1" :step="0.01" style="width: 100%" /><small>低于 {{ (draft.lowConfidenceThreshold * 100).toFixed(0) }}% 的结果将标记为待复核</small></a-form-item>
      <a-form-item label="默认结果展示模式"><a-radio-group v-model:value="draft.defaultResultViewMode" button-style="solid"><a-radio-button value="list">列表</a-radio-button><a-radio-button value="layout">原位布局</a-radio-button></a-radio-group></a-form-item>
      <a-form-item label="默认显示置信度"><a-switch v-model:checked="draft.showConfidence" /></a-form-item>
      <a-form-item label="默认 Excel 导出类型"><a-select v-model:value="draft.defaultExportMode" :options="[{ value: 'simple', label: '精简导出' }, { value: 'full', label: '完整导出' }]" /></a-form-item>
      <a-form-item label="默认页面缩放比例"><a-select v-model:value="draft.defaultZoom" :options="[{ value: .55, label: '55%' }, { value: .7, label: '70%' }, { value: .82, label: '82%（适应窗口）' }, { value: 1, label: '100%' }, { value: 1.15, label: '115%' }]" /></a-form-item>
    </a-form>
    <template #footer><div class="settings-footer"><button class="settings-reset" @click="reset">恢复默认设置</button><div><a-button @click="emit('update:open', false)">取消</a-button><a-button type="primary" @click="save">保存设置</a-button></div></div></template>
  </a-drawer>
</template>
