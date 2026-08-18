<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import type { OcrPage, OcrPolygon } from '../types/ocr'
import { bboxToCanvasRect, bboxToPolygon, canvasPointToSource, canvasRectToBbox, isValidPolygon, polygonToCanvasPoints, resultBoxColor, SELECTED_BOX_COLOR, translatePolygonWithinBounds, type CanvasRect, type ImageTransform } from '../bboxEditing'

const props = defineProps<{ page: OcrPage; selectedId: string; zoom: number; editMode?: boolean }>()
const emit = defineEmits<{
  select: [id: string]
  polygonPreview: [id: string, polygon: OcrPolygon]
  create: [bbox: OcrPage['items'][number]['bbox']]
}>()
const stageConfig = computed(() => ({ width: 700 * props.zoom, height: 760 * props.zoom, scaleX: props.zoom, scaleY: props.zoom }))
const sourceImage = shallowRef<HTMLImageElement>()
let imageLoadToken = 0
const drawingRect = ref<CanvasRect>()
let drawingStart: { x: number; y: number } | undefined
let polygonDrag: { id: string; start: { x: number; y: number }; polygon: OcrPolygon } | undefined

const imageTransform = computed(() => {
  const sourceWidth = Math.max(1, props.page.sourceWidth || sourceImage.value?.naturalWidth || 700)
  const sourceHeight = Math.max(1, props.page.sourceHeight || sourceImage.value?.naturalHeight || 760)
  const scale = Math.min(700 / sourceWidth, 760 / sourceHeight)
  const width = sourceWidth * scale
  const height = sourceHeight * scale
  return { scale, x: (700 - width) / 2, y: (760 - height) / 2, width, height }
})
const editableTransform = computed<ImageTransform>(() => ({
  ...imageTransform.value,
  sourceWidth: Math.max(1, props.page.sourceWidth || sourceImage.value?.naturalWidth || 700),
  sourceHeight: Math.max(1, props.page.sourceHeight || sourceImage.value?.naturalHeight || 760),
}))

watch(() => props.page.imageUrl, (url) => {
  const token = ++imageLoadToken
  sourceImage.value = undefined
  if (!url) return
  const image = new Image()
  image.onload = () => { if (token === imageLoadToken) sourceImage.value = image }
  image.src = url
}, { immediate: true })
onBeforeUnmount(() => { imageLoadToken += 1 })

function itemPolygon(item: OcrPage['items'][number]): OcrPolygon {
  return item.polygon || bboxToPolygon(item.bbox)
}
function canvasPolygon(item: OcrPage['items'][number]) {
  return polygonToCanvasPoints(itemPolygon(item), editableTransform.value)
}
function rectConfig(item: OcrPage['items'][number]) {
  return bboxToCanvasRect(item.bbox, editableTransform.value)
}
function dragCorner(item: OcrPage['items'][number], index: number, event: any) {
  event.cancelBubble = true
  const pointer = pointerInCanvas(event)
  if (!pointer) return
  const polygon = itemPolygon(item).map(point => [...point]) as OcrPolygon
  polygon[index] = canvasPointToSource(pointer, editableTransform.value)
  if (!isValidPolygon(polygon)) {
    const previous = canvasPolygon(item)
    event.target.position({ x: previous[index * 2], y: previous[index * 2 + 1] })
    return
  }
  emit('polygonPreview', item.id, polygon)
}

function beginPolygonDrag(item: OcrPage['items'][number], event: any) {
  const pointer = pointerInCanvas(event)
  if (!pointer) return
  polygonDrag = {
    id: item.id,
    start: pointer,
    polygon: itemPolygon(item).map(point => [...point]) as OcrPolygon,
  }
}

function updatePolygonDrag(item: OcrPage['items'][number], event: any) {
  if (!polygonDrag || polygonDrag.id !== item.id) return
  const pointer = pointerInCanvas(event)
  if (!pointer) return
  event.target.position({ x: 0, y: 0 })
  const transform = editableTransform.value
  const requestedX = (pointer.x - polygonDrag.start.x) / transform.scale
  const requestedY = (pointer.y - polygonDrag.start.y) / transform.scale
  emit('polygonPreview', item.id, translatePolygonWithinBounds(
    polygonDrag.polygon, requestedX, requestedY, transform.sourceWidth, transform.sourceHeight,
  ))
}

