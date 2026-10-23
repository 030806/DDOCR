import type { TerminalRecord } from './api/terminalDocument'
export const BUSINESS_CLIPBOARD = 'application/x-ddocr-terminal-cells'
export type BusinessClipboard = { scope: string; cut: boolean; rows: { id: string; cable: string; sourceResultId: string | null; sourceRevision: number }[] }
export function transferBusinessRows(records: TerminalRecord[], payload: BusinessClipboard, targets: string[]): TerminalRecord[] {
  if (targets.length !== payload.rows.length || new Set(targets).size !== targets.length) throw new Error('粘贴范围无效')
  const next = records.map(r => ({ ...r }))
  if (payload.cut) {
    for (const source of payload.rows) {
      const current = records.find(r => r.id === source.id)
      if (!current || current.cable !== source.cable || current.sourceResultId !== source.sourceResultId || current.sourceRevision !== source.sourceRevision) throw new Error('剪切来源已变化，请重新剪切')
      Object.assign(next.find(r => r.id === source.id)!, { cable: '', sourceResultId: null, sourceRevision: 0, manualConfirmed: false, manual: true })
    }
  }
  targets.forEach((id, index) => {
    const target = next.find(r => r.id === id), source = payload.rows[index]!
    if (!target) throw new Error('目标行不存在')
    Object.assign(target, { cable: source.cable, sourceResultId: source.sourceResultId, sourceRevision: source.sourceRevision, manualConfirmed: false, manual: true })
  })
  return next
}
