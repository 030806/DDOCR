import type { TerminalRecord } from './api/terminalDocument'
import type { OcrItem, TerminalPoint } from './types/ocr'

export type BusinessDisplayRow = {
  id: string
  terminal?: TerminalRecord
  cable?: TerminalRecord
  matched: boolean
}

export function businessTableRows(records: TerminalRecord[], points: TerminalPoint[] = [], items: OcrItem[] = []): BusinessDisplayRow[] {
  const visible = records.filter(row => !row.orphaned)
  const pointOrder = new Map([...points].sort((a,b)=>a.y-b.y || a.x-b.x || a.id.localeCompare(b.id)).map((point,index)=>[point.id,index]))
  const terminals = visible.filter(row=>row.terminalPointId).sort((a,b)=>(pointOrder.get(a.terminalPointId!) ?? Number.MAX_SAFE_INTEGER)-(pointOrder.get(b.terminalPointId!) ?? Number.MAX_SAFE_INTEGER))
  const sourceOrder = new Map(items.map(item=>[item.id,item]))
  const sources = visible.filter(row=>!row.terminalPointId && row.sourceResultId).sort((a,b)=>{
    const left=sourceOrder.get(a.sourceResultId!), right=sourceOrder.get(b.sourceResultId!)
    return ((left?.bbox[1] || 0)+(left?.bbox[3] || 0))-((right?.bbox[1] || 0)+(right?.bbox[3] || 0)) ||
      ((left?.bbox[0] || 0)+(left?.bbox[2] || 0))-((right?.bbox[0] || 0)+(right?.bbox[2] || 0))
  })
  return [
    ...terminals.map(row=>({id:row.id,terminal:row,cable:row.sourceResultId || row.cable ? row : undefined,matched:!!row.sourceResultId})),
    ...sources.map(row=>({id:row.id,cable:row,matched:false})),
  ]
}
