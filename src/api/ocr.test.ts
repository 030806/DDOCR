import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from './client'
import { createComment, createCorrection, deleteComment, exportTaskResults, getModels, getOcrPages, mapApiJob, mapApiResult, saveResultEdits, updateComment, updateResultReviewStatus, uploadAndCreateOcrTask } from './ocr'

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('OCR API adapters', () => {
  it('persists batch result review status', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValueOnce({
      data: { data: { updated_count: 2, items: [] }, request_id: 'req-review' },
    } as never)
    const result = await updateResultReviewStatus(['r1', 'r2'], 'false_positive')
    expect(post).toHaveBeenCalledWith('/ocr/results/review-status', { result_ids: ['r1', 'r2'], review_status: 'false_positive' })
    expect(result.updated_count).toBe(2)
  })

  it('saves page result geometry edits in one request', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValueOnce({ data: { data: { updated: [], created: [], deleted: [] }, request_id: 'req-edit' } } as never)
    const payload = {
      updates: [{
        result_id: 'r1', bbox: [1, 2, 32, 42] as [number, number, number, number],
        polygon: [[2, 4], [30, 2], [32, 40], [1, 42]] as [[number, number], [number, number], [number, number], [number, number]],
        base_revision: 0,
      }], creates: [], deletes: [],
    }
    await saveResultEdits('job-1', 1, payload)
    expect(post).toHaveBeenCalledWith('/ocr/jobs/job-1/pages/1/result-edits', payload)
  })
  it('maps a FastAPI job to the existing task view model', () => {
    const task = mapApiJob({
      id: 'job-1', name: 'terminal', file_name: 'terminal.png',
      created_at: '2026-07-17T00:00:00Z', model_id: 'mock',
      model_version: '1.0.0', page_count: 1, status: 'succeeded',
      result_count: 3, review_count: 1,
    })
    expect(task.fileName).toBe('terminal.png')
    expect(task.status).toBe('partial')
    expect(task.regionCount).toBe(3)
  })

  it('maps confidence, bbox and polygon without changing OCR values', () => {
    const item = mapApiResult({
      id: 'result-1', text: 'QF10I', confidence: 0.884,
      bbox: [620, 240, 940, 320], display_text: 'QF10I',
      polygon: [[620, 245], [935, 240], [940, 315], [625, 320]],
      is_corrected: false, comments: [], revision: 0,
    })
    expect(item.score).toBe(0.884)
    expect(item.bbox).toEqual([620, 240, 940, 320])
    expect(item.polygon).toEqual([[620, 245], [935, 240], [940, 315], [625, 320]])
    expect(item.text).toBe('QF10I')
  })

  it('uploads a file, completes it, and creates a mock OCR job', async () => {
    const post = vi.spyOn(apiClient, 'post')
      .mockResolvedValueOnce({
        data: {
          data: {
            file_id: 'file-1',
            upload_url: 'http://127.0.0.1:8000/api/v1/files/file-1/content',
            upload_headers: { 'content-type': 'image/png' },
          },
          request_id: 'req-1',
        },
      })
      .mockResolvedValueOnce({ data: { data: { status: 'ready' }, request_id: 'req-2' } })
      .mockResolvedValueOnce({
        data: {
          data: {
            id: 'job-1', status: 'succeeded', stage: 'completed',
            progress: 100, created_at: '2026-07-20T00:00:00Z',
          },
          request_id: 'req-3',
        },
      })
    const put = vi.spyOn(apiClient, 'put').mockResolvedValue({
      data: { data: { status: 'validating' }, request_id: 'req-upload' },
    })
    const stages: number[] = []

    const taskId = await uploadAndCreateOcrTask(
      new File(['image'], 'terminal.png', { type: 'image/png' }),
      { value: 'mock', version: '1.0.0' },
      (_stage, progress) => stages.push(progress),
    )

    expect(taskId).toBe('job-1')
    expect(post).toHaveBeenNthCalledWith(1, '/files/upload-sessions', {
      file_name: 'terminal.png',
      size_bytes: 5,
      media_type: 'image/png',
    })
    expect(put).toHaveBeenCalledWith(
      '/files/file-1/content',
      expect.any(File),
      expect.objectContaining({ headers: expect.objectContaining({ 'Content-Type': 'image/png' }) }),
    )
    expect(post).toHaveBeenNthCalledWith(2, '/files/file-1/complete')
    expect(post).toHaveBeenNthCalledWith(3, '/ocr/jobs', expect.objectContaining({
      name: 'terminal',
      file_id: 'file-1',
      model_id: 'mock',
      model_version: '1.0.0',
    }))
    expect(stages[stages.length - 1]).toBe(100)
  })

  it('loads the available model catalog from the API', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        data: {
          items: [{
            id: 'mock', name: 'Mock OCR', default_version: '1.0.0',
            note: '服务器模型', estimated_ms_per_page: 20,
          }],
        },
        request_id: 'req-models',
      },
    })

    await expect(getModels()).resolves.toEqual([{
      value: 'mock', version: '1.0.0', label: 'Mock OCR · 1.0.0',
      note: '服务器模型', speed: '20 ms/页',
    }])
    expect(apiClient.get).toHaveBeenCalledWith('/models', { params: { status: 'available' } })
  })

  it('keeps the uploaded image URL and dimensions on API pages', async () => {
    const createObjectURL = vi.fn(() => 'blob:protected-image')
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL: vi.fn() })
    vi.spyOn(apiClient, 'get')
      .mockResolvedValueOnce({
        data: {
          data: {
            items: [{
              page_no: 1,
              label: '第 1 页',
              image: {
                url: '/api/v1/files/file-1/content',
                width_px: 1920,
                height_px: 1080,
              },
            }],
          },
          request_id: 'req-pages',
        },
      })
      .mockResolvedValueOnce({
        data: {
          data: { page_no: 1, items: [] },
          request_id: 'req-results',
        },
      })
      .mockResolvedValueOnce({ data: new Blob(['image']) })

    const pages = await getOcrPages('job-1')

    expect(pages[0]).toEqual({
      no: 1,
      label: '第 1 页',
      items: [],
      imageUrl: 'blob:protected-image',
      sourceWidth: 1920,
      sourceHeight: 1080,
    })
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(apiClient.get).toHaveBeenCalledWith('/files/file-1/content', {
      responseType: 'blob',
    })
  })

  it('creates, updates, and deletes comments with the server author', async () => {
    const serverComment = {
      id: 'comment-1', content: '请复核',
      author: { id: 'user-1', name: '林工' },
      created_at: '2026-07-21T08:00:00Z', updated_at: null,
    }
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: { data: serverComment, request_id: 'req-comment' },
    })
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({
      data: { data: { ...serverComment, content: '已复核' }, request_id: 'req-update' },
    })
    const remove = vi.spyOn(apiClient, 'delete').mockResolvedValue({})

    await expect(createComment('result-1', '请复核')).resolves.toMatchObject({
      id: 'comment-1', authorId: 'user-1', author: '林工', content: '请复核',
    })
    await expect(updateComment('result-1', 'comment-1', '已复核')).resolves.toMatchObject({ content: '已复核' })
    await deleteComment('result-1', 'comment-1')

    expect(post).toHaveBeenCalledWith('/ocr/results/result-1/comments', { content: '请复核' })
    expect(patch).toHaveBeenCalledWith('/ocr/results/result-1/comments/comment-1', { content: '已复核' })
    expect(remove).toHaveBeenCalledWith('/ocr/results/result-1/comments/comment-1')
  })

  it('submits correction text with the current revision', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: {
        data: {
          id: 'correction-1', corrected_text: 'XT-102', revision: 2,
          created_by: { id: 'user-1', name: '林工' }, created_at: '2026-07-21T08:00:00Z',
        },
        request_id: 'req-correction',
      },
    })

    await expect(createCorrection('result-1', 'XT-102', 1)).resolves.toMatchObject({ revision: 2 })
    expect(post).toHaveBeenCalledWith(
      '/ocr/results/result-1/corrections',
      { corrected_text: 'XT-102', base_revision: 1 },
      { headers: { 'Idempotency-Key': expect.any(String) } },
    )
  })

  it('creates and downloads a backend export for the selected real task', async () => {
    const click = vi.fn()
    const createObjectURL = vi.fn(() => 'blob:task-export')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })
    vi.stubGlobal('document', { createElement: vi.fn(() => ({ href: '', download: '', click })) })
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: { data: {
        id: 'export-1', job_id: 'job-1', status: 'succeeded',
        download_url: 'http://127.0.0.1:8000/api/v1/ocr/jobs/job-1/exports/export-1/download',
      } },
    })
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: new Blob(['xlsx']) })

    await exportTaskResults('job-1', '端子/任务', 'simple')

    expect(post).toHaveBeenCalledWith('/ocr/jobs/job-1/exports', {
      format: 'xlsx', mode: 'simple', scope: 'all_pages',
    })
    expect(get).toHaveBeenCalledWith('/ocr/jobs/job-1/exports/export-1/download', { responseType: 'blob' })
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(click).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:task-export')
  })
})
