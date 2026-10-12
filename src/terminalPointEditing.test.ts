import { describe, expect, it } from 'vitest'
import { terminalPointFromPointer } from './terminalPointEditing'

describe('terminal point creation coordinates', () => {
  const transform = { x: 100, y: 30, scale: 0.5, sourceWidth: 1000, sourceHeight: 1400 }

  it.each([0.5, 1, 2])('preserves the clicked source position at zoom %s', zoom => {
    const point = terminalPointFromPointer({ x: 250 * zoom, y: 230 * zoom }, zoom, transform)
    expect(point).toEqual({ x: 300, y: 400 })
    // Workspace spreads this payload into the new point; x/y must be named fields.
    expect({ id: 'draft', ...point, source: 'manual' }).toMatchObject({ x: 300, y: 400 })
  })

  it('accepts image edges and rejects clicks in the surrounding canvas', () => {
    expect(terminalPointFromPointer({ x: 100, y: 30 }, 1, transform)).toEqual({ x: 0, y: 0 })
    expect(terminalPointFromPointer({ x: 600, y: 730 }, 1, transform)).toEqual({ x: 1000, y: 1400 })
    expect(terminalPointFromPointer({ x: 99, y: 230 }, 1, transform)).toBeUndefined()
    expect(terminalPointFromPointer({ x: 250, y: 731 }, 1, transform)).toBeUndefined()
  })
})
