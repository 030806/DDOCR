import { describe, expect, it } from 'vitest'
import { cloneEditableItems } from './bboxEditing'
import { applyCorrectionToItems } from './correctionState'
import type { OcrItem } from './types/ocr'

function result(): OcrItem {
  return {
    id: 'result-1', text: 'QF10I', score: 0.8, bbox: [1, 2, 30, 40],
    revision: 1, comments: [],
  }
}

describe('correction state', () => {
  it('updates both persisted results and the independent bbox-edit draft', () => {
    const persisted = [result()]
    const bboxDraft = cloneEditableItems(persisted)

    expect(applyCorrectionToItems(persisted, 'result-1', 'QF101', 2)).toBe(true)
    expect(applyCorrectionToItems(bboxDraft, 'result-1', 'QF101', 2)).toBe(true)

    expect(persisted[0]).toMatchObject({ corrected: 'QF101', revision: 2 })
    expect(bboxDraft[0]).toMatchObject({ corrected: 'QF101', revision: 2 })
    expect(bboxDraft[0].bbox).toEqual([1, 2, 30, 40])
  })

  it('does not modify unrelated results when the id is absent', () => {
    const items = [result()]
    expect(applyCorrectionToItems(items, 'missing', 'QF101', 2)).toBe(false)
    expect(items[0]).toMatchObject({ text: 'QF10I', revision: 1 })
    expect(items[0].corrected).toBeUndefined()
  })
})
