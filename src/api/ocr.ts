import type { ModelOption, OcrItem, OcrPage, OcrPolygon, OcrReviewStatus } from '../types/ocr'
import type { OcrJobStatus, OcrTask, TaskStatus } from '../types/task'
import type { ExportMode } from '../exportResults'
import { apiClient } from './client'

// OCR 相关 API 封装。
// 负责把后端返回的数据映射为前端可直接使用的任务、页面和结果结构。

type ApiEnvelope<T> = { data: T; request_id: string }

type ApiJob = {
  id: string
  name: string
  file_name: string
  created_at: string
  model_id: string
  model_version: string
  page_count: number
  status: string
  stage?: string
  progress?: number
  started_at?: string | null
  finished_at?: string | null
  error_code?: string | null
  error_message?: string | null
  duration_ms?: number | null
  result_count: number
  review_count: number
}

type ApiPage = {
  page_no: number
  label: string
  image: {
    url: string | null
    width_px: number
    height_px: number
  }
}

type ApiComment = {
  id: string
  content: string
  author: { id: string; name: string }
  created_at: string
  updated_at?: string | null
}

type ApiResult = {
  id: string
  text: string
  confidence: number
  bbox: [number, number, number, number]
  polygon?: OcrPolygon | null
  display_text: string
  is_corrected: boolean
  comments: ApiComment[]
  revision: number
  review_status?: OcrReviewStatus
  geometry_revision?: number
  terminal_number?: string
  manual_confirmed?: boolean
  table_note?: string
  table_revision?: number
  attributes?: { source?: string }
}

type ApiCorrection = {
  id: string
  corrected_text: string
  revision: number
  created_by: { id: string; name: string }
  created_at: string
}

type ApiPageResults = { page_no: number; items: ApiResult[] }

type ApiUploadSession = {
  file_id: string
  upload_url: string
  upload_headers: Record<string, string>
}

type ApiFile = {
  id: string
  file_name: string
  width_px?: number
  height_px?: number
}

export type RegionDraft = {
  clientId: string
  bbox: OcrItem['bbox']
}

type ApiCreatedJob = {
  id: string
  status: string
  stage: string
  progress: number
  created_at: string
}

type ApiExport = {
  id: string
  job_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  download_url: string | null
}

type ApiModel = {
  id: string
  name: string
  default_version: string
  note: string
  estimated_ms_per_page: number
}

export type UploadProgressStage = 'session' | 'content' | 'complete' | 'job'

// 将后端任务状态映射为前端统一的任务状态。
function taskStatus(status: string, reviewCount: number): TaskStatus {
  if (status === 'queued') return 'queued'
  if (status === 'running') return 'running'
  if (status === 'failed' || status === 'cancelled') return 'failed'
  if (status === 'partial_success' || reviewCount > 0) return 'partial'
  return 'succeeded'
}

const jobStatuses = new Set<OcrJobStatus>([
  'queued', 'running', 'recognizing', 'persisting', 'partial_success',
  'succeeded', 'failed', 'cancelled',
])

function jobStatus(status: string, stage?: string): OcrJobStatus {
  if (status === 'running' && (stage === 'recognizing' || stage === 'persisting')) return stage
  return jobStatuses.has(status as OcrJobStatus) ? status as OcrJobStatus : 'failed'
}

// 根据文件扩展名判断文件类型，当前仅区分图片和 PDF。
function fileType(fileName: string): OcrTask['fileType'] {
  const extension = fileName.split('.').pop()?.toUpperCase()
  return extension === 'PNG' || extension === 'JPG' ? extension : 'PDF'
}

// 将接口返回的任务信息映射为前端展示使用的任务对象。
export function mapApiJob(job: ApiJob): OcrTask {
  return {
    id: job.id,
    name: job.name,
    fileName: job.file_name,
    fileType: fileType(job.file_name),
    createdAt: job.created_at,
    modelId: job.model_id,
    modelVersion: job.model_version,
    modelName: `${job.model_id} · ${job.model_version}`,
    pageCount: job.page_count,
    status: taskStatus(job.status, job.review_count),
    jobStatus: jobStatus(job.status, job.stage),
    stage: job.stage || job.status,
    progress: Math.min(100, Math.max(0, job.progress ?? (job.status === 'succeeded' ? 100 : 0))),
    startedAt: job.started_at ?? null,
    finishedAt: job.finished_at ?? null,
    errorCode: job.error_code ?? null,
    errorMessage: job.error_message ?? null,
    durationMs: job.duration_ms ?? null,
    regionCount: job.result_count,
    reviewCount: job.review_count,
    mockPageNumbers: Array.from({ length: job.page_count }, (_, index) => index + 1),
  }
}

