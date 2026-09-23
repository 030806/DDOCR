import type { Side, TerminalRow } from './api/terminal'

export const TERMINAL_CREATE_PROMPT = '填写名称创建新的端子排任务'
export const terminalViewPositions = new Map<string, { page: number; selectedId: string; zoom: number }>()

export function readPendingSides(taskId: string): Partial<Record<Side, string>> {
  try {
    const value = JSON.parse(sessionStorage.getItem(`terminal.pending.${taskId}`) || '{}')
    return Object.fromEntries(['left', 'right'].filter(side => typeof value?.[side] === 'string').map(side => [side, value[side]]))
  } catch { return {} }
}
export function writePendingSides(taskId: string, value: Partial<Record<Side, string>>) {
  try { sessionStorage.setItem(`terminal.pending.${taskId}`, JSON.stringify(value)) } catch { /* Navigation still works without session storage. */ }
}

export function terminalSidePath(id: string, side: Side, jobId?: string) {
  return `/terminal-tasks/${encodeURIComponent(id)}/${side}${jobId ? `/${encodeURIComponent(jobId)}` : ''}`
}
export function filterTerminalRows(rows: TerminalRow[], filter: string) {
  return rows.filter(row => filter === 'confirmed' ? row.confirmed : filter === 'pending' ? !row.confirmed : true)
}
export function terminalRowStatus(row: TerminalRow) {
  if (row.conflict) return '编号缺失或重复'
  if (!row.left) return '缺左侧'
  if (!row.right) return '缺右侧'
  return row.manual ? '人工对应' : '已匹配'
}
