<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { CommentOutlined, EditOutlined, FullscreenOutlined, MinusOutlined, PlusOutlined } from '@ant-design/icons-vue'
import type { OcrItem } from '../types/ocr'
import { getFinalOcrText, getLayoutCanvasHeight, mapBboxToRelative, OCR_DOCUMENT_HEIGHT, OCR_DOCUMENT_WIDTH } from '../ocrLayout'

const props = defineProps<{
  items: OcrItem[]
  selectedId: string
  showConfidence: boolean
  sourceWidth?: number
  sourceHeight?: number
}>()

const emit = defineEmits<{
  select: [id: string]
  correct: [item: OcrItem]
  comment: [item: OcrItem]
}>()

const viewport = ref<HTMLElement>()
const fitWidth = ref(320)
const zoom = ref(1)
let resizeObserver: ResizeObserver | undefined
const sourceWidth = computed(() => Math.max(1, props.sourceWidth || OCR_DOCUMENT_WIDTH))
const sourceHeight = computed(() => Math.max(1, props.sourceHeight || OCR_DOCUMENT_HEIGHT))
const canvasWidth = computed(() => fitWidth.value * zoom.value)
const canvasHeight = computed(() => getLayoutCanvasHeight(canvasWidth.value, sourceWidth.value, sourceHeight.value))

onMounted(() => {
  if (!viewport.value) return
  const updateWidth = () => {
    if (viewport.value) fitWidth.value = Math.max(1, viewport.value.clientWidth - 24)
  }
  updateWidth()
  resizeObserver = new ResizeObserver(updateWidth)
  resizeObserver.observe(viewport.value)
})

onBeforeUnmount(() => resizeObserver?.disconnect())

function itemStyle(item: OcrItem) {
  const box = mapBboxToRelative(item.bbox, sourceWidth.value, sourceHeight.value)
  const scale = canvasWidth.value / sourceWidth.value
  const bboxHeight = Math.abs(item.bbox[3] - item.bbox[1])
  return {
    left: `${box.left}%`,
    top: `${box.top}%`,
    width: `${box.width}%`,
    height: `${box.height}%`,
    fontSize: `${Math.min(14, Math.max(8, bboxHeight * scale * 0.46))}px`,
    borderLeftColor: scoreColor(item.score),
  }
}

function opensToLeft(item: OcrItem) {
  return mapBboxToRelative(item.bbox, sourceWidth.value, sourceHeight.value).left > 65
}

function changeZoom(delta: number) {
  zoom.value = Math.min(3, Math.max(.5, Number((zoom.value + delta).toFixed(2))))
}

function scoreColor(score: number) {
  if (score < 0.9) return '#ef5350'
  if (score < 0.95) return '#42a5f5'
  return '#66bb6a'
}
</script>

<template>
  <div class="layout-view-shell">
    <div class="layout-zoom-toolbar">
      <button :disabled="zoom <= .5" title="缩小" @click="changeZoom(-.2)"><MinusOutlined /></button>
      <span>{{ Math.round(zoom * 100) }}%</span>
      <button :disabled="zoom >= 3" title="放大" @click="changeZoom(.2)"><PlusOutlined /></button>
      <button title="适应窗口" @click="zoom = 1"><FullscreenOutlined /> 适应窗口</button>
    </div>
    <div ref="viewport" class="layout-view-scroll">
    <div
      class="ocr-layout-canvas"
      :style="{ width: `${canvasWidth}px`, height: `${canvasHeight}px`, aspectRatio: `${sourceWidth} / ${sourceHeight}` }"
    >
      <article
        v-for="item in items"
        :key="item.id"
        :data-result-id="item.id"
        class="ocr-layout-item"
        :class="{ selected: selectedId === item.id, corrected: item.corrected, 'popover-left': opensToLeft(item) }"
        :style="itemStyle(item)"
        :title="`${getFinalOcrText(item)} · ${(item.score * 100).toFixed(1)}%`"
        @click="emit('select', item.id)"
        @dblclick.stop="emit('correct', item)"
      >
        <span class="ocr-layout-text">{{ getFinalOcrText(item) }}</span>
        <div class="ocr-layout-popover">
          <b>{{ getFinalOcrText(item) }}</b>
          <small>{{ item.editSource === 'manual' ? '人工新增' : `${(item.score * 100).toFixed(1)}%` }} · 坐标 {{ item.bbox.join(', ') }}</small>
        </div>
        <span v-if="showConfidence && item.editSource !== 'manual'" class="ocr-layout-score">{{ Math.round(item.score * 100) }}%</span>
        <div class="ocr-layout-actions">
          <button title="纠正识别文字" @click.stop="emit('correct', item)"><EditOutlined /></button>
          <button title="查看或添加留言" @click.stop="emit('comment', item)"><CommentOutlined /><small v-if="item.comments.length">{{ item.comments.length }}</small></button>
        </div>
      </article>
      <a-empty v-if="!items.length" class="layout-empty" description="没有匹配的识别结果" />
    </div>
    </div>
  </div>
</template>