// 将接口返回的 OCR 结果映射为前端展示项。
export function mapApiResult(result: ApiResult): OcrItem {
  return {
    id: result.id,
    text: result.text,
    score: result.confidence,
    bbox: result.bbox,
    polygon: result.polygon || undefined,
    revision: result.revision,
    corrected: result.is_corrected ? result.display_text : undefined,
    comments: result.comments.map((comment) => ({
      id: comment.id,
      authorId: comment.author.id,
      author: comment.author.name,
      content: comment.content,
      time: comment.created_at,
      updatedAt: comment.updated_at,
    })),
    reviewStatus: result.review_status || 'unreviewed',
    editSource: result.attributes?.source === 'manual' ? 'manual' : 'ocr',
    geometryRevision: result.geometry_revision || 0,
    terminalNumber: result.terminal_number || '',
    manualConfirmed: result.manual_confirmed || false,
    tableNote: result.table_note || '',
    tableRevision: result.table_revision || 0,
  }
}

export async function updateResultReviewStatus(resultIds: string[], reviewStatus: OcrReviewStatus) {
  const response = await apiClient.post<ApiEnvelope<{ updated_count: number; items: Array<{ id: string; review_status: OcrReviewStatus }> }>>(
    '/ocr/results/review-status',
    { result_ids: resultIds, review_status: reviewStatus },
  )
  return response.data.data
}

export async function updateResultTable(item: OcrItem, values: { terminalNumber: string; manualConfirmed: boolean; tableNote: string }) {
  const response = await apiClient.patch<ApiEnvelope<{
    terminal_number: string; manual_confirmed: boolean; table_note: string; table_revision: number
  }>>(`/ocr/results/${item.id}/table`, {
    terminal_number: values.terminalNumber,
    manual_confirmed: values.manualConfirmed,
    table_note: values.tableNote,
    base_revision: item.tableRevision || 0,
  })
  return response.data.data
}

export type ResultEditPayload = {
  updates: Array<{ result_id: string; bbox: OcrItem['bbox']; polygon?: OcrPolygon; base_revision: number }>
  creates: Array<{ client_id: string; bbox: OcrItem['bbox']; polygon?: OcrPolygon; text: string }>
  deletes: Array<{ result_id: string }>
}

export async function saveResultEdits(taskId: string, pageNo: number, payload: ResultEditPayload) {
  const response = await apiClient.post<ApiEnvelope<{
    updated: Array<{ id: string; bbox: OcrItem['bbox']; polygon?: OcrPolygon; geometry_revision: number }>
    created: Array<{ client_id: string; id: string }>
    deleted: string[]
  }>>(`/ocr/jobs/${taskId}/pages/${pageNo}/result-edits`, payload)
  return response.data.data
}

function mapApiComment(comment: ApiComment): OcrItem['comments'][number] {
  return {
    id: comment.id,
    authorId: comment.author.id,
    author: comment.author.name,
    content: comment.content,
    time: comment.created_at,
    updatedAt: comment.updated_at,
  }
}

// 新增纠错结果。
export async function createCorrection(resultId: string, correctedText: string, baseRevision: number) {
  const response = await apiClient.post<ApiEnvelope<ApiCorrection>>(
    `/ocr/results/${resultId}/corrections`,
    { corrected_text: correctedText, base_revision: baseRevision },
    { headers: { 'Idempotency-Key': crypto.randomUUID() } },
  )

  return response.data.data
}

// 为结果添加评论。
export async function createComment(resultId: string, content: string) {
  const response = await apiClient.post<ApiEnvelope<ApiComment>>(
    `/ocr/results/${resultId}/comments`,
    { content },
  )

  return mapApiComment(response.data.data)
}

// 更新已有评论内容。
export async function updateComment(resultId: string, commentId: string, content: string) {
  const response = await apiClient.patch<ApiEnvelope<ApiComment>>(
    `/ocr/results/${resultId}/comments/${commentId}`,
    { content },
  )

  return mapApiComment(response.data.data)
}

// 删除指定评论。
export async function deleteComment(resultId: string, commentId: string) {
  await apiClient.delete(`/ocr/results/${resultId}/comments/${commentId}`)
}

// 获取任务列表。
export async function getTasks(): Promise<OcrTask[]> {
  const response = await apiClient.get<ApiEnvelope<{ items: ApiJob[] }>>('/ocr/jobs', {
    params: { sort: '-created_at', limit: 100 },
  })

  return response.data.data.items.map(mapApiJob)
}

// 软删除任务；服务端保留审计数据，但不再对用户展示该任务。
export async function deleteTask(taskId: string) {
  await apiClient.delete(`/ocr/jobs/${taskId}`)
}

// 创建服务端全任务导出，并下载由后端真实 OCR 结果生成的 Excel。
export async function exportTaskResults(taskId: string, taskName: string, mode: ExportMode) {
  const created = await apiClient.post<ApiEnvelope<ApiExport>>(`/ocr/jobs/${taskId}/exports`, {
    format: 'xlsx',
    mode,
    scope: 'all_pages',
  })
  let taskExport = created.data.data

  if (taskExport.status !== 'succeeded') {
    const statusResponse = await apiClient.get<ApiEnvelope<ApiExport>>(
      `/ocr/jobs/${taskId}/exports/${taskExport.id}`,
    )
    taskExport = statusResponse.data.data
  }
  if (taskExport.status !== 'succeeded' || !taskExport.download_url) {
    throw new Error(taskExport.status === 'failed' ? 'Export failed' : 'Export is not ready')
  }

  const downloadPath = taskExport.download_url.replace(/^https?:\/\/[^/]+\/api\/v1/, '').replace(/^\/api\/v1/, '')
  const response = await apiClient.get<Blob>(downloadPath, { responseType: 'blob' })
  const objectUrl = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = `${taskName.replace(/[\\/:*?"<>|]/g, '_')}_${mode === 'simple' ? '精简' : '完整'}.xlsx`
  link.click()
  URL.revokeObjectURL(objectUrl)
}



