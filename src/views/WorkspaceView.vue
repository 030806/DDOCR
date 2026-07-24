<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { FileSearchOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { isAxiosError } from 'axios'
import { Pane, Splitpanes } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import { useRoute, useRouter } from 'vue-router'
import type { ModelOption, OcrItem, OcrPage } from '../types/ocr'
import { createComment, createCorrection, deleteComment, getModels, getOcrPages, releasePageImages, updateComment, uploadAndCreateOcrTask } from '../api/ocr'
import { createSplitLayout } from '../splitLayout'
import { exportOcrResults, type ExportMode } from '../exportResults'
import type { ResultViewMode } from '../ocrLayout'
import UploadPanel from '../components/UploadPanel.vue'
import DocumentViewer from '../components/DocumentViewer.vue'
import OCRResultPanel from '../components/OCRResultPanel.vue'
import CorrectionModal from '../components/CorrectionModal.vue'
import CommentDrawer from '../components/CommentDrawer.vue'
import OcrProgressCard from '../components/OcrProgressCard.vue'
import { useAppSettings } from '../composables/useAppSettings'
import { useAuth } from '../composables/useAuth'
import { useOcrJobPolling } from '../composables/useOcrJobPolling'
import { createEmptyWorkspaceContent } from '../workspaceState'

type JobState = 'ready' | 'running' | 'done'

const route = useRoute()
const router = useRouter()
const { settings } = useAppSettings()
const { user } = useAuth()
const initialContent = createEmptyWorkspaceContent()
const currentPage = ref(initialContent.currentPage)
const selectedId = ref(initialContent.selectedId)
const selectedModel = ref('')
const availableModels = ref<ModelOption[]>([])
const zoom = ref(settings.value.defaultZoom)
const jobState = ref<JobState>('ready')
const progress = ref(0)
const taskLoading = ref(false)
const correctionOpen = ref(false)
const commentOpen = ref(false)
const reviewSaving = ref(false)
const resultViewMode = ref<ResultViewMode>(settings.value.defaultResultViewMode)
const workspaceWidth = ref(typeof window === 'undefined' ? 1440 : window.innerWidth)
const workspace = ref<{ $el: HTMLElement }>()
const pages = ref<OcrPage[]>(initialContent.pages)
const selectedFile = ref<File>()
let workspaceObserver: ResizeObserver | undefined
let taskLoadSequence = 0
const { task: polledTask, requestError: pollingError, elapsedMs, start: startPolling, stop: stopPolling, reset: resetPolling } = useOcrJobPolling()

const page = computed(() => pages.value[currentPage.value - 1])
const selectedItem = computed(() => pages.value.flatMap((ocrPage) => ocrPage.items).find((item) => item.id === selectedId.value))
const currentModel = computed(() => availableModels.value.find((model) => model.value === selectedModel.value))
const splitLayout = computed(() => createSplitLayout(workspaceWidth.value))
const selectedFileName = computed(() => selectedFile.value?.name || '请选择文件')
const selectedFileMeta = computed(() => {
  if (!selectedFile.value) return '支持 PDF、PNG、JPG，最大 100 MB'
  const size = selectedFile.value.size < 1024 * 1024
    ? `${Math.max(1, Math.round(selectedFile.value.size / 1024))} KB`
    : `${(selectedFile.value.size / 1024 / 1024).toFixed(1)} MB`
  const type = selectedFile.value.name.split('.').pop()?.toUpperCase() || 'FILE'
  return `${size} · ${type}`
})

function observeWorkspace() {
  workspaceObserver?.disconnect()
  workspaceObserver = undefined
  const workspaceElement = workspace.value?.$el
  if (!workspaceElement) return
  workspaceWidth.value = workspaceElement.clientWidth
  workspaceObserver = new ResizeObserver(([entry]) => { workspaceWidth.value = entry.contentRect.width })
  workspaceObserver.observe(workspaceElement)
}

onMounted(async () => {
  observeWorkspace()
  try {
    availableModels.value = await getModels()
    const preferred = availableModels.value.find((model) => model.value === settings.value.defaultModelId)
    selectedModel.value = preferred?.value || availableModels.value[0]?.value || ''
  } catch {
    message.error('识别模型加载失败')
  }
})

onBeforeUnmount(() => {
  stopPolling()
  workspaceObserver?.disconnect()
  releasePageImages(pages.value)
})

function ensureTaskModel(task: NonNullable<typeof polledTask.value>): void {
  if (!availableModels.value.some((model) => model.value === task.modelId)) {
    availableModels.value.push({ value: task.modelId, version: task.modelVersion || '', label: task.modelName, note: '', speed: '' })
  }
  selectedModel.value = task.modelId
}

async function loadCompletedTask(task: NonNullable<typeof polledTask.value>, sequence: number): Promise<void> {
  taskLoading.value = true
  try {
    const taskPages = await getOcrPages(task.id)
    if (sequence !== taskLoadSequence) { releasePageImages(taskPages); return }
    releasePageImages(pages.value)
    pages.value = taskPages
    ensureTaskModel(task)
    currentPage.value = 1
    const candidates = taskPages[0]?.items || []
    const reviewItem = route.query.action === 'review' ? candidates.find((item) => item.score < 0.95) : undefined
    selectedId.value = (reviewItem || candidates[0])?.id || ''
    jobState.value = 'done'
    progress.value = 100
    message.success(task.jobStatus === 'partial_success' ? `任务部分完成：${task.name}` : `识别完成：${task.name}`)
  } catch {
    if (sequence !== taskLoadSequence) return
    releasePageImages(pages.value)
    pages.value = []
    selectedId.value = ''
    message.error('OCR 已完成，但页面结果加载失败，请重试。')
  } finally {
    if (sequence === taskLoadSequence) taskLoading.value = false
  }
}

function pollTask(taskId: string, sequence: number): void {
  startPolling(taskId, {
    onUpdate(task) {
      if (sequence !== taskLoadSequence) return
      ensureTaskModel(task)
      progress.value = task.progress || 0
      jobState.value = 'running'
      taskLoading.value = false
    },
    onSucceeded(task) {
      if (sequence === taskLoadSequence) void loadCompletedTask(task, sequence)
    },
    onFailed() {
      if (sequence !== taskLoadSequence) return
      taskLoading.value = false
      jobState.value = 'ready'
    },
  })
}

function retryTask(): void {
  const taskId = route.params.taskId
  if (typeof taskId !== 'string') return
  taskLoading.value = true
  pollTask(taskId, taskLoadSequence)
}

watch(() => route.params.taskId, (taskId) => {
  const sequence = ++taskLoadSequence
  resetPolling()
  releasePageImages(pages.value)
  pages.value = []
  selectedId.value = ''
  if (typeof taskId !== 'string') {
    selectedFile.value = undefined
    jobState.value = 'ready'
    progress.value = 0
    taskLoading.value = false
    return
  }
  taskLoading.value = true
  jobState.value = 'running'
  progress.value = 0
  pollTask(taskId, sequence)
}, { immediate: true })

watch([taskLoading, page], async ([loading, activePage]) => {
  if (loading || !activePage) return
  await nextTick()
  observeWorkspace()
})

function selectItem(id: string) {
  selectedId.value = id
  nextTick(() => document.querySelector(`[data-result-id="${id}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
}

function switchPage(no: number) {
  currentPage.value = no
  selectedId.value = pages.value[no - 1].items[0]?.id || ''
}

async function runOcr() {
  if (jobState.value === 'running') return
  if (!selectedFile.value) {
    message.warning('请先选择要识别的 PDF 或图片文件')
    return
  }
  if (!currentModel.value) {
    message.warning('请先选择可用的识别模型')
    return
  }
  jobState.value = 'running'
  progress.value = 5
  try {
    const taskId = await uploadAndCreateOcrTask(selectedFile.value, currentModel.value, (_stage, value) => {
      progress.value = value
    })
    progress.value = 0
    jobState.value = 'running'
    message.success(`任务已提交 · ${currentModel.value.label}`)
    await router.push(`/workspace/${taskId}`)
  } catch {
    jobState.value = 'ready'
    progress.value = 0
    message.error('上传或创建 OCR 任务失败，请确认 FastAPI 服务已启动')
  }
}

function openCorrection(item: OcrItem) { selectItem(item.id); correctionOpen.value = true }
async function saveCorrection(text: string) {
  if (!selectedItem.value) return
  reviewSaving.value = true
  try {
    const correction = await createCorrection(selectedItem.value.id, text, selectedItem.value.revision || 0)
    selectedItem.value.corrected = correction.corrected_text
    selectedItem.value.revision = correction.revision
    correctionOpen.value = false
    message.success('纠正已保存，原始识别内容已保留')
  } catch (error) {
    const details = isAxiosError(error) ? error.response?.data?.error?.details : undefined
    if (error && isAxiosError(error) && error.response?.status === 409 && details) {
      selectedItem.value.revision = details.current_revision
      selectedItem.value.corrected = details.current_display_text
      message.warning('结果已被其他用户修改，已加载服务器最新内容，请重新确认')
    } else message.error('纠正保存失败')
  } finally { reviewSaving.value = false }
}
function openComment(item: OcrItem) { selectItem(item.id); commentOpen.value = true }
async function saveComment(content: string) {
  if (!selectedItem.value) return
  reviewSaving.value = true
  try {
    selectedItem.value.comments.push(await createComment(selectedItem.value.id, content))
    message.success('留言已添加')
  } catch { message.error('留言添加失败') }
  finally { reviewSaving.value = false }
}
async function editComment(commentId: string, content: string) {
  if (!selectedItem.value) return
  reviewSaving.value = true
  try {
    const saved = await updateComment(selectedItem.value.id, commentId, content)
    const index = selectedItem.value.comments.findIndex((comment) => comment.id === commentId)
    if (index >= 0) selectedItem.value.comments[index] = saved
    message.success('留言已更新')
  } catch { message.error('留言更新失败，仅留言作者可以修改') }
  finally { reviewSaving.value = false }
}
async function removeComment(commentId: string) {
  if (!selectedItem.value) return
  reviewSaving.value = true
  try {
    await deleteComment(selectedItem.value.id, commentId)
    selectedItem.value.comments = selectedItem.value.comments.filter((comment) => comment.id !== commentId)
    message.success('留言已删除')
  } catch { message.error('留言删除失败，仅留言作者可以删除') }
  finally { reviewSaving.value = false }
}
function handleUpload(file: File) {
  if (file.size > 100 * 1024 * 1024) {
    message.error('文件不能超过 100 MB')
    return
  }
  selectedFile.value = file
  jobState.value = 'ready'
  progress.value = 0
  message.success(`已载入文件：${file.name}`)
}
async function handleExport(mode: ExportMode) {
  try {
    // TODO(integration): Use the backend export job/download endpoints so exports
    // include server-side corrections and comments from every requested page.
    if (!page.value) return
    await exportOcrResults(page.value.items, mode, page.value.no)
    message.success(mode === 'simple' ? '精简结果已导出' : '完整结果已导出')
  } catch { message.error('导出失败，请重试') }
}
</script>

<template>
  <div class="workspace-view">
    <UploadPanel :models="availableModels" :selected-model="selectedModel" :current-model="currentModel" :job-state="jobState" :progress="progress" :file-name="selectedFileName" :file-meta="selectedFileMeta" @update:selected-model="selectedModel = $event" @upload="handleUpload" @run="runOcr" />
    <div v-if="taskLoading" class="workspace-empty"><a-spin size="large" /><p>正在加载任务数据…</p></div>
    <OcrProgressCard v-else-if="polledTask && !['succeeded', 'partial_success'].includes(polledTask.jobStatus || 'queued')" :task="polledTask" :elapsed-ms="elapsedMs" :request-failed="Boolean(pollingError)" @retry="retryTask" />
    <Splitpanes v-else-if="page" ref="workspace" class="workspace">
      <Pane :size="splitLayout.documentSizePercent" :min-size="splitLayout.documentMinPercent">
        <div class="document-workspace">
          <DocumentViewer :pages="pages" :page="page" :current-page="currentPage" :selected-id="selectedId" :zoom="zoom" :job-state="jobState" :progress="progress" @page-change="switchPage" @select="selectItem" @zoom-change="zoom = $event" />
        </div>
      </Pane>
      <Pane :size="splitLayout.resultSizePercent" :min-size="splitLayout.resultMinPercent">
        <OCRResultPanel :page="page" :pages="pages" :selected-id="selectedId" :model-label="currentModel?.label || selectedModel" :low-confidence-threshold="settings.lowConfidenceThreshold" :show-confidence="settings.showConfidence" v-model:view-mode="resultViewMode" @select="selectItem" @correct="openCorrection" @comment="openComment" @export="handleExport" />
      </Pane>
    </Splitpanes>
    <div v-else class="workspace-empty">
      <FileSearchOutlined />
      <h2>暂无任务</h2>
      <p>请选择历史任务，或上传文件创建 OCR 任务。</p>
      <button @click="router.push('/tasks')">查看历史任务</button>
    </div>
    <CorrectionModal v-model:open="correctionOpen" :item="selectedItem" :saving="reviewSaving" @save="saveCorrection" />
    <CommentDrawer v-model:open="commentOpen" :item="selectedItem" :current-user-id="user?.id" :saving="reviewSaving" @save="saveComment" @update-comment="editComment" @delete-comment="removeComment" />
  </div>
</template>
