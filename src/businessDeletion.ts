import type { TerminalRecord } from './api/terminalDocument'

export function selectedBusinessSourceIds(
  records: Pick<TerminalRecord, 'id' | 'sourceResultId'>[],
  selectedIds: string[],
  activeSourceIds: string[],
): string[] {
  const selected = new Set(selectedIds)
  const active = new Set(activeSourceIds)
  return [...new Set(records.filter(row => selected.has(row.id) && row.sourceResultId && active.has(row.sourceResultId))
    .map(row => row.sourceResultId!))]
}
