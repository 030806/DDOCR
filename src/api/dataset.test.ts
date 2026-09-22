import { beforeEach, describe, expect, it, vi } from 'vitest'
import { completeDatasetReview, datasetButton, expectedResults, getDatasetStatuses, saveDatasetEntry, type DatasetStatus } from './dataset'
import { apiClient } from './client'
import type { OcrPage } from '../types/ocr'

vi.mock('./client', () => ({ apiClient: { post: vi.fn() } }))
const status: DatasetStatus = { job_id: 'j', state: 'unreviewed', result_version: 3, reviewed_version: 3, reviewed_at: null, saved_version: null, image_id: 'INC_20260907_000001', last_error: null }
beforeEach(() => vi.clearAllMocks())

describe('dataset workflow', () => {
  it('gates storage and retry buttons on review state', () => {
    expect(datasetButton().disabled).toBe(true)
    expect(datasetButton(status).disabled).toBe(true)
    expect(datasetButton({ ...status, state: 'reviewed' }).disabled).toBe(false)
    expect(datasetButton({ ...status, state: 'failed' }).label).toBe('重试入库')
    expect(datasetButton({ ...status, state: 'saved' }).disabled).toBe(true)
    expect(datasetButton({ ...status, state: 'reviewed' }, true).disabled).toBe(true)
  })
  it('reviews all pages including excluded results to detect concurrent edits', async () => {
    const pages: OcrPage[] = [1, 2].map(no => ({ no, label: '', items: [{ id: `r${no}`, text: 'X', score: 0.1, bbox: [0, 0, 10, 10], comments: [], revision: 2, geometryRevision: 4, reviewStatus: no === 1 ? 'deleted' : 'unreviewed' }] }))
    vi.mocked(apiClient.post).mockResolvedValue({ data: { data: status } })
    await completeDatasetReview('j', pages)
    expect(expectedResults(pages)).toHaveLength(2)
    expect(apiClient.post).toHaveBeenCalledWith('/ocr/jobs/j/review-completion', { expected_results: expectedResults(pages) }, expect.anything())
  })
  it('sends the reviewed version for idempotent publication', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { data: status } })
    await saveDatasetEntry('j', 3)
    expect(apiClient.post).toHaveBeenCalledWith('/ocr/jobs/j/dataset-entries', { reviewed_version: 3 }, expect.anything())
  })
  it('batches history status requests within the API limit', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { data: [] } })
    await getDatasetStatuses(Array.from({ length: 201 }, (_, index) => String(index)))
    expect(apiClient.post).toHaveBeenCalledTimes(2)
    expect(vi.mocked(apiClient.post).mock.calls[1]?.[1]).toEqual({ job_ids: ['200'] })
  })
})
