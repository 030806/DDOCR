<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { RegionDraft } from '../api/ocr'

const props = defineProps<{
  open: boolean
  file?: File
  imageUrl?: string
  sourceWidth?: number
  sourceHeight?: number
  initialName: string
  submitting?: boolean
}>()
const emit = defineEmits<{
  close: []
  confirm: [name: string, regions: RegionDraft[]]
}>()

const localUrl = ref('')
const image = ref<HTMLImageElement>()
const name = ref('')
const regions = ref<RegionDraft[]>([])
const draft = ref<{ x1: number; y1: number; x2: number; y2: number }>()
const naturalWidth = ref(1)
const naturalHeight = ref(1)

const activeUrl = computed(() => props.imageUrl || localUrl.value)
const width = computed(() => props.sourceWidth || naturalWidth.value)
const height = computed(() => props.sourceHeight || naturalHeight.value)

function releaseLocalUrl() {
  if (localUrl.value) URL.revokeObjectURL(localUrl.value)
  localUrl.value = ''
}

watch(() => [props.open, props.file, props.imageUrl] as const, ([open, file]) => {
  releaseLocalUrl()
  if (!open) return
  name.value = props.initialName
  regions.value = []
  draft.value = undefined
  if (file) localUrl.value = URL.createObjectURL(file)
}, { immediate: true })
onBeforeUnmount(releaseLocalUrl)

function point(event: PointerEvent) {
  const rect = image.value?.getBoundingClientRect()
  if (!rect) return
  const x = Math.min(rect.width, Math.max(0, event.clientX - rect.left))
  const y = Math.min(rect.height, Math.max(0, event.clientY - rect.top))
  return { x: x / rect.width * width.value, y: y / rect.height * height.value }
}

function begin(event: PointerEvent) {
  if (regions.value.length >= 20) { message.warning('单页最多框选 20 个区域'); return }
  const current = point(event)
  if (!current) return
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  draft.value = { x1: current.x, y1: current.y, x2: current.x, y2: current.y }
}

function move(event: PointerEvent) {
  if (!draft.value) return
  const current = point(event)
  if (!current) return
  draft.value.x2 = current.x
  draft.value.y2 = current.y
}

function finish() {
  if (!draft.value) return
  const box = draft.value
  draft.value = undefined
  const bbox: RegionDraft['bbox'] = [
    Math.round(Math.min(box.x1, box.x2)), Math.round(Math.min(box.y1, box.y2)),
    Math.round(Math.max(box.x1, box.x2)), Math.round(Math.max(box.y1, box.y2)),
  ]
  if (bbox[2] - bbox[0] < 16 || bbox[3] - bbox[1] < 16) {
    message.warning('识别区域不能小于 16 × 16 px')
    return
  }
  regions.value.push({ clientId: crypto.randomUUID(), bbox })
}

function percentBox(bbox: RegionDraft['bbox']) {
  return {
    left: `${bbox[0] / width.value * 100}%`, top: `${bbox[1] / height.value * 100}%`,
    width: `${(bbox[2] - bbox[0]) / width.value * 100}%`,
    height: `${(bbox[3] - bbox[1]) / height.value * 100}%`,
  }
}

const draftBox = computed(() => draft.value ? percentBox([
  Math.min(draft.value.x1, draft.value.x2), Math.min(draft.value.y1, draft.value.y2),
  Math.max(draft.value.x1, draft.value.x2), Math.max(draft.value.y1, draft.value.y2),
]) : undefined)

function confirm() {
  const normalizedName = name.value.trim()
  if (!normalizedName) { message.warning('请输入任务名称'); return }
  if (!regions.value.length) { message.warning('请至少框选一个识别区域'); return }
  emit('confirm', normalizedName, regions.value.map(region => ({ ...region, bbox: [...region.bbox] })))
}
</script>

<template>
  <a-modal :open="open" title="创建区域 OCR 任务" width="min(1040px, 94vw)" :footer="null" :mask-closable="false" @cancel="emit('close')">
    <div class="region-job-intro"><PlusOutlined /> 在图片上拖动框选一个或多个区域。提交后会创建独立任务，不修改来源任务。</div>
    <a-input v-model:value="name" class="region-job-name" addon-before="任务名称" :maxlength="200" />
    <div class="region-selector-scroll">
      <div class="region-selector" @pointerdown="begin" @pointermove="move" @pointerup="finish" @pointercancel="draft = undefined">
        <img ref="image" :src="activeUrl" alt="区域识别原图" draggable="false" @load="naturalWidth = image?.naturalWidth || 1; naturalHeight = image?.naturalHeight || 1" />
        <div v-for="(region, index) in regions" :key="region.clientId" class="region-box" :style="percentBox(region.bbox)">
          <span>区域 {{ index + 1 }}</span>
          <button type="button" title="删除区域" @pointerdown.stop @click.stop="regions.splice(index, 1)"><DeleteOutlined /></button>
        </div>
        <div v-if="draftBox" class="region-box is-draft" :style="draftBox"></div>
      </div>
    </div>
    <div class="region-job-footer">
      <span>已选择 {{ regions.length }} 个区域 · 原图 {{ width }} × {{ height }} px</span>
      <a-button @click="regions = []">清空</a-button>
      <a-button @click="emit('close')">取消</a-button>
      <a-button type="primary" :loading="submitting" @click="confirm" ><span style="color:white">创建区域识别任务</span></a-button>
    </div>
  </a-modal>
</template>
