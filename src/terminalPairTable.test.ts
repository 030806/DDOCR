import { describe, expect, it } from 'vitest'
import { orderedTerminalPoints, terminalTableRows } from './terminalPairTable'
import type { OcrItem, TerminalPoint } from './types/ocr'

const line = (id: string, y: number, reviewStatus?: OcrItem['reviewStatus']): OcrItem => ({
  id, text: id, score: 0.95, bbox: [10, y, 40, y + 10], comments: [], reviewStatus,
})
const point = (id: string, y: number): TerminalPoint => ({ id, x: 20, y, source: 'model' })

describe('terminal-pair table rows', () => {
  it('keeps blank line cells when the detector finds more terminals', () => {
    const rows = terminalTableRows([point('b', 200), point('a', 100), point('c', 300)], [line('H1', 10)])
    expect(rows.map(row => [row.terminalNumber, row.item?.text || ''])).toEqual([
      ['1', 'H1'], ['2', ''], ['3', ''],
    ])
    expect(orderedTerminalPoints([point('b', 200), point('a', 100)]).map(item => item.id)).toEqual(['a', 'b'])
    expect(rows.map(row => row.selectionId)).toEqual(['H1', 'terminal:b', 'terminal:c'])
  })

  it('keeps every OCR line and blanks surplus terminal numbers', () => {
    const rows = terminalTableRows([point('a', 100)], [
      line('J2', 200), line('ignored', 150, 'false_positive'), line('J1', 100), line('J3', 300),
    ])
    expect(rows.map(row => [row.terminalNumber, row.item?.text || ''])).toEqual([
      ['1', 'J1'], ['', 'J2'], ['', 'J3'],
    ])
  })

  it('reorders after a line box moves or a terminal point is added', () => {
    const rows = terminalTableRows([point('a', 100), point('manual', 250)], [
      line('H2', 200), line('H1', 10),
    ])
    expect(rows.map(row => [row.terminalNumber, row.item?.text])).toEqual([
      ['1', 'H1'], ['2', 'H2'],
    ])
  })

  it('gives every terminal-only row a stable selection identity', () => {
    const points = [point('b', 200), point('a', 100)]
    const rows = terminalTableRows(points, [])
    expect(rows.map(row => row.selectionId)).toEqual(['terminal:a', 'terminal:b'])
    expect(new Set(rows.map(row => row.selectionId)).size).toBe(rows.length)
    expect(terminalTableRows([point('new', 50), ...points], []).map(row => row.selectionId))
      .toEqual(['terminal:new', 'terminal:a', 'terminal:b'])
  })
})
