import { describe, expect, it, vi } from 'vitest'
import { createGridEditing, normalizeGridValue, parseGridClipboard, sequentialNumbers, type GridValues } from './ocrGridEditing'
import type { OcrItem } from './types/ocr'

const item = (id: string): OcrItem => ({ id, text: id, score: 1, bbox: [0, 0, 10, 10], comments: [] })
function setup(items = [item('a'), item('b')]) {
  const table = vi.fn(async (row: OcrItem, value: GridValues) => { Object.assign(row, { terminalNumber: value.terminalNumber, tableNote: value.tableNote, manualConfirmed: value.manualConfirmed, tableRevision: (row.tableRevision || 0) + 1 }) })
  const cable = vi.fn(async (row: OcrItem, text: string) => { row.corrected = text; row.revision = (row.revision || 0) + 1 })
  return { items, table, cable, editing: createGridEditing(() => items, table, cable) }
}
const deferred = () => { let resolve!: () => void; const promise = new Promise<void>(r => { resolve = r }); return { promise, resolve } }

describe('grid clipboard and numbering', () => {
  it('parses Excel quoted cells, newlines, tabs and escaped quotes without coercion', () => {
    expect(parseGridClipboard('001\t"a\tb"\r\n=ABC\t"line1\nline2 ""Q"""\r\n')).toEqual([['001', 'a\tb'], ['=ABC', 'line1\nline2 "Q"']])
    expect(parseGridClipboard('a\t')).toEqual([['a', '']])
    expect(() => parseGridClipboard('"bad')).toThrow()
  })
  it('keeps identifiers as text and rejects invalid confirmations and empty cables', () => {
    expect(normalizeGridValue('cable', '=001')).toBe('=001')
    expect(normalizeGridValue('terminalNumber', '001')).toBe('001')
    expect(normalizeGridValue('manualConfirmed', '否')).toBe(false)
    expect(() => normalizeGridValue('manualConfirmed', 'maybe')).toThrow()
    expect(() => normalizeGridValue('cable', ' ')).toThrow()
  })
  it('numbers in visible order, skips existing values without consuming a number', () => {
    const result = sequentialNumbers(['c', 'a', 'b'], id => id === 'a' ? 'existing' : '', { start: 1, step: 2, width: 3, prefix: 'XT-', suffix: 'L', overwrite: false })
    expect(result).toEqual([{ id: 'c', field: 'terminalNumber', value: 'XT-001L' }, { id: 'b', field: 'terminalNumber', value: 'XT-003L' }])
  })
  it('rejects invalid numbering and supports explicit overwrite', () => {
    const options = { start: 1, step: 1, width: 2, prefix: '', suffix: '', overwrite: true }
    expect(sequentialNumbers(['a'], () => 'existing', options)[0]!.value).toBe('01')
    expect(() => sequentialNumbers(['a'], () => '', { ...options, start: -1 })).toThrow()
    expect(() => sequentialNumbers(['a'], () => '', { ...options, step: 0 })).toThrow()
  })
})

