import { reactive } from 'vue'
import type { OcrItem } from './types/ocr'

export const gridFields = ['terminalNumber', 'cable', 'manualConfirmed', 'tableNote'] as const
export type GridField = typeof gridFields[number]
export type GridValues = Record<Exclude<GridField, 'manualConfirmed'>, string> & { manualConfirmed: boolean }
export type GridChange = { id: string; field: GridField; value: string | boolean; clearSource?: boolean }
type Change = GridChange & { before: string | boolean }
export const itemValues = (item: OcrItem): GridValues => ({ terminalNumber: item.terminalNumber || '', cable: item.corrected ?? item.text, manualConfirmed: !!item.manualConfirmed, tableNote: item.tableNote || '' })

export function parseGridClipboard(text: string): string[][] {
  const rows: string[][] = [[]]
  let value = '', quoted = false
  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    if (char === '"' && (quoted || !value)) {
      if (quoted && text[i + 1] === '"') { value += '"'; i++ } else quoted = !quoted
    } else if (!quoted && (char === '\t' || char === '\n' || char === '\r')) {
      rows[rows.length - 1]!.push(value); value = ''
      if (char !== '\t') { if (char === '\r' && text[i + 1] === '\n') i++; rows.push([]) }
    } else value += char
  }
  if (quoted) throw new Error('剪贴板包含未闭合的引号')
  if (value || rows[rows.length - 1]!.length || rows.length === 1) rows[rows.length - 1]!.push(value)
  else rows.pop()
  return rows
}

export function normalizeGridValue(field: GridField, value: unknown): string | boolean {
  if (field === 'manualConfirmed') {
    if (typeof value === 'boolean') return value
    const text = String(value).trim().toLowerCase()
    if (['true', '1', '是', '已确认'].includes(text)) return true
    if (['false', '0', '否', '', '未确认'].includes(text)) return false
    throw new Error('人工确认请填写 是/否、true/false 或 1/0')
  }
  const text = String(value ?? '').trim()
  if (text.length > (field === 'tableNote' ? 1000 : 500)) throw new Error('输入超过字段长度限制')
  return text
}

export function sequentialNumbers(ids: string[], values: (id: string) => string, options: { start: number; step: number; width: number; prefix: string; suffix: string; overwrite: boolean }): GridChange[] {
  if (!Number.isSafeInteger(options.start) || options.start < 0 || !Number.isSafeInteger(options.step) || options.step <= 0 || !Number.isInteger(options.width) || options.width < 1 || options.width > 20) throw new Error('请填写非负整数起始值、正整数步长和位数（1–20）')
  let offset = 0
  return ids.flatMap(id => {
    if (!options.overwrite && values(id).trim()) return []
    const number = options.start + offset++ * options.step
    if (!Number.isSafeInteger(number)) throw new Error('编号超出安全整数范围')
    return [{ id, field: 'terminalNumber' as const, value: normalizeGridValue('terminalNumber', `${options.prefix}${String(number).padStart(options.width, '0')}${options.suffix}`) }]
  })
}

export function createGridEditing(getItems: () => OcrItem[], saveTable: (item: OcrItem, values: GridValues) => Promise<void>, saveCable: (item: OcrItem, text: string) => Promise<void>, validateChange?: (change: GridChange) => void) {
  const state = reactive({ drafts: {} as Record<string, GridValues>, status: {} as Record<string, string>, undo: [] as Change[][], redo: [] as Change[][], revision: 0 })
  const find = (id: string) => getItems().find(item => item.id === id)
  const values = (id: string) => state.drafts[id] ||= itemValues(find(id)!)
  const queue = new Set<string>()
  const blocked = new Set<string>()
  const running = new Map<string, Promise<void>>()
  let active = 0
  const pending = () => {
    void state.revision
    return getItems().some(item => state.drafts[item.id] && gridFields.some(field => values(item.id)[field] !== itemValues(item)[field])) || queue.size > 0 || active > 0 || Object.values(state.status).some(s => s.startsWith('保存失败') || s.startsWith('版本冲突'))
  }
  async function persist(id: string) {
    const item = find(id)
    if (!item) return
    const submitted = { ...values(id) }
    try {
      if (submitted.cable !== itemValues(item).cable) await saveCable(item, submitted.cable)
      // The table fields share one versioned endpoint; keep this request's snapshot consistent.
      if (['terminalNumber', 'manualConfirmed', 'tableNote'].some(field => submitted[field as GridField] !== itemValues(item)[field as GridField])) await saveTable(item, submitted)
      state.status[id] = '已保存'
      if (gridFields.some(field => values(id)[field] !== itemValues(item)[field])) queue.add(id)
    } catch (error) {
      const conflict = (error as { response?: { status?: number } })?.response?.status === 409
      blocked.add(id)
      state.status[id] = conflict ? '版本冲突：请核对服务器值后重试' : '保存失败：输入已保留，可重试'
    } finally { state.revision++ }
  }
  function pump() {
    for (const id of queue) {
      if (active >= 4) break
      if (running.has(id) || blocked.has(id)) continue
      queue.delete(id); active++; state.status[id] = '保存中'
      const operation = persist(id).finally(() => { active--; running.delete(id); pump() })
      running.set(id, operation)
    }
  }
  function apply(changes: GridChange[], record = true) {
    const normalized = changes.map(change => {
      validateChange?.(change)
      if (!find(change.id)) throw new Error('目标识别结果不存在')
      return { ...change, value: normalizeGridValue(change.field, change.value), before: values(change.id)[change.field] }
    }).filter(change => change.value !== change.before)
    for (const change of normalized) {
      Object.assign(values(change.id), { [change.field]: change.value })
      if (!blocked.has(change.id)) { queue.add(change.id); state.status[change.id] = '待保存' }
    }
    if (normalized.length && record) { state.undo.push(normalized); state.redo = [] }
    state.revision++
    // Batch synchronous edits before starting network requests.
    void Promise.resolve().then(pump)
  }
  async function flush() {
    pump()
    while (running.size) { await Promise.all([...running.values()]); pump() }
    return !pending()
  }
  function retry(id: string) { blocked.delete(id); queue.add(id); pump() }
  function history(redo = false) {
    const source = redo ? state.redo : state.undo
    const changes = source[source.length - 1]
    if (!changes) return
    apply(changes.map(c => ({ id: c.id, field: c.field, value: redo ? c.value : c.before })), false)
    source.pop()
    ;(redo ? state.undo : state.redo).push(changes)
  }
  function syncCorrection(id: string, text: string) {
    // A save callback also calls this method. Preserve any newer draft while requests run.
    if (running.has(id) || queue.has(id) || blocked.has(id)) return
    if (state.drafts[id]) state.drafts[id]!.cable = text
    state.revision++
  }
  function reset() { state.drafts = {}; state.status = {}; state.undo = []; state.redo = []; blocked.clear(); queue.clear(); state.revision++ }
  return { state, values, apply, flush, pending, retry, history, syncCorrection, reset }
}