// 获取单个任务详情。
export async function getTask(taskId: string): Promise<OcrTask> {
  const response = await apiClient.get<ApiEnvelope<ApiJob>>(`/ocr/jobs/${taskId}`)
  return mapApiJob(response.data.data)
}

// 获取任务对应的所有页面及其 OCR 结果。
export async function getOcrPages(taskId: string): Promise<OcrPage[]> {
  const pagesResponse = await apiClient.get<ApiEnvelope<{ items: ApiPage[] }>>(`/ocr/jobs/${taskId}/pages`)

  return Promise.all(
    pagesResponse.data.data.items.map(async (page) => {
      const [response, imageUrl] = await Promise.all([
        apiClient.get<ApiEnvelope<ApiPageResults>>(`/ocr/jobs/${taskId}/pages/${page.page_no}/results`),
        loadProtectedImage(page.image.url),
      ])

      return {
        no: page.page_no,
        label: page.label,
        items: response.data.data.items.map(mapApiResult),
        imageUrl,
        sourceWidth: page.image.width_px,
        sourceHeight: page.image.height_px,
      }
    }),
  )
}

// 下载受保护图片，并将其转换成浏览器可访问的 blob URL。
async function loadProtectedImage(url: string | null) {
  if (!url) return undefined

  const requestUrl = url.replace(/^\/api\/v1/, '')

  const response = await apiClient.get<Blob>(requestUrl, {
    responseType: 'blob',
  })

  return URL.createObjectURL(response.data)
}

// 释放页面图片占用的 blob URL，避免内存泄漏。
export function releasePageImages(pages: OcrPage[]) {
  for (const page of pages) {
    if (page.imageUrl?.startsWith('blob:')) URL.revokeObjectURL(page.imageUrl)
  }
}

// 上传文件并创建 OCR 任务，包含阶段性进度回调。
export async function uploadAndCreateOcrTask(
  file: File,
  model: Pick<ModelOption, 'value' | 'version'>,
  onStage?: (stage: UploadProgressStage, progress: number) => void,
): Promise<string> {
  const uploaded = await uploadOcrFile(file, onStage)

  onStage?.('job', 90)
  const jobResponse = await apiClient.post<ApiEnvelope<ApiCreatedJob>>('/ocr/jobs', {
    name: file.name.replace(/\.[^.]+$/, '') || file.name,
    file_id: uploaded.id,
    model_id: model.value,
    model_version: model.version,
    options: {},
  })

  onStage?.('job', 100)
  return jobResponse.data.data.id
}

export async function uploadOcrFile(
  file: File,
  onStage?: (stage: UploadProgressStage, progress: number) => void,
): Promise<ApiFile> {
  onStage?.('session', 10)

  const sessionResponse = await apiClient.post<ApiEnvelope<ApiUploadSession>>(
    '/files/upload-sessions',
    {
      file_name: file.name,
      size_bytes: file.size,
      media_type: file.type || 'application/octet-stream',
    },
  )
  const session = sessionResponse.data.data

  onStage?.('content', 20)
  await apiClient.put(`/files/${session.file_id}/content`, file, {
    headers: {
      ...session.upload_headers,
      'Content-Type': file.type || 'application/octet-stream',
    },
    onUploadProgress: (event) => {
      if (!event.total) return
      onStage?.('content', 20 + Math.round((event.loaded / event.total) * 55))
    },
  })

  onStage?.('complete', 80)
  const completed = await apiClient.post<ApiEnvelope<ApiFile>>(`/files/${session.file_id}/complete`)
  return { ...completed.data.data, id: completed.data.data.id || session.file_id }
}

export async function createRegionOcrTask(input: {
  name: string
  model: Pick<ModelOption, 'value' | 'version'>
  regions: RegionDraft[]
  fileId?: string
  sourceJobId?: string
}): Promise<string> {
  const response = await apiClient.post<ApiEnvelope<ApiCreatedJob>>('/ocr/region-jobs', {
    name: input.name,
    file_id: input.fileId,
    source_job_id: input.sourceJobId,
    model_id: input.model.value,
    model_version: input.model.version,
    pages: [{
      page_no: 1,
      regions: input.regions.map(region => ({ client_id: region.clientId, bbox: region.bbox })),
    }],
  })
  return response.data.data.id
}

export async function getModels(): Promise<ModelOption[]> {
  const response = await apiClient.get<ApiEnvelope<{ items: ApiModel[] }>>('/models', {
    params: { status: 'available' },
  })

  return response.data.data.items.map((model) => ({
    value: model.id,
    version: model.default_version,
    label: `${model.name} · ${model.default_version}`,
    note: model.note,
    speed: `${model.estimated_ms_per_page} ms/页`,
  }))
}
