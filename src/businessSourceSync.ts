import type { SourceUpdate, TerminalRecord } from './api/terminalDocument'
import type { OcrItem } from './types/ocr'

// Plan only direct cell edits. Source reassignment remains a clipboard operation.
export function planTableSync(before: TerminalRecord[], after: TerminalRecord[], items: OcrItem[]) {
  const previous = new Map(before.map(row => [row.id, row]))
  const sources = new Map(items.map(item => [item.id, item]))
  const updates = new Map<string, SourceUpdate>()
  const shared = new Set<string>()
  let skipped = 0
  for (const row of after) {
    const old = previous.get(row.id)
    if (!old || old.sourceResultId !== row.sourceResultId) continue
    const cableChanged = old.cable !== row.cable
    const numberChanged = old.terminalNumber !== row.terminalNumber
    if (!cableChanged && !numberChanged) continue
    const source = row.sourceResultId ? sources.get(row.sourceResultId) : undefined
    if (!source || row.sourceUnavailable || source.reviewStatus === 'deleted' || source.reviewStatus === 'false_positive') {
      skipped++
      continue
    }
    const update = updates.get(source.id) ?? {
      result_id: source.id, base_revision: source.revision ?? 0, base_table_revision: source.tableRevision ?? 0,
    }
    for (const [field, changed, value] of [
      ['text', cableChanged, row.cable], ['terminal_number', numberChanged, row.terminalNumber],
    ] as const) {
      if (!changed) continue
      if (update[field] !== undefined && update[field] !== value) throw new Error('同一 OCR 来源存在冲突的表格修改，请分别核对')
      update[field] = value
    }
    updates.set(source.id, update)
    if (after.filter(candidate => candidate.sourceResultId === source.id).length > 1) shared.add(source.id)
  }
  return { updates: [...updates.values()], shared, skipped }
}
