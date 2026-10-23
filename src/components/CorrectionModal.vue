<script setup lang="ts">
import { sourcePreviewStyle } from '../sourceCorrection'
import { onBeforeUnmount, ref, watch } from 'vue'
import type { OcrItem } from '../types/ocr'
import { boundedModalOffset, type DragOffset } from '../modalDrag'

const props = defineProps<{ open: boolean; item?: OcrItem; saving?: boolean; sourceMode?: boolean; independent?: boolean; imageUrl?: string; sourceWidth?: number; sourceHeight?: number }>()
const emit = defineEmits<{ 'update:open': [open: boolean]; save: [text: string] }>()
const correctionText = ref('')
const dragElement = ref<HTMLElement>()
const dragOffset = ref<DragOffset>({ x: 0, y: 0 })
let dragStart: { pointerX: number; pointerY: number; offset: DragOffset; bounds: DOMRect } | undefined

watch(() => [props.open, props.item] as const, ([open, item]) => {
  if (open && item) correctionText.value = item.corrected ?? item.rawText ?? item.text
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
        <span>{{ sourceMode ? '纠正来源文字' : '纠正识别文字' }}</span><small>拖动标题可移动</small>
      </div>
    </template>
    <template #modalRender="{ originVNode }">
      <div ref="dragElement" :style="{ transform: `translate(${dragOffset.x}px, ${dragOffset.y}px)` }">
        <component :is="originVNode" />
      </div>
    </template>
    <template v-if="sourceMode">
      <p class="modal-hint">修改当前识别框的文字，图片框位置与端子关联保持不变。</p>
      <div v-if="item && imageUrl && sourceWidth && sourceHeight" class="source-crop-wrap">
        <div role="img" aria-label="来源识别框局部图片" :style="{ ...sourcePreviewStyle(item, sourceWidth, sourceHeight), backgroundImage: `url(${JSON.stringify(imageUrl)})`, backgroundRepeat: 'no-repeat' }"></div>
      </div>
      <p v-else class="modal-hint">暂无可用的来源图片，请对照工作台高亮框核对。</p>
      <div class="modal-label">当前纠正文字</div>
      <div class="original-text">{{ item?.corrected ?? item?.text }}</div>
      <p v-if="!independent" class="modal-hint">当前版本表格与列表仍共用识别文字；保存会同步影响关联表格行。</p>
      <slot :text="correctionText" />
    </template>
    <div class="modal-label">原始识别</div>
    <div class="original-text">{{ item?.rawText || item?.text }}</div>
    <p v-if="item?.rawText && item.rawText !== item.text" class="modal-hint">待核对显示：{{ item.text }}</p>
    <div class="modal-label">纠正内容</div>
    <a-textarea v-model:value="correctionText" :rows="4" :maxlength="500" show-count autofocus />
    <p class="modal-hint">保存后会显示纠正内容，同时保留模型原始识别结果。</p>
  </a-modal>
</template>

<style scoped>
.source-crop-wrap { overflow: auto; max-height: 180px; padding: 8px; border: 1px solid #dce5df; background: #f6f9f7; margin-bottom: 12px; }
</style>
