<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { isAxiosError } from 'axios'
import { Pane, Splitpanes } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import { useRoute, useRouter } from 'vue-router'
import { models, pages as mockPages, type MockPage, type OcrItem } from '../mock'
import { createComment, createCorrection, deleteComment, getOcrPages, getTask, releasePageImages, updateComment, uploadAndCreateOcrTask } from '../api/ocr'
import { createSplitLayout } from '../splitLayout'
import { exportOcrResults, type ExportMode } from '../exportResults'
import type { ResultViewMode } from '../ocrLayout'
import UploadPanel from '../components/UploadPanel.vue'
import DocumentViewer from '../components/DocumentViewer.vue'
import OCRResultPanel from '../components/OCRResultPanel.vue'
import CorrectionModal from '../components/CorrectionModal.vue'
import CommentDrawer from '../components/CommentDrawer.vue'
import { useAppSettings } from '../composables/useAppSettings'
import { useAuth } from '../composables/useAuth'

type JobState = 'ready' | 'running' | 'done'

const route = useRoute()
const router = useRouter()
const { settings } = useAppSettings()
const { user } = useAuth()
const currentPage = ref(1)
const selectedId = ref('r-114')
const selectedModel = ref(settings.value.defaultModelId)
const zoom = ref(settings.value.defaultZoom)
const jobState = ref<JobState>('done')
const progress = ref(100)
const correctionOpen = ref(false)
const commentOpen = ref(false)
const reviewSaving = ref(false)
const resultViewMode = ref<ResultViewMode>(settings.value.defaultResultViewMode)
const workspaceWidth = ref(typeof window === 'undefined' ? 1440 : window.innerWidth)
const workspace = ref<{ $el: HTMLElement }>()
// The route without a task id intentionally keeps the original demo canvas.
// TODO(integration): Replace it with an explicit empty/upload state when mock.ts is retired.
const pages = ref<MockPage[]>(mockPages)
const selectedFile = ref<File>()
let workspaceObserver: ResizeObserver | undefined

const page = computed(() => pages.value[currentPage.value - 1])
const selectedItem = computed(() => pages.value.flatMap((ocrPage) => ocrPage.items).find((item) => item.id === selectedId.value))
const currentModel = computed(() => models.find((model) => model.value === selectedModel.value)!)
const splitLayout = computed(() => createSplitLayout(workspaceWidth.value))
const selectedFileName = computed(() => selectedFile.value?.name || 'QC_Report_0714.pdf')
const selectedFileMeta = computed(() => {
  if (!selectedFile.value) return '3 页 · 2.4 MB · PDF'
  const size = selectedFile.value.size < 1024 * 1024
    ? `${Math.max(1, Math.round(selectedFile.value.size / 1024))} KB`
    : `${(selectedFile.value.size / 1024 / 1024).toFixed(1)} MB`
  const type = selectedFile.value.name.split('.').pop()?.toUpperCase() || 'FILE'
  return `${size} · ${type}`
})

onMounted(() => {
  const workspaceElement = workspace.value?.$el
  if (workspaceElement) {
    workspaceWidth.value = workspaceElement.clientWidth
    workspaceObserver = new ResizeObserver(([entry]) => { workspaceWidth.value = entry.contentRect.width })
    workspaceObserver.observe(workspaceElement)
  }
})

onBeforeUnmount(() => {
  workspaceObserver?.disconnect()
  releasePageImages(pages.value)
})

watch(() => route.params.taskId, async (taskId) => {
  if (typeof taskId !== 'string') return
  try {
    const [task, taskPages] = await Promise.all([getTask(taskId), getOcrPages(taskId)])
    releasePageImages(pages.value)
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

async function runOcr() {
  if (jobState.value === 'running') return
  if (!selectedFile.value) {
    message.warning('请先选择要识别的 PDF 或图片文件')
    return
  }
  jobState.value = 'running'
  progress.value = 5
  try {
    const taskId = await uploadAndCreateOcrTask(selectedFile.value, (_stage, value) => {
      progress.value = value
    })
    progress.value = 100
    jobState.value = 'done'
    message.success(`识别完成 · ${currentModel.value.label}`)
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
    await exportOcrResults(page.value.items, mode, page.value.no)
    message.success(mode === 'simple' ? '精简结果已导出' : '完整结果已导出')
  } catch { message.error('导出失败，请重试') }
}
</script>

<template>
  <div class="workspace-view">
    <UploadPanel :models="models" :selected-model="selectedModel" :current-model="currentModel" :job-state="jobState" :progress="progress" :file-name="selectedFileName" :file-meta="selectedFileMeta" @update:selected-model="selectedModel = $event" @upload="handleUpload" @run="runOcr" />
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
    <CorrectionModal v-model:open="correctionOpen" :item="selectedItem" :saving="reviewSaving" @save="saveCorrection" />
    <CommentDrawer v-model:open="commentOpen" :item="selectedItem" :current-user-id="user?.id" :saving="reviewSaving" @save="saveComment" @update-comment="editComment" @delete-comment="removeComment" />
  </div>
</template>
