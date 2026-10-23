import { apiClient } from './client'

export type Side = 'left' | 'right'
export type TerminalSource = {
  id: string; job_id: string; page_no: number; terminal_number: string; text: string
}
export type TerminalRow = {
  id: string; terminal_number: string; left: TerminalSource | null; right: TerminalSource | null
  confirmed: boolean; conflict: boolean; manual: boolean; note: string; fingerprint: string
}
export type TerminalTask = {
  id: string; name: string; revision: number; version: string; created_at: string
  sides: Partial<Record<Side, { job_id: string; page_no: number; status: string; name: string }>>
  rows: TerminalRow[]
}
export type TerminalSummary = Omit<TerminalTask, 'rows' | 'version'> & {
  row_count: number; confirmed_count: number; conflict_count: number
}
type Envelope<T> = { data: T }
const base = '/terminal-tasks'
const headers = () => ({ 'Idempotency-Key': crypto.randomUUID() })
export const versionOf = (task: TerminalTask) => ({ base_revision: task.revision, version: task.version })
export async function listTerminalTasks(offset = 0) {
  return (await apiClient.get<Envelope<{ items: TerminalSummary[]; next_offset: number | null }>>(base, { params: { offset } })).data.data
}
export async function createTerminalTask(name: string, key: string) {
  return (await apiClient.post<Envelope<TerminalTask>>(base, { name }, { headers: { 'Idempotency-Key': key } })).data.data
}
export async function getTerminalTask(id: string) {
  return (await apiClient.get<Envelope<TerminalTask>>(`${base}/${id}`)).data.data
}
export async function deleteTerminalTask(task: Pick<TerminalSummary, 'id' | 'revision'>) {
  await apiClient.delete(`${base}/${task.id}`, { headers: { 'If-Match': `"${task.revision}"` } })
}
export async function associateSide(task: TerminalTask, side: Side, jobId: string, pageNo: number) {
  return (await apiClient.put<Envelope<TerminalTask>>(`${base}/${task.id}/sides/${side}`,
    { job_id: jobId, page_no: pageNo, base_revision: task.revision }, { headers: headers() })).data.data
}
export async function reviewTerminalRows(task: TerminalTask, rows: Array<Pick<TerminalRow, 'id' | 'confirmed' | 'note'>>) {
  return (await apiClient.patch<Envelope<TerminalTask>>(`${base}/${task.id}/rows`, { ...versionOf(task), rows }, { headers: headers() })).data.data
}
export async function linkTerminalRows(task: TerminalTask, left: string | null, right: string | null) {
  return (await apiClient.post<Envelope<TerminalTask>>(`${base}/${task.id}/links`, { ...versionOf(task), left, right }, { headers: headers() })).data.data
}
export async function exportTerminalTask(task: TerminalTask, scope: 'all' | 'confirmed') {
  const result = (await apiClient.post<Envelope<{ download_url: string }>>(`${base}/${task.id}/exports`,
    { ...versionOf(task), scope }, { headers: headers() })).data.data
  const blob = (await apiClient.get<Blob>(result.download_url.replace(/^\/api\/v1/, ''), { responseType: 'blob' })).data
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${task.name.replace(/[\\/:*?"<>|]/g, '_')}_端子排结果.xlsx`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
