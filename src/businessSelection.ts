import type { TerminalRecord } from './api/terminalDocument'
export function businessSelection(row: Pick<TerminalRecord, 'terminalPointId' | 'sourceResultId' | 'cable' | 'sourceUnavailable'>) {
  return { pointId: row.terminalPointId || '', sourceId: row.cable.trim() && !row.sourceUnavailable ? row.sourceResultId || '' : '' }
}
