import { apiClient } from './client'
import type { OcrPage } from '../types/ocr'

export type DatasetStatus = {
  job_id: string
  state: 'unreviewed' | 'reviewed' | 'saved' | 'failed'
  result_version: number
  reviewed_version: number | null
  reviewed_at: string | null
  saved_version: number | null
  image_id: string | null
  last_error: string | null
}

export function expectedResults(pages: OcrPage[]) {
  return pages.flatMap(page => page.items.map(item => ({
    id: item.id,
    revision: item.revision ?? 0,
    geometry_revision: item.geometryRevision ?? 0,
    review_status: item.reviewStatus ?? 'unreviewed',
  })))
}

export async function getDatasetStatuses(jobIds: string[]): Promise<DatasetStatus[]> {
  const output: DatasetStatus[] = []
  for (let i = 0; i < jobIds.length; i += 200) {
    const response = await apiClient.post<{ data: DatasetStatus[] }>('/ocr/jobs/dataset-statuses', { job_ids: jobIds.slice(i, i + 200) })
    output.push(...response.data.data)
  }
  return output
}

export async function completeDatasetReview(jobId: string, pages: OcrPage[]): Promise<DatasetStatus> {
  const response = await apiClient.post<{ data: DatasetStatus }>(`/ocr/jobs/${jobId}/review-completion`, { expected_results: expectedResults(pages) }, { timeout: 120_000 })
  return response.data.data
}

export async function saveDatasetEntry(jobId: string, reviewedVersion: number): Promise<DatasetStatus> {
  const response = await apiClient.post<{ data: DatasetStatus }>(`/ocr/jobs/${jobId}/dataset-entries`, { reviewed_version: reviewedVersion }, { timeout: 120_000 })
  return response.data.data
}

export function datasetButton(status?: DatasetStatus, saving = false) {
  if (saving) return { label: '入库中…', disabled: true, hint: '正在保存训练数据' }
  if (!status) return { label: '入库', disabled: true, hint: '复核状态未加载' }
  if (status.state === 'saved') return { label: '已入库', disabled: true, hint: status.image_id || '当前版本已入库' }
  if (status.state === 'unreviewed') return { label: '入库', disabled: true, hint: '请先完成复核' }
  return { label: status.state === 'failed' ? '重试入库' : '入库', disabled: false, hint: status.last_error || '已复核，可以入库' }
}
