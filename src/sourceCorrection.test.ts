import { describe, expect, it } from 'vitest'
import { sourceCorrectionUnavailable, sourcePreviewStyle } from './sourceCorrection'
import type { OcrItem } from './types/ocr'
const item: OcrItem = { id: 'ocr-1', text: 'C01', score: 0.9, bbox: [10, 20, 110, 60], comments: [] }
describe('source correction', () => {
  it('allows an actual OCR source and blocks terminal-only records', () => {
    expect(sourceCorrectionUnavailable(item)).toBe('')
    expect(sourceCorrectionUnavailable()).not.toBe('')
    expect(sourceCorrectionUnavailable({ ...item, terminalPointId: 'p1' })).not.toBe('')
    expect(sourceCorrectionUnavailable({ ...item, id: 'terminal:p1' })).not.toBe('')
  })
  it('requires deleted and false positive sources to be restored', () => {
    expect(sourceCorrectionUnavailable({ ...item, reviewStatus: 'deleted' })).not.toBe('')
    expect(sourceCorrectionUnavailable({ ...item, reviewStatus: 'false_positive' })).not.toBe('')
  })
  it('crops the source using image coordinates with bounded scaling', () => {
    expect(sourcePreviewStyle(item, 1000, 800)).toEqual({ width: '300px', height: '120px', backgroundSize: '3000px 2400px', backgroundPosition: '-30px -60px' })
  })
})
