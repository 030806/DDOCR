import { expect, it } from 'vitest'
import type { TerminalRecord } from './api/terminalDocument'
import type { OcrItem, TerminalPoint } from './types/ocr'
import { businessTableRows } from './businessTableRows'

const point = (id: string, y: number): TerminalPoint => ({id,x:10,y,source:'model'})
const source = (id: string, y: number): OcrItem => ({id,text:id,score:1,bbox:[50,y,80,y+10],comments:[]})
const row = (id: string, pointId: string | null, sourceId: string | null): TerminalRecord => ({
  id, terminalPointId:pointId, sourceResultId:sourceId, terminalNumber:pointId || '',
  cable:sourceId || '', manualConfirmed:false, tableNote:'', manual:false, sourceRevision:0,
})

it('keeps sequence and terminal rows fixed when a source moves to another terminal', () => {
  const points=[point('p1',100),point('p2',200),point('p3',300)]
  const items=[source('A',100),source('B',200),source('C',300)]
  const initial=[row('terminal:p3','p3','C'),row('terminal:p1','p1','A'),row('terminal:p2','p2','B')]
  expect(businessTableRows(initial,points,items).map(r=>[r.id,r.cable?.sourceResultId])).toEqual([
    ['terminal:p1','A'],['terminal:p2','B'],['terminal:p3','C'],
  ])
  const changed=[row('terminal:p3','p3','B'),row('terminal:p1','p1',null),row('terminal:p2','p2','A'),row('ocr:C',null,'C')]
  expect(businessTableRows(changed,points,items).map(r=>[r.id,r.cable?.sourceResultId])).toEqual([
    ['terminal:p1',undefined],['terminal:p2','A'],['terminal:p3','B'],['ocr:C','C'],
  ])
})
