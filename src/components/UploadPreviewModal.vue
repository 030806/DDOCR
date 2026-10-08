<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { DeleteOutlined, RotateLeftOutlined, RotateRightOutlined, SaveOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { isPreviewableImage, rotateImageFile } from '../imageUpload'
import type { RegionDraft } from '../api/ocr'
import { copyRegions, MAX_OCR_REGIONS, regionBboxFromPoints } from '../regionSelection'

const props = defineProps<{ open: boolean; file?: File; initialRegions?: RegionDraft[] }>()
const emit = defineEmits<{ close: []; delete: []; save: [file: File, regions: RegionDraft[]] }>()
const workingFile = ref<File>()
const saving = ref(false)
const rotating = ref(false)
const previewUrl = ref('')
const image = ref<HTMLImageElement>()
const isImage = computed(() => Boolean(workingFile.value && isPreviewableImage(workingFile.value)))
const selecting = ref(false)
const regions = ref<RegionDraft[]>([])
const draft = ref<{ x1: number; y1: number; x2: number; y2: number }>()
const imageWidth = ref(0)
const imageHeight = ref(0)
let previewVersion = 0

function releasePreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

watch(() => [props.open, props.file] as const, ([open, file]) => {
  previewVersion++
  releasePreview()
  workingFile.value = open ? file : undefined
  draft.value = undefined
  imageWidth.value = 0
  imageHeight.value = 0
  if (!open) return
  regions.value = copyRegions(props.initialRegions || [])
  selecting.value = regions.value.length > 0
  if (file) previewUrl.value = URL.createObjectURL(file)
}, { immediate: true })

onBeforeUnmount(releasePreview)

async function rotate(degrees: number) {
  if (!workingFile.value || rotating.value) return
  const version = previewVersion
  rotating.value = true
  try {
    const rotated = await rotateImageFile(workingFile.value, degrees)
    if (!props.open || version !== previewVersion) return
    releasePreview()
    workingFile.value = rotated
    previewUrl.value = URL.createObjectURL(rotated)
    imageWidth.value = 0
    imageHeight.value = 0
    draft.value = undefined
    if (regions.value.length) message.info('图片已旋转，原选区已清空，请重新框选')
    regions.value = []
  } catch { message.error('图片旋转失败，请重试') }
  finally { rotating.value = false }
}

function point(event: PointerEvent): [number, number] | undefined {
  const rect = image.value?.getBoundingClientRect()
  if (!rect || !imageWidth.value || !imageHeight.value) return
  return [
    (Math.min(rect.right, Math.max(rect.left, event.clientX)) - rect.left) / rect.width * imageWidth.value,
    (Math.min(rect.bottom, Math.max(rect.top, event.clientY)) - rect.top) / rect.height * imageHeight.value,
  ]
}

function beginRegion(event: PointerEvent) {
  if (!selecting.value || rotating.value || event.button !== 0) return
  if (regions.value.length >= MAX_OCR_REGIONS) { message.warning(`单页最多框选 ${MAX_OCR_REGIONS} 个区域`); return }
  const start = point(event)
  if (!start) return
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  draft.value = { x1: start[0], y1: start[1], x2: start[0], y2: start[1] }
}

function moveRegion(event: PointerEvent) {
  if (!draft.value) return
  const current = point(event)
  if (!current) return
  draft.value.x2 = current[0]
  draft.value.y2 = current[1]
}

function finishRegion() {
  if (!draft.value) return
  const current = draft.value
  draft.value = undefined
  const bbox = regionBboxFromPoints(
    [current.x1, current.y1], [current.x2, current.y2], imageWidth.value, imageHeight.value,
  )
  if (!bbox) { message.warning('识别区域不能小于 16 × 16 px'); return }
  regions.value.push({ clientId: crypto.randomUUID(), bbox })
}

function percentBox(bbox: RegionDraft['bbox']) {
  return {
    left: `${bbox[0] / imageWidth.value * 100}%`, top: `${bbox[1] / imageHeight.value * 100}%`,
    width: `${(bbox[2] - bbox[0]) / imageWidth.value * 100}%`,
    height: `${(bbox[3] - bbox[1]) / imageHeight.value * 100}%`,
  }
}

const draftBox = computed(() => draft.value && imageWidth.value && imageHeight.value ? percentBox([
  Math.min(draft.value.x1, draft.value.x2), Math.min(draft.value.y1, draft.value.y2),
  Math.max(draft.value.x1, draft.value.x2), Math.max(draft.value.y1, draft.value.y2),
]) : undefined)

async function save() {
  if (!workingFile.value || rotating.value) return
  saving.value = true
  try {
    emit('save', workingFile.value, copyRegions(regions.value))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <a-modal :open="open" title="上传文件预览" width="min(900px, 92vw)" :footer="null" :mask-closable="false" @cancel="emit('close')">
    <div v-if="isImage" class="upload-preview-selection-bar">
      <a-checkbox v-model:checked="selecting">框选模式（拖动图片添加区域）</a-checkbox>
      <span>{{ regions.length ? `已选 ${regions.length} 个区域；开始识别将只处理选区` : '未框选时识别整张图片' }}</span>
      <a-button v-if="regions.length" size="small" @click="regions = []; draft = undefined">清空选区</a-button>
    </div>
    <div class="upload-preview-stage">
      <div v-if="isImage" class="upload-preview-image-wrap">
        <div class="region-selector" :class="{ 'selection-disabled': !selecting }" @pointerdown="beginRegion" @pointermove="moveRegion" @pointerup="finishRegion" @pointercancel="draft = undefined">
          <img ref="image" :src="previewUrl" :alt="file?.name" draggable="false" @load="imageWidth = image?.naturalWidth || 0; imageHeight = image?.naturalHeight || 0" />
          <div v-for="(region, index) in imageWidth && imageHeight ? regions : []" :key="region.clientId" class="region-box" :style="percentBox(region.bbox)">
            <span>区域 {{ index + 1 }}</span>
            <button type="button" title="删除区域" @pointerdown.stop @click.stop="regions.splice(index, 1)"><DeleteOutlined /></button>
          </div>
          <div v-if="draftBox" class="region-box is-draft" :style="draftBox"></div>
        </div>
      </div>
      <iframe v-else-if="previewUrl" :src="previewUrl" title="PDF 文件预览"></iframe>
    </div>
    <div class="upload-preview-info">
      <div><b>{{ workingFile?.name }}</b><small>请检查图片和选区，确认后保存为待识别文件</small></div>
      <div class="upload-preview-actions">
        <a-button v-if="isImage" :disabled="rotating || saving" @click="rotate(-90)"><RotateLeftOutlined />左转</a-button>
        <a-button v-if="isImage" :disabled="rotating || saving" @click="rotate(90)"><RotateRightOutlined />右转</a-button>
        <a-button danger @click="emit('delete')"><DeleteOutlined />删除</a-button>
        <a-button type="primary" :loading="saving || rotating" @click="save"><SaveOutlined />保存</a-button>
      </div>
    </div>
  </a-modal>
</template>
