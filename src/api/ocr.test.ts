import { describe, expect, it } from 'vitest'
import { mapApiJob, mapApiResult } from './ocr'

describe('OCR API adapters', () => {
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

  it('maps confidence and bbox without changing OCR values', () => {
    const item = mapApiResult({
      id: 'result-1', text: 'QF10I', confidence: 0.884,
      bbox: [620, 240, 940, 320], display_text: 'QF10I',
      is_corrected: false, comments: [],
    })
    expect(item.score).toBe(0.884)
    expect(item.bbox).toEqual([620, 240, 940, 320])
    expect(item.text).toBe('QF10I')
  })
})
