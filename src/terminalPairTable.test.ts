import { describe, expect, it } from 'vitest'
import { gridTerminalNumber, orderedTerminalPoints, terminalTableRows } from './terminalPairTable'
import type { OcrItem, TerminalPoint } from './types/ocr'

const line = (id: string, y: number, reviewStatus?: OcrItem['reviewStatus']): OcrItem => ({
  id, text: id, score: 0.95, bbox: [10, y, 40, y + 10], comments: [], reviewStatus,
})
const point = (id: string, y: number): TerminalPoint => ({ id, x: 20, y, source: 'model' })

describe('terminal-pair table rows', () => {
  it('marks surplus OCR lines independently of displayed numbers and blank terminal rows', () => {
    const rows = terminalTableRows([point('p', 1)], [{ ...line('a', 1), terminalNumber: '101' }, line('b', 2)])
    expect(rows[0]).toMatchObject({ hasTerminal: true, hasOcrResult: true, requiresTerminalReview: false, terminalNumber: '101' })
    expect(rows[1]).toMatchObject({ hasTerminal: false, hasOcrResult: true, requiresTerminalReview: true })
    expect(terminalTableRows([point('p', 1)], [])[0]).toMatchObject({ hasTerminal: true, hasOcrResult: false, requiresTerminalReview: false })
  })
  it('uses saved terminal numbers only for matched rows', () => {
    const custom = { ...line('H1', 10), terminalNumber: 'XT-001' }
    expect(terminalTableRows([point('a', 10), point('b', 20)], [custom]).map(row => row.terminalNumber)).toEqual(['XT-001', '2'])
    expect(terminalTableRows([], [custom])[0]!).toMatchObject({ terminalNumber: '', hasTerminal: false, requiresTerminalReview: true })
    custom.terminalNumber = ''
    expect(terminalTableRows([point('a', 10)], [custom])[0]!.terminalNumber).toBe('1')
    expect(gridTerminalNumber({ hasTerminal: false, terminalNumber: '' }, 'OLD-001')).toBe('')
    expect(gridTerminalNumber({ hasTerminal: true, terminalNumber: '1' }, 'XT-001')).toBe('XT-001')
  })
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

  it('matches by nearest vertical position rather than pairing two sorted lists', () => {
    const rows = terminalTableRows([point('a', 100), point('b', 200), point('c', 300)], [
      line('H1', 95), line('H3', 295),
    ])
    expect(rows.map(row => [row.terminalNumber, row.item?.text || ''])).toEqual([
      ['1', 'H1'], ['2', ''], ['3', 'H3'],
    ])
  })

  it('keeps the losing line unnumbered when two lines compete for one point', () => {
    const rows = terminalTableRows([point('a', 100), point('b', 200)], [
      line('far', 110), line('near', 98), line('other', 198),
    ])
    expect(rows.filter(row => row.hasTerminal)).toHaveLength(2)
    expect(rows.find(row => row.terminalNumber === '1')?.item?.id).toBe('near')
    expect(rows.find(row => row.terminalNumber === '2')?.item?.id).toBe('other')
    expect(rows.find(row => row.item?.id === 'far')).toMatchObject({ terminalNumber: '', hasTerminal: false, requiresTerminalReview: true })
  })

  it('falls back to box centers when slanted projections reverse adjacent lines', () => {
    const upper = { ...line('upper', 135), bbox: [100, 135, 200, 155] as OcrItem['bbox'],
      polygon: [[100, 145], [200, 135], [200, 145], [100, 155]] as OcrItem['polygon'] }
    const lower = { ...line('lower', 145), bbox: [100, 145, 200, 165] as OcrItem['bbox'],
      polygon: [[100, 145], [200, 155], [200, 165], [100, 155]] as OcrItem['polygon'] }
    const points = [{ ...point('a', 100), x: 50 }, { ...point('b', 200), x: 50 }]
    expect(terminalTableRows(points, [lower, upper]).filter(row => row.hasTerminal)
      .map(row => [row.terminalNumber, row.item?.id])).toEqual([['1', 'upper'], ['2', 'lower']])
  })

  it('rejects a polygon extrapolation that reaches too far beyond the OCR box', () => {
    const slanted = { ...line('slanted', 150), bbox: [100, 150, 200, 190] as OcrItem['bbox'],
      polygon: [[100, 150], [200, 180], [200, 190], [100, 160]] as OcrItem['polygon'] }
    const points = [{ ...point('a', 100), x: 0 }, { ...point('b', 200), x: 0 }]
    expect(terminalTableRows(points, [slanted]).find(row => row.item?.id === 'slanted')?.terminalNumber).toBe('2')
  })

  it('retains a small slope correction near the boundary between two terminals', () => {
    const slanted = { ...line('slanted', 139), bbox: [100, 139, 200, 159] as OcrItem['bbox'],
      polygon: [[100, 149], [200, 139], [200, 149], [100, 159]] as OcrItem['polygon'] }
    const points = [{ ...point('a', 100), x: 50 }, { ...point('b', 200), x: 50 }]
    expect(terminalTableRows(points, [slanted]).find(row => row.item?.id === 'slanted')?.terminalNumber).toBe('2')
  })
})

it('keeps manually recorded values bound to their terminal and preserves displaced OCR', () => {
  const manual = { ...line('manual', 200), terminalPointId: 'a', corrected: 'C1' }
  const original = line('original', 100)
  const rows = terminalTableRows([point('a', 100), point('b', 200)], [original, manual])
  expect(rows.find(row => row.hasTerminal && row.item?.id === 'manual')?.terminalNumber).toBe('1')
  expect(rows.some(row => !row.hasTerminal && row.item?.id === 'original')).toBe(true)
  expect(rows.find(row => row.terminalNumber === '2')?.item).toBeUndefined()
})
