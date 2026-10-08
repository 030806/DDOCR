import { describe, expect, it } from 'vitest'
import { copyRegions, regionBboxFromPoints } from './regionSelection'

describe('upload preview region selection', () => {
  it('normalizes reverse dragging in final image pixels', () => {
    expect(regionBboxFromPoints([180.3, 120.2], [20.4, 30.1], 200, 150)).toEqual([20, 30, 180, 120])
  })

  it('clamps to the image and rejects regions smaller than 16 pixels', () => {
    expect(regionBboxFromPoints([-20, 10], [50, 60], 40, 50)).toEqual([0, 10, 40, 50])
    expect(regionBboxFromPoints([4, 4], [19, 30], 100, 100)).toBeUndefined()
  })

  it('copies saved regions independently of preview edits', () => {
    const saved = [{ clientId: 'region-1', bbox: [1, 2, 30, 40] as [number, number, number, number] }]
    const preview = copyRegions(saved)
    preview[0].bbox[0] = 10
    expect(saved[0].bbox[0]).toBe(1)
  })
})
