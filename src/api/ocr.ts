import type { MockPage, OcrItem } from '../mock'
import type { OcrTask, TaskStatus } from '../types/task'
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
  display_text: string
  is_corrected: boolean
  comments: ApiComment[]
  revision: number
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

type ApiCreatedJob = {
  id: string
  status: string
  stage: string
  progress: number
  created_at: string
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
    modelName: `${job.model_id} · ${job.model_version}`,
    pageCount: job.page_count,
    status: taskStatus(job.status, job.review_count),
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
  }
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

// 获取单个任务详情。
export async function getTask(taskId: string): Promise<OcrTask> {
  const response = await apiClient.get<ApiEnvelope<ApiJob>>(`/ocr/jobs/${taskId}`)
  return mapApiJob(response.data.data)
}

// 获取任务对应的所有页面及其 OCR 结果。
export async function getOcrPages(taskId: string): Promise<MockPage[]> {
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
  console.log('[loadProtectedImage] 实际请求 URL:', requestUrl)

  const response = await apiClient.get<Blob>(requestUrl, {
    responseType: 'blob',
  })

  return URL.createObjectURL(response.data)
}

// 释放页面图片占用的 blob URL，避免内存泄漏。
export function releasePageImages(pages: MockPage[]) {
  for (const page of pages) {
    if (page.imageUrl?.startsWith('blob:')) URL.revokeObjectURL(page.imageUrl)
  }
}

// 上传文件并创建 OCR 任务，包含阶段性进度回调。
export async function uploadAndCreateOcrTask(
  file: File,
  onStage?: (stage: UploadProgressStage, progress: number) => void,
): Promise<string> {
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
  await apiClient.post(`/files/${session.file_id}/complete`)

  onStage?.('job', 90)
  // TODO(integration): Fetch the model catalog from /models and submit the selected
  // backend model/version. The current Mock Backend accepts only mock@1.0.0.
  const jobResponse = await apiClient.post<ApiEnvelope<ApiCreatedJob>>('/ocr/jobs', {
    name: file.name.replace(/\.[^.]+$/, '') || file.name,
    file_id: session.file_id,
    model_id: 'mock',
    model_version: '1.0.0',
    options: {},
  })

  onStage?.('job', 100)
  return jobResponse.data.data.id
}
