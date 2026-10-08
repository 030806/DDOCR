import { describe, expect, it } from 'vitest'
import { boundedModalOffset } from './modalDrag'

describe('modal dragging', () => {
  const bounds = { left: 300, top: 200, right: 700, bottom: 500 }
  const viewport = { width: 1000, height: 800 }

  it('moves within the viewport', () => {
    expect(boundedModalOffset({ x: 0, y: 0 }, bounds, viewport, { x: 80, y: -40 }))
      .toEqual({ x: 80, y: -40 })
  })

  it('keeps the dialog visible at each edge', () => {
    expect(boundedModalOffset({ x: 20, y: -10 }, bounds, viewport, { x: -900, y: 900 }))
      .toEqual({ x: -264, y: 274 })
  })
})
