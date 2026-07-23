<script setup lang="ts">
import { ref, watch } from 'vue'
import type { OcrItem } from '../types/ocr'

const props = defineProps<{ open: boolean; item?: OcrItem; saving?: boolean }>()
const emit = defineEmits<{ 'update:open': [open: boolean]; save: [text: string] }>()
const correctionText = ref('')

watch(() => [props.open, props.item] as const, ([open, item]) => {
  if (open && item) correctionText.value = item.corrected || item.text
}, { immediate: true })

function save() {
  if (correctionText.value.trim()) emit('save', correctionText.value.trim())
}
</script>

<template>
  <a-modal :open="open" title="纠正识别文字" ok-text="保存纠正" cancel-text="取消" :confirm-loading="saving" @update:open="emit('update:open', $event)" @ok="save">
    <div class="modal-label">原始识别</div>
    <div class="original-text">{{ item?.text }}</div>
    <div class="modal-label">纠正内容</div>
    <a-textarea v-model:value="correctionText" :rows="4" :maxlength="500" show-count autofocus />
    <p class="modal-hint">保存后会显示纠正内容，同时保留模型原始识别结果。</p>
  </a-modal>
</template>
