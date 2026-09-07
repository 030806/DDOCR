import { describe, expect, it } from 'vitest'
import { bboxToCanvasRect, bboxToPolygon, canvasPointToSource, canvasRectToBbox, isValidPolygon, normalizeBbox, normalizePolygon, polygonToBbox, polygonToCanvasPoints, resultBoxColor, translatePolygonWithinBounds } from './bboxEditing'

describe('bbox editing coordinates', () => {
  const transform = { x: 10, y: 20, scale: .25, sourceWidth: 2400, sourceHeight: 1600 }

  it('round-trips original coordinates independently of viewer zoom', () => {
    const bbox: [number, number, number, number] = [1200, 800, 1800, 1000]
    expect(canvasRectToBbox(bboxToCanvasRect(bbox, transform), transform)).toEqual(bbox)
  })

  it('clips boxes to the source image and enforces a minimum size', () => {
    expect(normalizeBbox([-20, -10, 2, 1], 100, 80)).toEqual([0, 0, 4, 4])
    expect(normalizeBbox([98, 78, 120, 100], 100, 80)).toEqual([96, 76, 100, 80])
  })

  it('converts a four-point polygon to its compatible bbox', () => {
    const polygon = [[100, 80], [240, 60], [260, 150], [90, 170]] as const
    expect(polygonToBbox([...polygon] as any, 500, 400)).toEqual([90, 60, 260, 170])
    expect(bboxToPolygon([90, 60, 260, 170])).toEqual([[90, 60], [260, 60], [260, 170], [90, 170]])
  })

  it('maps polygon points through the canvas transform and clamps dragged points', () => {
    const transform = { x: 20, y: 30, scale: 0.5, sourceWidth: 1000, sourceHeight: 800 }
    expect(polygonToCanvasPoints([[0, 0], [100, 0], [100, 80], [0, 80]], transform)).toEqual([20, 30, 70, 30, 70, 70, 20, 70])
    expect(canvasPointToSource({ x: 900, y: -10 }, transform)).toEqual([1000, 0])
    expect(normalizePolygon([[-5, 10], [1010, 20], [900, 900], [2, 700]], 1000, 800)).toEqual([[0, 10], [1000, 20], [900, 800], [2, 700]])
  })

  it('rejects crossed and degenerate polygons', () => {
    expect(isValidPolygon([[10, 10], [100, 10], [100, 80], [10, 80]])).toBe(true)
    expect(isValidPolygon([[10, 10], [100, 80], [100, 10], [10, 80]])).toBe(false)
    expect(isValidPolygon([[10, 10], [11, 10], [11, 11], [10, 11]])).toBe(false)
  })

  it('moves the whole polygon without allowing it to leave the source image', () => {
    const polygon = [[10, 20], [90, 20], [90, 60], [10, 60]] as [[number, number], [number, number], [number, number], [number, number]]
    expect(translatePolygonWithinBounds(polygon, 15, -5, 120, 100)).toEqual([[25, 15], [105, 15], [105, 55], [25, 55]])
    expect(translatePolygonWithinBounds(polygon, -50, 80, 120, 100)).toEqual([[0, 60], [80, 60], [80, 100], [0, 100]])
  })

  it('uses a neutral box color and red for the selected result', () => {
    expect(resultBoxColor(false)).toBe('#b6bfbc')
    expect(resultBoxColor(true)).toBe('#ff4d4f')
  })
})
