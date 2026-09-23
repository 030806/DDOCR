import { describe, expect, it } from 'vitest'
import { exportableOcrItems, filterOcrItems } from './resultVisibility'
import type { OcrItem } from './types/ocr'

const item = (id: string, score: number, reviewStatus?: OcrItem['reviewStatus']): OcrItem => ({
  id, text: id, score, bbox: [0, 0, 10, 10], comments: [], reviewStatus,
})

describe('OCR result visibility', () => {
  it('combines confidence and review-status filters', () => {
    const items = [item('ok', .8), item('low', .4), item('fp', .9, 'false_positive'), item('gone', .9, 'deleted')]
    expect(filterOcrItems(items, {
      search: '', minimumConfidence: .5, lowOnly: false, lowConfidenceThreshold: .7,
      showFalsePositive: false, showDeleted: false,
    }).map(value => value.id)).toEqual(['ok'])
  })

  it('always excludes deleted and false-positive results from export', () => {
    expect(exportableOcrItems([item('ok', .8), item('fp', .9, 'false_positive'), item('gone', .9, 'deleted')]).map(value => value.id)).toEqual(['ok'])
  })

  it('uses the minimum-confidence value as the low-confidence threshold', () => {
    const items = [item('high', .8), item('low', .6), item('very-low', .4)]
    const base = {
      search: '', minimumConfidence: .7, lowConfidenceThreshold: .5,
      showFalsePositive: false, showDeleted: false,
    }
    expect(filterOcrItems(items, { ...base, lowOnly: false }).map(value => value.id)).toEqual(['high'])
    expect(filterOcrItems(items, { ...base, lowOnly: true }).map(value => value.id)).toEqual(['low', 'very-low'])
  })

  it('falls back to the configured low-confidence threshold when showing all', () => {
    const items = [item('high', .8), item('low', .4)]
    expect(filterOcrItems(items, {
      search: '', minimumConfidence: 0, lowOnly: true, lowConfidenceThreshold: .5,
      showFalsePositive: false, showDeleted: false,
    }).map(value => value.id)).toEqual(['low'])
  })
})
