import { expect, it } from 'vitest'
import { transferBusinessRows } from './businessClipboard'
import type { TerminalRecord } from './api/terminalDocument'
const row = (id: string, cable: string, sourceResultId: string | null): TerminalRecord => ({ id, cable, sourceResultId, terminalPointId: id, sourceRevision: 0, terminalNumber: id, manualConfirmed: true, tableNote: '', manual: true })
it('moves an overlapping range upward with source identity, clearing only the trailing slot', () => {
 const rows=[row('7','',null),row('8','A','ocrA'),row('9','B','ocrB')]
 const next=transferBusinessRows(rows,{scope:'p',cut:true,rows:rows.slice(1)},['7','8'])
 expect(next.map(r=>[r.cable,r.sourceResultId])).toEqual([['A','ocrA'],['B','ocrB'],['',null]])
 expect(next.map(r=>r.terminalPointId)).toEqual(['7','8','9'])
 expect(next.every(r=>!r.manualConfirmed)).toBe(true)
 expect(rows[1]!.cable).toBe('A')
})
it('copies provenance without changing the source row',()=>{
 const rows=[row('7','',null),row('8','A','ocrA')]
 const next=transferBusinessRows(rows,{scope:'p',cut:false,rows:[rows[1]!]},['7'])
 expect(next[0]!.sourceResultId).toBe('ocrA')
 expect(next[1]).toEqual(rows[1])
})
it('rejects a changed cut source before applying any changes',()=>{
 const rows=[row('7','',null),row('8','A','ocrA')]
 expect(()=>transferBusinessRows(rows,{scope:'p',cut:true,rows:[{...rows[1]!,cable:'OLD'}]},['7'])).toThrow('来源已变化')
 expect(rows[0]!.cable).toBe('')
})
