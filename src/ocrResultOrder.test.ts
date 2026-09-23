import { describe, expect, it } from 'vitest'
import { sortOcrItemsByCoordinates } from './ocrResultOrder'
import type { OcrItem } from './types/ocr'

function item(id: string, bbox: OcrItem['bbox'], editSource?: OcrItem['editSource']): OcrItem {
  return { id, text: id, score: 1, bbox, comments: [], editSource }
}

describe('OCR result coordinate ordering', () => {
  it('orders top-to-bottom and uses left-to-right within the same row', () => {
    const manual = item('manual', [20, 10, 60, 30], 'manual')
    const ordered = sortOcrItemsByCoordinates([
      item('bottom', [5, 80, 20, 100]),
      item('right', [100, 10, 150, 30]),
      manual,
    ])

    expect(ordered.map(value => value.id)).toEqual(['manual', 'right', 'bottom'])
  })

  it('does not mutate the source result list', () => {
    const source = [item('bottom', [0, 50, 10, 60]), item('top', [0, 10, 10, 20])]
    sortOcrItemsByCoordinates(source)
    expect(source.map(value => value.id)).toEqual(['bottom', 'top'])
  })
})
