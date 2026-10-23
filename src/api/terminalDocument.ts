import { apiClient } from './client'
export type TerminalRecord = { id: string; terminalPointId: string | null; sourceResultId: string | null; terminalNumber: string; cable: string; manualConfirmed: boolean; tableNote: string; manual: boolean; sourceRevision: number; sourceChanged?: boolean; sourceUnavailable?: boolean; orphaned?: boolean; sourceText?: string; currentSourceRevision?: number }
export type TerminalDocument = { revision: number; records: TerminalRecord[] }
export type SourceChange = { result_id: string; base_revision: number; text: string }
export async function loadTerminalDocument(job: string, page: number): Promise<TerminalDocument> {
  return (await apiClient.get(`/ocr/jobs/${job}/pages/${page}/terminal-document`)).data.data
}
export async function saveTerminalDocument(job: string, page: number, document: TerminalDocument, source?: SourceChange, syncRecordId?: string) {
  return (await apiClient.put(`/ocr/jobs/${job}/pages/${page}/terminal-document`, { base_revision: document.revision, records: document.records, source, sync_record_id: syncRecordId })).data.data as TerminalDocument & { correction?: { corrected_text: string; revision: number } }
}