function finishPolygonDrag(event: any) {
  event.target.position({ x: 0, y: 0 })
  polygonDrag = undefined
}
function pointerInCanvas(event: any) {
  const pointer = event.target.getStage()?.getPointerPosition()
  return pointer ? { x: pointer.x / props.zoom, y: pointer.y / props.zoom } : undefined
}
function beginDrawing(event: any) {
  const targetName = event.target.name?.() || ''
  if (!props.editMode || (event.target !== event.target.getStage() && !['canvas-background', 'source-image'].includes(targetName))) return
  const point = pointerInCanvas(event)
  if (!point) return
  const transform = imageTransform.value
  drawingStart = {
    x: Math.min(transform.x + transform.width, Math.max(transform.x, point.x)),
    y: Math.min(transform.y + transform.height, Math.max(transform.y, point.y)),
  }
  drawingRect.value = { ...drawingStart, width: 0, height: 0 }
}
function updateDrawing(event: any) {
  if (!drawingStart) return
  const point = pointerInCanvas(event)
  if (!point) return
  const transform = imageTransform.value
  const x = Math.min(transform.x + transform.width, Math.max(transform.x, point.x))
  const y = Math.min(transform.y + transform.height, Math.max(transform.y, point.y))
  drawingRect.value = { x: Math.min(drawingStart.x, x), y: Math.min(drawingStart.y, y), width: Math.abs(x - drawingStart.x), height: Math.abs(y - drawingStart.y) }
}
function finishDrawing() {
  if (!drawingStart || !drawingRect.value) return
  const rect = drawingRect.value
  drawingStart = undefined
  drawingRect.value = undefined
  if (rect.width < 3 || rect.height < 3) return
  emit('create', canvasRectToBbox(rect, editableTransform.value))
}
</script>

<template>
  <v-stage :config="stageConfig" @mousedown="beginDrawing" @mousemove="updateDrawing" @mouseup="finishDrawing">
    <v-layer>
      <v-rect :config="{ name: 'canvas-background', x: 0, y: 0, width: 700, height: 760, fill: '#fbfaf6', shadowColor: '#0b1512', shadowBlur: 25, shadowOpacity: .2, shadowOffsetY: 8 }" />
      <v-image v-if="sourceImage" :config="{ name: 'source-image', image: sourceImage, x: imageTransform.x, y: imageTransform.y, width: imageTransform.width, height: imageTransform.height }" />
      <template v-if="!page.imageUrl">
        <v-rect :config="{ x: 50, y: 38, width: 8, height: 78, fill: '#168b6c' }" />
        <v-text :config="{ x: 74, y: 40, text: page.no === 1 ? 'JUXI PRECISION' : page.no === 2 ? 'JUXI MACHINERY' : 'JUXI LOGISTICS', fontSize: 13, fontStyle: 'bold', fill: '#168b6c', letterSpacing: 2 }" />
        <v-line :config="{ points: [50, 170, 650, 170], stroke: '#d9d7cf', strokeWidth: 1 }" />
        <v-line v-for="y in [274, 336, 402, 468]" :key="y" :config="{ points: [64, y, 640, y], stroke: '#e4e2da', strokeWidth: 1 }" />
        <v-line v-for="x in [218, 398, 554]" :key="x" :config="{ points: [x, 274, x, 468], stroke: '#e4e2da', strokeWidth: 1 }" />
        <v-text v-for="item in page.items" :key="`text-${item.id}`" :config="{ x: item.bbox[0] + 2, y: item.bbox[1] + 5, text: item.corrected || item.text, fontSize: Math.min(25, Math.max(13, item.bbox[3] - item.bbox[1] - 9)), fontStyle: item.id === page.items[0].id ? 'bold' : 'normal', fill: '#252c29', width: item.bbox[2] - item.bbox[0], ellipsis: true }" />
      </template>
    </v-layer>
    <v-layer>
      <template v-for="item in page.items" :key="item.id">
        <template v-if="!(editMode && selectedId === item.id)">
          <v-line v-if="item.polygon" :config="{ points: canvasPolygon(item), closed: true, stroke: resultBoxColor(selectedId === item.id), strokeWidth: selectedId === item.id ? 3 : 1.5, fill: selectedId === item.id ? 'rgba(255,77,79,.10)' : 'rgba(182,191,188,.025)', hitStrokeWidth: 12 }" @click="emit('select', item.id)" @tap="emit('select', item.id)" />
          <v-rect v-else :config="{ ...rectConfig(item), stroke: resultBoxColor(selectedId === item.id), strokeWidth: selectedId === item.id ? 3 : 1.5, fill: selectedId === item.id ? 'rgba(255,77,79,.10)' : 'rgba(182,191,188,.025)', cornerRadius: 2, hitStrokeWidth: 12 }" @click="emit('select', item.id)" @tap="emit('select', item.id)" />
        </template>
        <template v-else>
          <v-line
            :config="{ points: canvasPolygon(item), closed: true, stroke: SELECTED_BOX_COLOR, strokeWidth: 3, fill: 'rgba(255,77,79,.10)', hitStrokeWidth: 12, draggable: true }"
            @dragstart="beginPolygonDrag(item, $event)" @dragmove="updatePolygonDrag(item, $event)" @dragend="finishPolygonDrag($event)"
          />
          <v-circle v-for="(_, index) in itemPolygon(item)" :key="`${item.id}-corner-${index}`" :config="{ x: canvasPolygon(item)[index * 2], y: canvasPolygon(item)[index * 2 + 1], radius: 6, fill: '#fff', stroke: SELECTED_BOX_COLOR, strokeWidth: 2, draggable: true }" @mousedown="$event.cancelBubble = true" @touchstart="$event.cancelBubble = true" @dragmove="dragCorner(item, index, $event)" />
        </template>
      </template>
      <v-rect v-if="drawingRect" :config="{ ...drawingRect, stroke: '#1677ff', strokeWidth: 1.5, dash: [6, 4], fill: 'rgba(22,119,255,.08)' }" />
    </v-layer>
  </v-stage>
</template>
