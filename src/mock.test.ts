import { describe, expect, it } from 'vitest'
import { models, pages } from './mock'

describe('OCR mock contract', () => {
  it('provides selectable models and multi-page results', () => {
    expect(models.length).toBeGreaterThan(1)
    expect(pages.length).toBeGreaterThan(1)
  })

  it('uses the documented bbox, text and score fields', () => {
    for (const item of pages.flatMap((page) => page.items)) {
      expect(item.bbox).toHaveLength(4)
      expect(item.bbox[2]).toBeGreaterThan(item.bbox[0])
      expect(item.bbox[3]).toBeGreaterThan(item.bbox[1])
      expect(item.text.length).toBeGreaterThan(0)
      expect(item.score).toBeGreaterThanOrEqual(0)
      expect(item.score).toBeLessThanOrEqual(1)
    }
  })
})
