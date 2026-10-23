<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import type { OcrItem } from '../types/ocr'
import { boundedModalOffset, type DragOffset } from '../modalDrag'

const props = defineProps<{ open: boolean; item?: OcrItem; saving?: boolean }>()
const emit = defineEmits<{ 'update:open': [open: boolean]; save: [text: string] }>()
const correctionText = ref('')
const dragElement = ref<HTMLElement>()
const dragOffset = ref<DragOffset>({ x: 0, y: 0 })
let dragStart: { pointerX: number; pointerY: number; offset: DragOffset; bounds: DOMRect } | undefined

watch(() => [props.open, props.item] as const, ([open, item]) => {
  if (open && item) correctionText.value = item.corrected || item.rawText || item.text
  if (!open) {
    stopDrag()
    dragOffset.value = { x: 0, y: 0 }
  }
}, { immediate: true })

function startDrag(event: PointerEvent) {
  if (event.button !== 0 || !dragElement.value) return
  event.preventDefault()
  dragStart = {
    pointerX: event.clientX,
    pointerY: event.clientY,
    offset: { ...dragOffset.value },
    bounds: dragElement.value.getBoundingClientRect(),
  }
  window.addEventListener('pointermove', moveDrag)
  window.addEventListener('pointerup', stopDrag)
  window.addEventListener('pointercancel', stopDrag)
}

function moveDrag(event: PointerEvent) {
  if (!dragStart) return
  dragOffset.value = boundedModalOffset(dragStart.offset, dragStart.bounds, {
    width: window.innerWidth, height: window.innerHeight,
  }, {
    x: event.clientX - dragStart.pointerX,
    y: event.clientY - dragStart.pointerY,
  })
}

function stopDrag() {
  dragStart = undefined
  window.removeEventListener('pointermove', moveDrag)
  window.removeEventListener('pointerup', stopDrag)
  window.removeEventListener('pointercancel', stopDrag)
}

onBeforeUnmount(stopDrag)

function save() {
  if (correctionText.value.trim()) emit('save', correctionText.value.trim())
}
</script>

<template>
  <a-modal :open="open" :mask="false" ok-text="保存纠正" cancel-text="取消" :confirm-loading="saving" @update:open="emit('update:open', $event)" @ok="save">
    <template #title>
      <div class="correction-modal-drag-handle" @pointerdown="startDrag">
        <span>纠正识别文字</span><small>拖动标题可移动</small>
      </div>
    </template>
    <template #modalRender="{ originVNode }">
      <div ref="dragElement" :style="{ transform: `translate(${dragOffset.x}px, ${dragOffset.y}px)` }">
        <component :is="originVNode" />
      </div>
    </template>
    <div class="modal-label">原始识别</div>
    <div class="original-text">{{ item?.rawText || item?.text }}</div>
    <p v-if="item?.rawText && item.rawText !== item.text" class="modal-hint">待核对显示：{{ item.text }}</p>
    <div class="modal-label">纠正内容</div>
    <a-textarea v-model:value="correctionText" :rows="4" :maxlength="500" show-count autofocus />
    <p class="modal-hint">保存后会显示纠正内容，同时保留模型原始识别结果。</p>
  </a-modal>
</template>
