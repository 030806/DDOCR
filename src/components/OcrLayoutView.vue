<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { CommentOutlined, EditOutlined } from '@ant-design/icons-vue'
import type { OcrItem } from '../mock'
import { getFinalOcrText, getLayoutCanvasHeight, mapBboxToRelative, OCR_DOCUMENT_HEIGHT, OCR_DOCUMENT_WIDTH } from '../ocrLayout'

defineProps<{
  items: OcrItem[]
  selectedId: string
  showConfidence: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  correct: [item: OcrItem]
  comment: [item: OcrItem]
}>()

const viewport = ref<HTMLElement>()
const canvasWidth = ref(320)
let resizeObserver: ResizeObserver | undefined
const canvasHeight = computed(() => getLayoutCanvasHeight(canvasWidth.value))

onMounted(() => {
  if (!viewport.value) return
  const updateWidth = () => {
    if (viewport.value) canvasWidth.value = Math.max(1, viewport.value.clientWidth - 24)
  }
  updateWidth()
  resizeObserver = new ResizeObserver(updateWidth)
  resizeObserver.observe(viewport.value)
})

onBeforeUnmount(() => resizeObserver?.disconnect())

function itemStyle(item: OcrItem) {
  const box = mapBboxToRelative(item.bbox)
  const scale = canvasWidth.value / OCR_DOCUMENT_WIDTH
  const sourceHeight = Math.abs(item.bbox[3] - item.bbox[1])
  return {
    left: `${box.left}%`,
    top: `${box.top}%`,
    width: `${box.width}%`,
    height: `${box.height}%`,
    fontSize: `${Math.min(14, Math.max(8, sourceHeight * scale * 0.46))}px`,
    borderLeftColor: scoreColor(item.score),
  }
}

function scoreColor(score: number) {
  if (score < 0.9) return '#ef5350'
  if (score < 0.95) return '#42a5f5'
  return '#66bb6a'
}
</script>

<template>
  <div ref="viewport" class="layout-view-scroll">
    <div
      class="ocr-layout-canvas"
      :style="{ width: `${canvasWidth}px`, height: `${canvasHeight}px`, aspectRatio: `${OCR_DOCUMENT_WIDTH} / ${OCR_DOCUMENT_HEIGHT}` }"
    >
      <article
        v-for="item in items"
        :key="item.id"
        :data-result-id="item.id"
        class="ocr-layout-item"
        :class="{ selected: selectedId === item.id, corrected: item.corrected }"
        :style="itemStyle(item)"
        :title="`${getFinalOcrText(item)} · ${(item.score * 100).toFixed(1)}%`"
        @click="emit('select', item.id)"
        @dblclick.stop="emit('correct', item)"
      >
        <span class="ocr-layout-text">{{ getFinalOcrText(item) }}</span>
        <span v-if="showConfidence" class="ocr-layout-score">{{ Math.round(item.score * 100) }}%</span>
        <div class="ocr-layout-actions">
          <button title="纠正识别文字" @click.stop="emit('correct', item)"><EditOutlined /></button>
          <button title="查看或添加留言" @click.stop="emit('comment', item)"><CommentOutlined /><small v-if="item.comments.length">{{ item.comments.length }}</small></button>
        </div>
      </article>
      <a-empty v-if="!items.length" class="layout-empty" description="没有匹配的识别结果" />
    </div>
  </div>
</template>
