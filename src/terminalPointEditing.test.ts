import { describe, expect, it, vi } from 'vitest'
import { saveWithTerminalPointConfirmation, terminalPointChanges, terminalPointConfirmationText, terminalPointFromPointer } from './terminalPointEditing'
import type { TerminalPoint } from './types/ocr'

describe('terminal point save confirmation', () => {
  const point = (id: string): TerminalPoint => ({ id, x: 1, y: 2, source: 'manual' })
  it('counts additions and deletions including replacements with unchanged totals', () => {
    expect(terminalPointChanges([point('a'), point('b')], [point('a'), point('c')])).toEqual({ before: 2, after: 2, added: 1, deleted: 1, requiresConfirmation: true })
    expect(terminalPointConfirmationText([point('a')], [point('a'), point('b')])).toContain('从 1 变为 2')
  })
  it('does not save if the user returns to inspect added or deleted points', async () => {
    const persist = vi.fn(async () => {})
    const confirm = vi.fn(async () => false)
    expect(await saveWithTerminalPointConfirmation([point('a')], [], confirm, persist)).toBe(false)
    expect(confirm).toHaveBeenCalledOnce(); expect(persist).not.toHaveBeenCalled()
  })
  it('saves only after explicit confirmation', async () => {
    const persist = vi.fn(async () => {})
    const confirm = vi.fn(async () => { expect(persist).not.toHaveBeenCalled(); return true })
    expect(await saveWithTerminalPointConfirmation([], [point('a')], confirm, persist)).toBe(true)
    expect(persist).toHaveBeenCalledOnce()
  })
  it('does not ask about counts for coordinate-only moves', async () => {
    const confirm = vi.fn(async () => false), persist = vi.fn(async () => {})
    expect(await saveWithTerminalPointConfirmation([point('a')], [{ ...point('a'), y: 100 }], confirm, persist)).toBe(true)
    expect(confirm).not.toHaveBeenCalled(); expect(persist).toHaveBeenCalledOnce()
  })
})

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
