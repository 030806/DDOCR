import type { MockPage, OcrItem } from '../mock'
import type { OcrTask, TaskStatus } from '../types/task'
import { apiClient } from './client'

type ApiEnvelope<T> = { data: T; request_id: string }
type ApiJob = {
  id: string; name: string; file_name: string; created_at: string
  model_id: string; model_version: string; page_count: number; status: string
  duration_ms?: number | null; result_count: number; review_count: number
}
type ApiPage = { page_no: number; label: string }
type ApiComment = { id: string; content: string; author: { name: string }; created_at: string }
type ApiResult = {
  id: string; text: string; confidence: number
  bbox: [number, number, number, number]
  display_text: string; is_corrected: boolean; comments: ApiComment[]
}
type ApiPageResults = { page_no: number; items: ApiResult[] }

function taskStatus(status: string, reviewCount: number): TaskStatus {
  if (status === 'queued') return 'queued'
  if (status === 'running') return 'running'
  if (status === 'failed' || status === 'cancelled') return 'failed'
  if (status === 'partial_success' || reviewCount > 0) return 'partial'
  return 'succeeded'
}

function fileType(fileName: string): OcrTask['fileType'] {
  const extension = fileName.split('.').pop()?.toUpperCase()
  return extension === 'PNG' || extension === 'JPG' ? extension : 'PDF'
}

export function mapApiJob(job: ApiJob): OcrTask {
  return {
    id: job.id, name: job.name, fileName: job.file_name, fileType: fileType(job.file_name),
    createdAt: job.created_at, modelId: job.model_id,
    modelName: `${job.model_id} · ${job.model_version}`, pageCount: job.page_count,
    status: taskStatus(job.status, job.review_count), durationMs: job.duration_ms ?? null,
    regionCount: job.result_count, reviewCount: job.review_count,
    mockPageNumbers: Array.from({ length: job.page_count }, (_, index) => index + 1),
  }
}

export function mapApiResult(result: ApiResult): OcrItem {
  return {
    id: result.id, text: result.text, score: result.confidence, bbox: result.bbox,
    corrected: result.is_corrected ? result.display_text : undefined,
    comments: result.comments.map((comment) => ({
      id: comment.id, author: comment.author.name, content: comment.content, time: comment.created_at,
    })),
  }
}

export async function getTasks(): Promise<OcrTask[]> {
  const response = await apiClient.get<ApiEnvelope<{ items: ApiJob[] }>>('/ocr/jobs', {
    params: { sort: '-created_at', limit: 100 },
  })
  return response.data.data.items.map(mapApiJob)
}

export async function getTask(taskId: string): Promise<OcrTask> {
  const response = await apiClient.get<ApiEnvelope<ApiJob>>(`/ocr/jobs/${taskId}`)
  return mapApiJob(response.data.data)
}

export async function getOcrPages(taskId: string): Promise<MockPage[]> {
  const pagesResponse = await apiClient.get<ApiEnvelope<{ items: ApiPage[] }>>(`/ocr/jobs/${taskId}/pages`)
  return Promise.all(pagesResponse.data.data.items.map(async (page) => {
    const response = await apiClient.get<ApiEnvelope<ApiPageResults>>(
      `/ocr/jobs/${taskId}/pages/${page.page_no}/results`,
    )
    return { no: page.page_no, label: page.label, items: response.data.data.items.map(mapApiResult) }
  }))
}
