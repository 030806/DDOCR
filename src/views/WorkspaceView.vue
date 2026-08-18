<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { FileSearchOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { isAxiosError } from 'axios'
import { Pane, Splitpanes } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter, type NavigationGuardNext } from 'vue-router'
import type { ModelOption, OcrItem, OcrPage, OcrPolygon, OcrReviewStatus } from '../types/ocr'
import { createComment, createCorrection, createRegionOcrTask, deleteComment, getModels, getOcrPages, releasePageImages, saveResultEdits, updateComment, updateResultReviewStatus, uploadAndCreateOcrTask, uploadOcrFile, type RegionDraft } from '../api/ocr'
import { createSplitLayout } from '../splitLayout'
import { exportOcrResults, type ExportMode } from '../exportResults'
import type { ResultViewMode } from '../ocrLayout'
import UploadPanel from '../components/UploadPanel.vue'
import DocumentViewer from '../components/DocumentViewer.vue'
import OCRResultPanel from '../components/OCRResultPanel.vue'
import CorrectionModal from '../components/CorrectionModal.vue'
import CommentDrawer from '../components/CommentDrawer.vue'
import OcrProgressCard from '../components/OcrProgressCard.vue'
import UploadPreviewModal from '../components/UploadPreviewModal.vue'
import RegionJobModal from '../components/RegionJobModal.vue'
import { MAX_UPLOAD_SIZE_BYTES } from '../imageUpload'
import { useAppSettings } from '../composables/useAppSettings'
import { useAuth } from '../composables/useAuth'
import { useOcrJobPolling } from '../composables/useOcrJobPolling'
import { createEmptyWorkspaceContent } from '../workspaceState'
import { bboxToPolygon, cloneEditableItems, polygonToBbox, type EditableOcrItem } from '../bboxEditing'

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
const pendingFile = ref<File>()
const uploadPreviewOpen = ref(false)
const visibleResultIds = ref<string[]>()
const lastReviewAction = ref<Array<{ id: string; status: OcrReviewStatus }>>()
const bboxEditMode = ref(false)
const bboxDraftItems = ref<EditableOcrItem[]>([])
const bboxUndoStack = ref<EditableOcrItem[][]>([])
const bboxRedoStack = ref<EditableOcrItem[][]>([])
const bboxDirty = ref(false)
const pendingGeometrySnapshot = ref<EditableOcrItem[]>()
const pendingGeometryId = ref('')
const manualBbox = ref<OcrItem['bbox']>()
const manualText = ref('')
const manualTextOpen = ref(false)
const regionJobOpen = ref(false)
const regionJobMode = ref<'upload' | 'source'>('upload')
const regionJobSubmitting = ref(false)
let autoRegionTaskId = ''
let workspaceObserver: ResizeObserver | undefined
let taskLoadSequence = 0
const { task: polledTask, requestError: pollingError, elapsedMs, start: startPolling, stop: stopPolling, reset: resetPolling } = useOcrJobPolling()

const page = computed(() => pages.value[currentPage.value - 1])
const resultPanelPage = computed(() => page.value && bboxEditMode.value
  ? { ...page.value, items: bboxDraftItems.value }
  : page.value)
const displayPage = computed(() => {
  const activePage = resultPanelPage.value
  if (!activePage || !visibleResultIds.value) return activePage
  const visible = new Set(visibleResultIds.value)
  return { ...activePage, items: activePage.items.filter(item => visible.has(item.id)) }
})
const selectedItem = computed(() => pages.value.flatMap((ocrPage) => ocrPage.items).find((item) => item.id === selectedId.value))
const currentModel = computed(() => availableModels.value.find((model) => model.value === selectedModel.value))
const splitLayout = computed(() => createSplitLayout(workspaceWidth.value))
const selectedFileName = computed(() => selectedFile.value?.name || '请选择文件')
const selectedFileMeta = computed(() => {
  if (!selectedFile.value) return '支持 PDF、PNG、JPG，最大 200 MB'
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
  window.addEventListener('keydown', handleBboxKeyboard)
  window.addEventListener('beforeunload', handleBeforeUnload)
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
  window.removeEventListener('keydown', handleBboxKeyboard)
  window.removeEventListener('beforeunload', handleBeforeUnload)
  stopPolling()
  workspaceObserver?.disconnect()
  releasePageImages(pages.value)
})

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!bboxDirty.value && !pendingGeometrySnapshot.value) return
  event.preventDefault()
  event.returnValue = ''
}

