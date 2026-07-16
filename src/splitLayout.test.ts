import { describe, expect, it } from 'vitest'
import { createSplitLayout } from './splitLayout'

describe('OCR workspace split layout', () => {
  it('converts the required pixel minimums to pane percentages', () => {
    const layout = createSplitLayout(1200)

    expect(layout.documentMinPercent * 12).toBeCloseTo(400)
    expect(layout.resultMinPercent * 12).toBeCloseTo(300)
  })

  it('preserves the existing responsive result panel widths', () => {
    expect(createSplitLayout(1440).resultSizePercent * 14.4).toBeCloseTo(390)
    expect(createSplitLayout(1280).resultSizePercent * 12.8).toBeCloseTo(350)
  })

  it('always allocates the complete workspace', () => {
    const layout = createSplitLayout(1600)

    expect(layout.documentSizePercent + layout.resultSizePercent).toBeCloseTo(100)
  })
})