describe('grid persistence and history', () => {
  it('keeps history intact and prevents writes when an edit no longer passes business validation', async () => {
    const items = [item('a')]
    let allowed = true
    const table = vi.fn(async (row: OcrItem, values: GridValues) => { row.terminalNumber = values.terminalNumber })
    const editing = createGridEditing(() => items, table, async () => {}, () => { if (!allowed) throw new Error('先补充端子点') })
    editing.apply([{ id: 'a', field: 'terminalNumber', value: '101' }]); await editing.flush()
    allowed = false
    expect(() => editing.history()).toThrow('先补充端子点')
    expect(editing.state.undo).toHaveLength(1)
    expect(() => editing.apply([{ id: 'a', field: 'terminalNumber', value: '102' }])).toThrow()
    expect(table).toHaveBeenCalledTimes(1)
  })
  it('persists by ID despite reordered rows and combines table changes per row', async () => {
    const { items, editing, table, cable } = setup()
    editing.apply([{ id: 'a', field: 'terminalNumber', value: '001' }, { id: 'a', field: 'tableNote', value: 'note' }, { id: 'a', field: 'cable', value: '=ABC' }])
    items.reverse()
    expect(await editing.flush()).toBe(true)
    expect(table).toHaveBeenCalledTimes(1); expect(cable).toHaveBeenCalledTimes(1)
    expect(items.find(row => row.id === 'a')).toMatchObject({ terminalNumber: '001', tableNote: 'note', corrected: '=ABC' })
  })
  it('validates a batch before changing any drafts', () => {
    const { editing } = setup()
    expect(() => editing.apply([{ id: 'a', field: 'terminalNumber', value: '001' }, { id: 'b', field: 'cable', value: '' }])).toThrow()
    expect(editing.values('a').terminalNumber).toBe('')
    expect(editing.state.undo).toHaveLength(0)
  })
  it('undoes and redoes an entire saved batch through the APIs', async () => {
    const { editing, items, table } = setup()
    editing.apply([{ id: 'a', field: 'terminalNumber', value: '001' }, { id: 'b', field: 'terminalNumber', value: '002' }])
    await editing.flush(); editing.history(); await editing.flush()
    expect(items.map(row => row.terminalNumber)).toEqual(['', ''])
    editing.history(true); await editing.flush()
    expect(items.map(row => row.terminalNumber)).toEqual(['001', '002'])
    expect(table).toHaveBeenCalledTimes(6)
  })
  it('serializes edits to the same row and persists undo requested during save', async () => {
    const { editing, table, items } = setup()
    const gate = deferred()
    table.mockImplementationOnce(async (row, value) => { await gate.promise; row.terminalNumber = value.terminalNumber })
    editing.apply([{ id: 'a', field: 'terminalNumber', value: '001' }])
    await Promise.resolve()
    editing.history()
    expect(table).toHaveBeenCalledTimes(1)
    gate.resolve(); expect(await editing.flush()).toBe(true)
    expect(items[0]!.terminalNumber).toBe('')
    expect(table).toHaveBeenCalledTimes(2)
  })
  it('preserves a newer cable draft when a correction callback arrives', async () => {
    const { editing, cable, items } = setup()
    const gate = deferred()
    cable.mockImplementationOnce(async (row, text) => { await gate.promise; row.corrected = text; editing.syncCorrection(row.id, text) })
    editing.apply([{ id: 'a', field: 'cable', value: 'first' }]); await Promise.resolve()
    editing.apply([{ id: 'a', field: 'cable', value: 'second' }])
    gate.resolve(); await editing.flush()
    expect(items[0]!.corrected).toBe('second')
    expect(editing.values('a').cable).toBe('second')
  })
  it('retains failed edits, saves other rows and retries only after user action', async () => {
    const { editing, table, items } = setup()
    table.mockRejectedValueOnce(new Error('offline'))
    editing.apply([{ id: 'a', field: 'terminalNumber', value: '001' }, { id: 'b', field: 'terminalNumber', value: '002' }])
    expect(await editing.flush()).toBe(false)
    expect(editing.values('a').terminalNumber).toBe('001')
    expect(items[1]!.terminalNumber).toBe('002')
    await editing.flush(); expect(table).toHaveBeenCalledTimes(2)
    editing.retry('a'); expect(await editing.flush()).toBe(true)
  })
  it('does not automatically overwrite a version conflict', async () => {
    const { editing, table } = setup()
    table.mockRejectedValueOnce({ response: { status: 409 } })
    editing.apply([{ id: 'a', field: 'terminalNumber', value: '001' }]); await editing.flush()
    expect(editing.state.status.a).toContain('版本冲突')
    editing.apply([{ id: 'a', field: 'terminalNumber', value: '002' }]); await editing.flush()
    expect(table).toHaveBeenCalledTimes(1)
    editing.retry('a'); await editing.flush(); expect(table).toHaveBeenCalledTimes(2)
  })
  it('limits concurrent rows to four', async () => {
    const { editing, table } = setup(Array.from({ length: 7 }, (_, i) => item(String(i))))
    const gate = deferred(); let active = 0, maximum = 0
    table.mockImplementation(async (row, value) => { active++; maximum = Math.max(maximum, active); await gate.promise; row.terminalNumber = value.terminalNumber; active-- })
    editing.apply(Array.from({ length: 7 }, (_, i) => ({ id: String(i), field: 'terminalNumber', value: '1' })))
    await Promise.resolve(); expect(table).toHaveBeenCalledTimes(4)
    gate.resolve(); await editing.flush(); expect(maximum).toBe(4)
  })
})
