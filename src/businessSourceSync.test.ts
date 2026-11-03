import { describe, expect, it } from 'vitest'
import { planTableSync } from './businessSourceSync'
import type { TerminalRecord } from './api/terminalDocument'
import type { OcrItem } from './types/ocr'

const row: TerminalRecord = { id: 'row1', terminalPointId: 'p1', sourceResultId: 's1', terminalNumber: '1', cable: 'A1', manualConfirmed: false, tableNote: '', manual: false, sourceRevision: 2 }
const source: OcrItem = { id: 's1', text: 'A1', revision: 2, tableRevision: 3, score: 1, bbox: [0, 0, 10, 10], comments: [] }
describe('table source synchronization', () => {
  it('sends only changed fields with both concurrency revisions', () => {
    const plan = planTableSync([row], [{ ...row, cable: 'A2' }], [source])
    expect(plan.updates).toEqual([{ result_id: 's1', base_revision: 2, base_table_revision: 3, text: 'A2' }])
    expect(planTableSync([row], [{ ...row, terminalNumber: 'XT-1' }], [source]).updates[0]).toMatchObject({ terminal_number: 'XT-1' })
    expect(source.text).toBe('A1')
  })
  it('identifies shared sources and rejects conflicting batch edits', () => {
    const rows = [row, { ...row, id: 'row2' }]
    expect(planTableSync(rows, [{ ...row, cable: 'A2' }, rows[1]!], [source]).shared.has('s1')).toBe(true)
    expect(() => planTableSync(rows, rows.map((r, i) => ({ ...r, cable: `B${i}` })), [source])).toThrow('冲突')
  })
  it('skips unavailable sources without affecting unrelated edits', () => {
    expect(planTableSync([row], [{ ...row, cable: 'A2' }], []).skipped).toBe(1)
    expect(planTableSync([row], [{ ...row, cable: 'A2' }], [{ ...source, reviewStatus: 'deleted' }]).updates).toEqual([])
    expect(planTableSync([row], [{ ...row, tableNote: 'note' }], []).skipped).toBe(0)
  })
  it('leaves source reassignment to the clipboard save path', () => {
    expect(planTableSync([row], [{ ...row, cable: '', sourceResultId: null }], [source]).updates).toEqual([])
  })
})
