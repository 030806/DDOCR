<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { Pane, Splitpanes } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import { useRoute, useRouter } from 'vue-router'
import { models, pages as mockPages, type MockPage, type OcrItem } from '../mock'
import { getOcrPages, getTask } from '../api/ocr'
import { createSplitLayout } from '../splitLayout'
import { exportOcrResults, type ExportMode } from '../exportResults'
import type { ResultViewMode } from '../ocrLayout'
import UploadPanel from '../components/UploadPanel.vue'
import DocumentViewer from '../components/DocumentViewer.vue'
import OCRResultPanel from '../components/OCRResultPanel.vue'
import CorrectionModal from '../components/CorrectionModal.vue'
import CommentDrawer from '../components/CommentDrawer.vue'
import { useAppSettings } from '../composables/useAppSettings'

type JobState = 'ready' | 'running' | 'done'

const route = useRoute()
const router = useRouter()
const { settings } = useAppSettings()
const currentPage = ref(1)
const selectedId = ref('r-114')
const selectedModel = ref(settings.value.defaultModelId)
const zoom = ref(settings.value.defaultZoom)
const jobState = ref<JobState>('done')
const progress = ref(100)
const correctionOpen = ref(false)
const commentOpen = ref(false)
const resultViewMode = ref<ResultViewMode>(settings.value.defaultResultViewMode)
const workspaceWidth = ref(typeof window === 'undefined' ? 1440 : window.innerWidth)
const workspace = ref<{ $el: HTMLElement }>()
const pages = ref<MockPage[]>(mockPages)
let workspaceObserver: ResizeObserver | undefined

const page = computed(() => pages.value[currentPage.value - 1])
const selectedItem = computed(() => pages.value.flatMap((ocrPage) => ocrPage.items).find((item) => item.id === selectedId.value))
const currentModel = computed(() => models.find((model) => model.value === selectedModel.value)!)
const splitLayout = computed(() => createSplitLayout(workspaceWidth.value))

onMounted(() => {
  const workspaceElement = workspace.value?.$el
  if (workspaceElement) {
    workspaceWidth.value = workspaceElement.clientWidth
    workspaceObserver = new ResizeObserver(([entry]) => { workspaceWidth.value = entry.contentRect.width })
    workspaceObserver.observe(workspaceElement)
  }
})

onBeforeUnmount(() => workspaceObserver?.disconnect())

watch(() => route.params.taskId, async (taskId) => {
  if (typeof taskId !== 'string') return
  try {
    const [task, taskPages] = await Promise.all([getTask(taskId), getOcrPages(taskId)])
    pages.value = taskPages
    if (models.some((model) => model.value === task.modelId)) selectedModel.value = task.modelId
    currentPage.value = 1
    const candidates = taskPages[0]?.items || []
    const reviewItem = route.query.action === 'review' ? candidates.find((item) => item.score < 0.95) : undefined
    selectedId.value = (reviewItem || candidates[0])?.id || ''
    message.success(route.query.action === 'review' ? `已继续复核：${task.name}` : `已加载任务：${task.name}`)
  } catch {
    message.warning('未找到对应的 FastAPI 任务，已返回默认工作台')
    router.replace('/workspace')
  }
}, { immediate: true })

function selectItem(id: string) {
  selectedId.value = id
  nextTick(() => document.querySelector(`[data-result-id="${id}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
}

function switchPage(no: number) {
  currentPage.value = no
  selectedId.value = pages.value[no - 1].items[0]?.id || ''
}

function runMockOcr() {
  if (jobState.value === 'running') return
  jobState.value = 'running'
  progress.value = 8
  const timer = window.setInterval(() => { progress.value = Math.min(96, progress.value + Math.ceil(Math.random() * 14)) }, 160)
  window.setTimeout(() => {
    clearInterval(timer)
    progress.value = 100
    jobState.value = 'done'
    message.success(`识别完成 · ${currentModel.value.label}`)
  }, 1350)
}

function openCorrection(item: OcrItem) { selectItem(item.id); correctionOpen.value = true }
function saveCorrection(text: string) {
  if (!selectedItem.value) return
  selectedItem.value.corrected = text
  correctionOpen.value = false
  message.success('纠正已保存，原始识别内容已保留')
}
function openComment(item: OcrItem) { selectItem(item.id); commentOpen.value = true }
function saveComment(content: string) {
  if (!selectedItem.value) return
  selectedItem.value.comments.push({ id: `c-${Date.now()}`, author: '当前用户', content, time: '刚刚' })
  message.success('留言已添加')
}
function handleUpload() { jobState.value = 'ready'; progress.value = 0; message.success('已载入 Mock 文件：QC_Report_0714.pdf') }
async function handleExport(mode: ExportMode) {
  try {
    await exportOcrResults(page.value.items, mode, page.value.no)
    message.success(mode === 'simple' ? '精简结果已导出' : '完整结果已导出')
  } catch { message.error('导出失败，请重试') }
}
</script>

<template>
  <div class="workspace-view">
    <UploadPanel :models="models" :selected-model="selectedModel" :current-model="currentModel" :job-state="jobState" :progress="progress" @update:selected-model="selectedModel = $event" @upload="handleUpload" @run="runMockOcr" />
    <Splitpanes ref="workspace" class="workspace">
      <Pane :size="splitLayout.documentSizePercent" :min-size="splitLayout.documentMinPercent">
        <div class="document-workspace">
          <DocumentViewer :pages="pages" :page="page" :current-page="currentPage" :selected-id="selectedId" :zoom="zoom" :job-state="jobState" :progress="progress" @page-change="switchPage" @select="selectItem" @zoom-change="zoom = $event" />
        </div>
      </Pane>
      <Pane :size="splitLayout.resultSizePercent" :min-size="splitLayout.resultMinPercent">
        <OCRResultPanel :page="page" :pages="pages" :selected-id="selectedId" :model-label="currentModel.label" :low-confidence-threshold="settings.lowConfidenceThreshold" :show-confidence="settings.showConfidence" v-model:view-mode="resultViewMode" @select="selectItem" @correct="openCorrection" @comment="openComment" @export="handleExport" />
      </Pane>
    </Splitpanes>
    <CorrectionModal v-model:open="correctionOpen" :item="selectedItem" @save="saveCorrection" />
    <CommentDrawer v-model:open="commentOpen" :item="selectedItem" @save="saveComment" />
  </div>
</template>