function confirmBboxNavigation(next: NavigationGuardNext) {
  if (!bboxEditMode.value || (!bboxDirty.value && !pendingGeometrySnapshot.value)) { next(); return }
  Modal.confirm({
    title: '存在未保存的检测框修改',
    content: '离开后本次移动、缩放、新建和删除操作将丢失。',
    okText: '放弃并离开', cancelText: '取消',
    onOk: () => {
      bboxDirty.value = false
      bboxEditMode.value = false
      pendingGeometrySnapshot.value = undefined
      pendingGeometryId.value = ''
      next()
    },
    onCancel: () => next(false),
  })
}

onBeforeRouteUpdate((_to, _from, next) => confirmBboxNavigation(next))
onBeforeRouteLeave((_to, _from, next) => confirmBboxNavigation(next))

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
    if (route.query.action === 'region' && autoRegionTaskId !== task.id) {
      autoRegionTaskId = task.id
      regionJobMode.value = 'source'
      regionJobOpen.value = true
    }
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
  if (pendingGeometrySnapshot.value && pendingGeometryId.value !== id) {
    message.warning('请先确认或取消当前检测框修改')
    return
  }
  selectedId.value = id
  nextTick(() => document.querySelector(`[data-result-id="${id}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
}

function switchPage(no: number) {
  if (bboxEditMode.value && (bboxDirty.value || pendingGeometrySnapshot.value)) {
    message.warning('请先保存或退出检测框编辑模式')
    return
  }
  currentPage.value = no
  visibleResultIds.value = undefined
  selectedId.value = pages.value[no - 1].items[0]?.id || ''
}

function pushBboxHistory() {
  bboxUndoStack.value.push(cloneEditableItems(bboxDraftItems.value))
  if (bboxUndoStack.value.length > 50) bboxUndoStack.value.shift()
  bboxRedoStack.value = []
}

function toggleBboxEdit() {
  if (!bboxEditMode.value) {
    if (!page.value) return
    bboxDraftItems.value = cloneEditableItems(page.value.items.map(item => ({ ...item, editSource: 'ocr', editOperation: 'unchanged', geometryRevision: (item as EditableOcrItem).geometryRevision || 0 })))
    bboxUndoStack.value = []
    bboxRedoStack.value = []
    bboxDirty.value = false
    pendingGeometrySnapshot.value = undefined
    pendingGeometryId.value = ''
    bboxEditMode.value = true
    return
  }
  if (!bboxDirty.value && !pendingGeometrySnapshot.value) { bboxEditMode.value = false; return }
  Modal.confirm({
    title: '放弃未保存的检测框修改？', content: '移动、缩放、新建和删除操作都将丢失。',
    okText: '放弃修改', cancelText: '继续编辑', onOk: () => {
      bboxEditMode.value = false
      bboxDirty.value = false
      pendingGeometrySnapshot.value = undefined
      pendingGeometryId.value = ''
    },
  })
}

function previewDraftPolygon(id: string, polygon: OcrPolygon) {
  const item = bboxDraftItems.value.find(value => value.id === id)
  if (!item) return
  if (!pendingGeometrySnapshot.value) {
    pendingGeometrySnapshot.value = cloneEditableItems(bboxDraftItems.value)
    pendingGeometryId.value = id
  }
  if (pendingGeometryId.value !== id) return
  item.polygon = polygon
  item.bbox = polygonToBbox(polygon, page.value?.sourceWidth || 700, page.value?.sourceHeight || 760)
}

function confirmGeometryEdit() {
  const snapshot = pendingGeometrySnapshot.value
  const item = bboxDraftItems.value.find(value => value.id === pendingGeometryId.value)
  const original = snapshot?.find(value => value.id === pendingGeometryId.value)
  if (!snapshot || !item || !original) return
  bboxUndoStack.value.push(snapshot)
  if (bboxUndoStack.value.length > 50) bboxUndoStack.value.shift()
  bboxRedoStack.value = []
  item.originalBbox ||= [...original.bbox] as OcrItem['bbox']
  item.originalPolygon ||= original.polygon?.map(point => [...point]) as OcrPolygon | undefined
  if (item.editOperation !== 'created') item.editOperation = 'updated'
  bboxDirty.value = true
  pendingGeometrySnapshot.value = undefined
  pendingGeometryId.value = ''
  message.success('当前检测框已确认，请点击“保存全部”提交修改')
}

function cancelGeometryEdit() {
  if (!pendingGeometrySnapshot.value) return
  bboxDraftItems.value = pendingGeometrySnapshot.value
  pendingGeometrySnapshot.value = undefined
  pendingGeometryId.value = ''
  message.info('已取消当前检测框调整')
}

function beginManualBbox(bbox: OcrItem['bbox']) {
  manualBbox.value = bbox
  manualText.value = ''
  manualTextOpen.value = true
}

function confirmManualBbox() {
  const text = manualText.value.trim()
  if (!text || !manualBbox.value) { message.warning('请填写新检测框的文字内容'); return }
  pushBboxHistory()
  const id = `draft-${crypto.randomUUID()}`
  bboxDraftItems.value.push({
    id, text, score: 1, bbox: manualBbox.value, polygon: bboxToPolygon(manualBbox.value), comments: [], reviewStatus: 'unreviewed',
    editSource: 'manual', editOperation: 'created', geometryRevision: 0,
  })
  selectedId.value = id
  bboxDirty.value = true
  manualTextOpen.value = false
  manualBbox.value = undefined
}

function undoBboxEdit() {
  if (pendingGeometrySnapshot.value) { message.warning('请先确认或取消当前检测框修改'); return }
  const previous = bboxUndoStack.value.pop()
  if (!previous) return
  bboxRedoStack.value.push(cloneEditableItems(bboxDraftItems.value))
  bboxDraftItems.value = previous
  bboxDirty.value = true
}

function redoBboxEdit() {
  if (pendingGeometrySnapshot.value) { message.warning('请先确认或取消当前检测框修改'); return }
  const next = bboxRedoStack.value.pop()
  if (!next) return
  bboxUndoStack.value.push(cloneEditableItems(bboxDraftItems.value))
  bboxDraftItems.value = next
  bboxDirty.value = true
}

function deleteSelectedDraft() {
  if (pendingGeometrySnapshot.value) { message.warning('请先确认或取消当前检测框修改'); return }
  const index = bboxDraftItems.value.findIndex(item => item.id === selectedId.value)
  if (index < 0) return
  pushBboxHistory()
  const item = bboxDraftItems.value[index]
  if (item.editOperation === 'created') bboxDraftItems.value.splice(index, 1)
  else { item.editOperation = 'deleted'; item.reviewStatus = 'deleted' }
  selectedId.value = ''
  bboxDirty.value = true
}

function handleBboxKeyboard(event: KeyboardEvent) {
  if (!bboxEditMode.value || ['INPUT', 'TEXTAREA'].includes((event.target as HTMLElement)?.tagName)) return
  if ((event.key === 'Delete' || event.key === 'Backspace') && selectedId.value) { event.preventDefault(); deleteSelectedDraft() }
  else if (event.ctrlKey && event.key.toLowerCase() === 'z' && !event.shiftKey) { event.preventDefault(); undoBboxEdit() }
  else if (event.ctrlKey && (event.key.toLowerCase() === 'y' || (event.shiftKey && event.key.toLowerCase() === 'z'))) { event.preventDefault(); redoBboxEdit() }
}

async function saveBboxEdits() {
  const taskId = route.params.taskId
  if (typeof taskId !== 'string' || !page.value) return
  if (pendingGeometrySnapshot.value) { message.warning('请先确认或取消当前检测框修改'); return }
  const updates = bboxDraftItems.value.filter(item => item.editOperation === 'updated').map(item => ({ result_id: item.id, bbox: item.bbox, polygon: item.polygon, base_revision: item.geometryRevision || 0 }))
  const creates = bboxDraftItems.value.filter(item => item.editOperation === 'created').map(item => ({ client_id: item.id, bbox: item.bbox, polygon: item.polygon, text: item.text }))
  const deletes = bboxDraftItems.value.filter(item => item.editOperation === 'deleted' && item.editSource !== 'manual').map(item => ({ result_id: item.id }))
  try {
    await saveResultEdits(taskId, page.value.no, { updates, creates, deletes })
    const refreshed = await getOcrPages(taskId)
    releasePageImages(pages.value)
    pages.value = refreshed
    bboxEditMode.value = false
    bboxDirty.value = false
    bboxUndoStack.value = []
    bboxRedoStack.value = []
    message.success('检测框修改已保存')
  } catch (error) {
    message.error(isAxiosError(error) && error.response?.status === 409 ? '检测框已被其他用户修改，请刷新后重试' : '检测框修改保存失败')
  }
}

async function reviewResults(ids: string[], status: OcrReviewStatus) {
  const changed = pages.value.flatMap(ocrPage => ocrPage.items).filter(item => ids.includes(item.id))
  if (!changed.length) return
  const previous = changed.map(item => ({ id: item.id, status: item.reviewStatus || 'unreviewed' as OcrReviewStatus }))
  try {
    await updateResultReviewStatus(ids, status)
    changed.forEach(item => { item.reviewStatus = status })
    lastReviewAction.value = previous
    message.success(status === 'deleted' ? `已删除 ${changed.length} 条结果` : status === 'false_positive' ? `已标记 ${changed.length} 条误检` : `已恢复 ${changed.length} 条结果`)
  } catch {
    message.error('结果状态保存失败，请重试')
  }
}

async function undoReviewAction() {
  const action = lastReviewAction.value
  if (!action) return
  try {
    for (const status of ['unreviewed', 'confirmed', 'false_positive', 'deleted'] as OcrReviewStatus[]) {
      const ids = action.filter(item => item.status === status).map(item => item.id)
      if (ids.length) await updateResultReviewStatus(ids, status)
    }
    for (const pageItem of pages.value.flatMap(ocrPage => ocrPage.items)) {
      const previous = action.find(item => item.id === pageItem.id)
      if (previous) pageItem.reviewStatus = previous.status
    }
    lastReviewAction.value = undefined
    message.success('已撤销上一次结果操作')
  } catch { message.error('撤销失败，请重试') }
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

function openUploadRegionJob() {
  if (!selectedFile.value) { message.warning('请先选择图片文件'); return }
  if (!selectedFile.value.type.startsWith('image/')) {
    message.warning('首期局部框选识别仅支持 PNG、JPG 图片')
    return
  }
  regionJobMode.value = 'upload'
  regionJobOpen.value = true
}

function openSourceRegionJob() {
  if (!page.value?.imageUrl) { message.warning('原始图片不可用，无法创建区域任务'); return }
  if (bboxEditMode.value) { message.warning('请先退出检测框编辑模式'); return }
  regionJobMode.value = 'source'
  regionJobOpen.value = true
}

async function submitRegionJob(name: string, regions: RegionDraft[]) {
  if (!currentModel.value) return
  regionJobSubmitting.value = true
  try {
    let fileId: string | undefined
    let sourceJobId: string | undefined
    if (regionJobMode.value === 'upload') {
      if (!selectedFile.value) return
      jobState.value = 'running'
      const uploaded = await uploadOcrFile(selectedFile.value, (_stage, value) => { progress.value = value })
      fileId = uploaded.id
    } else {
      sourceJobId = typeof route.params.taskId === 'string' ? route.params.taskId : undefined
      if (!sourceJobId) return
    }
    const taskId = await createRegionOcrTask({
      name, model: currentModel.value, regions, fileId, sourceJobId,
    })
    regionJobOpen.value = false
    progress.value = 0
    jobState.value = 'running'
    message.success('独立区域 OCR 任务已创建，来源任务未被修改')
    await router.push(`/workspace/${taskId}`)
  } catch {
    jobState.value = regionJobMode.value === 'upload' ? 'ready' : 'done'
    progress.value = 0
    message.error('区域 OCR 任务创建失败，请检查选区和原始文件')
  } finally {
    regionJobSubmitting.value = false
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
  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    message.error('文件不能超过 200 MB')
    return
  }
  pendingFile.value = file
  uploadPreviewOpen.value = true
}
function previewUpload() {
  if (!selectedFile.value) return
  pendingFile.value = selectedFile.value
  uploadPreviewOpen.value = true
}
function saveUpload(file: File) {
  selectedFile.value = file
  pendingFile.value = undefined
  uploadPreviewOpen.value = false
  jobState.value = 'ready'
  progress.value = 0
  message.success(`文件已保存：${file.name}`)
}
function deleteUpload() {
  pendingFile.value = undefined
  selectedFile.value = undefined
  uploadPreviewOpen.value = false
  jobState.value = 'ready'
  progress.value = 0
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
    <UploadPanel :models="availableModels" :selected-model="selectedModel" :current-model="currentModel" :job-state="jobState" :progress="progress" :file-name="selectedFileName" :file-meta="selectedFileMeta" :has-file="Boolean(selectedFile)" @update:selected-model="selectedModel = $event" @upload="handleUpload" @preview="previewUpload" @run="runOcr" @region-run="openUploadRegionJob" />
    <div v-if="taskLoading" class="workspace-empty"><a-spin size="large" /><p>正在加载任务数据…</p></div>
    <OcrProgressCard v-else-if="polledTask && !['succeeded', 'partial_success'].includes(polledTask.jobStatus || 'queued')" :task="polledTask" :elapsed-ms="elapsedMs" :request-failed="Boolean(pollingError)" @retry="retryTask" />
    <Splitpanes v-else-if="page" ref="workspace" class="workspace">
      <Pane :size="splitLayout.documentSizePercent" :min-size="splitLayout.documentMinPercent">
        <div class="document-workspace">
          <DocumentViewer v-if="displayPage" :pages="pages" :page="displayPage" :current-page="currentPage" :selected-id="selectedId" :zoom="zoom" :job-state="jobState" :progress="progress" :edit-mode="bboxEditMode" :can-undo="Boolean(bboxUndoStack.length) && !pendingGeometrySnapshot" :can-redo="Boolean(bboxRedoStack.length) && !pendingGeometrySnapshot" :has-unsaved-changes="bboxDirty" :has-pending-geometry="Boolean(pendingGeometrySnapshot)" @page-change="switchPage" @select="selectItem" @zoom-change="zoom = $event" @edit-toggle="toggleBboxEdit" @undo="undoBboxEdit" @redo="redoBboxEdit" @save="saveBboxEdits" @polygon-preview="previewDraftPolygon" @geometry-confirm="confirmGeometryEdit" @geometry-cancel="cancelGeometryEdit" @create-bbox="beginManualBbox" @create-region-job="openSourceRegionJob" />
        </div>
      </Pane>
      <Pane :size="splitLayout.resultSizePercent" :min-size="splitLayout.resultMinPercent">
        <OCRResultPanel v-if="resultPanelPage" :page="resultPanelPage" :pages="pages" :selected-id="selectedId" :model-label="currentModel?.label || selectedModel" :low-confidence-threshold="settings.lowConfidenceThreshold" :show-confidence="settings.showConfidence" :can-undo-review="Boolean(lastReviewAction)" v-model:view-mode="resultViewMode" @select="selectItem" @correct="openCorrection" @comment="openComment" @export="handleExport" @review="reviewResults" @visible-change="visibleResultIds = $event" @undo="undoReviewAction" />
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
    <UploadPreviewModal :open="uploadPreviewOpen" :file="pendingFile" @close="uploadPreviewOpen = false" @delete="deleteUpload" @save="saveUpload" />
    <RegionJobModal
      :open="regionJobOpen"
      :file="regionJobMode === 'upload' ? selectedFile : undefined"
      :image-url="regionJobMode === 'source' ? page?.imageUrl : undefined"
      :source-width="regionJobMode === 'source' ? page?.sourceWidth : undefined"
      :source-height="regionJobMode === 'source' ? page?.sourceHeight : undefined"
      :initial-name="`${regionJobMode === 'source' ? polledTask?.name || page?.label || '任务' : selectedFile?.name.replace(/\.[^.]+$/, '') || '图片'}-区域识别`"
      :submitting="regionJobSubmitting"
      @close="regionJobOpen = false"
      @confirm="submitRegionJob"
    />
    <a-modal v-model:open="manualTextOpen" title="填写新检测框文字" ok-text="添加检测框" cancel-text="取消" :mask-closable="false" @ok="confirmManualBbox">
      <a-input v-model:value="manualText" :maxlength="500" show-count placeholder="请输入该区域的文字内容" @press-enter="confirmManualBbox" />
      <p class="modal-hint">新框由人工创建，不会触发 OCR；保存后将显示“人工新增”。</p>
    </a-modal>
  </div>
</template>
