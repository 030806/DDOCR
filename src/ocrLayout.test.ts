import { describe, expect, it } from 'vitest'
import { getFinalOcrText, getLayoutCanvasHeight, mapBboxToRelative } from './ocrLayout'
import type { OcrItem } from './mock'

const item: OcrItem = { id: '1', text: 'QF10I', corrected: 'QF101', score: 0.9, bbox: [70, 76, 350, 152], comments: [] }

describe('OCR layout mapping', () => {
  it('maps bbox coordinates without changing their spatial relationship', () => {
    expect(mapBboxToRelative(item.bbox)).toEqual({ left: 10, top: 10, width: 40, height: 10 })
  })

  it('clips invalid coordinates to the document canvas', () => {
    expect(mapBboxToRelative([-10, -20, 800, 900])).toEqual({ left: 0, top: 0, width: 100, height: 100 })
  })

  it('uses corrected text when available and model text otherwise', () => {
    expect(getFinalOcrText(item)).toBe('QF101')
    expect(getFinalOcrText({ ...item, corrected: undefined })).toBe('QF10I')
  })

  it('preserves the source document aspect ratio', () => {
    expect(getLayoutCanvasHeight(350)).toBeCloseTo(380)
  })

  it('maps boxes using the real source image dimensions', () => {
    expect(mapBboxToRelative([1200, 800, 2400, 1200], 2400, 1600)).toEqual({
      left: 50, top: 50, width: 50, height: 25,
    })
    expect(getLayoutCanvasHeight(600, 2400, 1600)).toBe(400)
  })
})
