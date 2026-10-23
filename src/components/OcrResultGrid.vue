<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { TabulatorFull as Tabulator, type CellComponent, type ColumnDefinition } from 'tabulator-tables'
import 'tabulator-tables/dist/css/tabulator.min.css'
import type { OcrItem } from '../types/ocr'
import { gridTerminalNumber } from '../terminalPairTable'
import { gridFields, normalizeGridValue, parseGridClipboard, sequentialNumbers, type GridChange, type GridField, type GridValues } from '../ocrGridEditing'

type GridRow = GridValues & { id: string; index: number; item?: OcrItem; status: string; selected: boolean; hasTerminal: boolean; requiresTerminalReview: boolean }
const props = defineProps<{
  rows: { selectionId: string; terminalNumber: string; item?: OcrItem; hasTerminal: boolean; requiresTerminalReview: boolean }[]
  terminalCount?: number
  modelTerminalCount?: number | null
  editingDisabled?: boolean
  selectedId: string
  selectedIds: string[]
  values: (id: string) => GridValues
  statuses: Record<string, string>
  revision: number
  canUndo: boolean
  canRedo: boolean
}>()
const emit = defineEmits<{
  change: [changes: GridChange[]]
  select: [id: string]
  selection: [ids: string[]]
  undo: []
  redo: []
  retry: [id: string]
}>()
const host = ref<HTMLDivElement>()
const expanded = ref(false)
const feedback = ref('')
const numberDialog = ref(false)
type NumberTarget = { rowKey: string; id?: string; index: number; before: string; hasTerminal: boolean; requiresTerminalReview: boolean }
const numberRangeIds = ref<string[]>([])
const numberTargets = ref<NumberTarget[]>([])
const numberSource = ref<'range' | 'rows'>('rows')
const start = ref(1), step = ref(1), width = ref(1), prefix = ref(''), suffix = ref(''), overwrite = ref(false)
let table: Tabulator | undefined
let built = false
let anchorId = ''
let syncing = false
let activeCell: CellComponent | undefined
let selectionDragStart: { x: number; y: number; select: boolean; field: 'selected' | 'manualConfirmed' } | undefined
function selectionMouseDown(event: MouseEvent) {
  const cell = (event.target as HTMLElement).closest('[tabulator-field="selected"], [tabulator-field="manualConfirmed"]')
  const row = cell && table?.getRows('active').find(row => row.getElement() === cell.closest('.tabulator-row'))
  const field = cell?.getAttribute('tabulator-field') as 'selected' | 'manualConfirmed' | undefined
  const allowed = field === 'selected' || (row && editable(row.getCell('manualConfirmed')))
  selectionDragStart = event.button === 0 && row && field && allowed
    ? { x: event.clientX, y: event.clientY, field, select: field === 'selected' ? !props.selectedIds.includes(String(row.getIndex())) : !row.getData().manualConfirmed }
    : undefined
}
function selectionMouseUp(event: MouseEvent) {
  const start = selectionDragStart
  selectionDragStart = undefined
  if (!start || Math.abs(event.clientX - start.x) + Math.abs(event.clientY - start.y) < 4) return
  const cells = rangeCells()
  if (cells.length < 2 || cells.some(row => row.length !== 1 || row[0]!.getField() !== start.field)) return
  if (start.field === 'manualConfirmed') {
    const changes: GridChange[] = []; let skipped = 0
    for (const [cell] of cells) {
      if (!cell || !editable(cell)) { skipped++; continue }
      const row = cell.getRow().getData() as GridRow
      changes.push({ id: row.item!.id, field: 'manualConfirmed', value: start.select })
    }
    submit(changes, skipped)
    return
  }
  const ids = cells.map(row => String(row[0]!.getRow().getIndex()))
  emit('selection', start.select
    ? [...new Set([...props.selectedIds, ...ids])]
    : props.selectedIds.filter(id => !ids.includes(id)))
}
function syncNumberRange() {
  const cells = rangeCells()
  numberRangeIds.value = cells.length && cells.every(row => row.length === 1 && row[0]!.getField() === 'terminalNumber')
    ? cells.map(row => String(row[0]!.getRow().getIndex())) : []
}
function scheduleNumberRange() { void nextTick(() => { if (built) syncNumberRange() }) }
function openNumberDialog() {
  syncNumberRange()
  numberSource.value = numberRangeIds.value.length ? 'range' : 'rows'
  const ids = numberSource.value === 'range' ? numberRangeIds.value : props.selectedIds
  numberTargets.value = (table?.getRows('active') || []).map(row => row.getData() as GridRow).filter(row => ids.includes(row.id))
    .map(row => ({ rowKey: row.id, id: row.item?.id, index: row.index, before: row.terminalNumber, hasTerminal: row.hasTerminal, requiresTerminalReview: row.requiresTerminalReview }))
  numberDialog.value = true
}
const numberPlan = computed(() => {
  void props.revision
  try {
    const changes = sequentialNumbers(numberTargets.value.flatMap(row => row.id && row.hasTerminal ? [row.id] : []), id => props.values(id).terminalNumber, { start: start.value, step: step.value, width: width.value, prefix: prefix.value, suffix: suffix.value, overwrite: overwrite.value })
    return { changes, error: '' }
  } catch (error) { return { changes: [] as GridChange[], error: (error as Error).message } }
})
const preview = computed(() => numberPlan.value.changes)
const previewRows = computed(() => numberTargets.value.map(row => {
  const change = preview.value.find(change => change.id === row.id)
  return { ...row, after: change ? String(change.value) : row.before, action: row.requiresTerminalReview ? '跳过：待核对端子，请先核对或补点' : !row.id ? '跳过：只读行' : numberPlan.value.error ? '参数无效' : !change ? '跳过：已有编号' : change.value === row.before ? '保持原值' : '填写编号' }
}))
function rowData(): GridRow[] {
  return props.rows.map((row, index) => ({
    ...(row.item ? props.values(row.item.id) : { terminalNumber: '', cable: '', manualConfirmed: false, tableNote: '' }),
    // A saved number from an older positional match must not create an extra numbered row.
    terminalNumber: gridTerminalNumber(row, row.item ? props.values(row.item.id).terminalNumber : ''),
    id: row.selectionId, item: row.item, index: index + 1, status: props.statuses[row.item?.id || ''] || '已保存', selected: props.selectedIds.includes(row.selectionId),
    hasTerminal: row.hasTerminal, requiresTerminalReview: row.requiresTerminalReview,
  }))
}
function editable(cell: CellComponent) {
  const row = cell.getRow().getData() as GridRow
  return !props.editingDisabled && !!row.item && (cell.getField() !== 'terminalNumber' || row.hasTerminal)
}
function submit(changes: GridChange[], skipped = 0) {
  try {
    if (props.editingDisabled) throw new Error('请先保存或退出端子点编辑，再修改表格')
    changes.forEach(c => normalizeGridValue(c.field, c.value))
    emit('change', changes)
    feedback.value = `已应用 ${changes.length} 个单元格${skipped ? `，跳过 ${skipped} 个只读单元格` : ''}`
  } catch (error) { feedback.value = (error as Error).message; refresh() }
}
// Tabulator 6.3 returns a matrix here; @types still declares a flat array.
function rangeCells(): CellComponent[][] { return (table?.getRanges()[0]?.getCells() as unknown as CellComponent[][]) || (activeCell ? [[activeCell]] : []) }
function paste(event: ClipboardEvent) {
  if ((event.target as HTMLElement).closest('input,textarea,[contenteditable=true]')) return
  event.preventDefault(); event.stopImmediatePropagation()
  try {
    const matrix = parseGridClipboard(event.clipboardData?.getData('text/plain') || '')
    const first = rangeCells()[0]?.[0]
    if (!first || !table) throw new Error('请先选择粘贴起点')
    const rows = table.getRows('active'), columns = table.getColumns()
    const r = rows.indexOf(first.getRow()), c = columns.indexOf(first.getColumn())
    if (r + matrix.length > rows.length || c + Math.max(...matrix.map(row => row.length)) > columns.length) throw new Error('粘贴超出表格范围，未应用任何修改')
    const changes: GridChange[] = []; let skipped = 0
    matrix.forEach((line, y) => line.forEach((value, x) => {
      const cell = rows[r + y]!.getCell(columns[c + x]!.getField())
      if (!cell || !gridFields.includes(cell.getField() as GridField) || !editable(cell)) { skipped++; return }
      const row = cell.getRow().getData() as GridRow
      changes.push({ id: row.item!.id, field: cell.getField() as GridField, value: normalizeGridValue(cell.getField() as GridField, value) })
    }))
    submit(changes, skipped)
  } catch (error) { feedback.value = (error as Error).message }
}
function copy(event: ClipboardEvent) {
  if ((event.target as HTMLElement).closest('input,textarea,[contenteditable=true]')) return
  const cells = rangeCells()
  if (!cells.length) return
  event.preventDefault(); event.stopImmediatePropagation()
  const escape = (value: unknown) => {
    const text = String(value ?? '')
    return /[\t\r\n"]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }
  event.clipboardData?.setData('text/plain', cells.map(row => row.map(cell => escape(cell.getValue())).join('\t')).join('\r\n'))
}
function fillDown() {
  const cells = rangeCells(), changes: GridChange[] = []; let skipped = 0
  if (cells.length < 2) { feedback.value = '请选择至少两行单元格，以第一行向下填充'; return }
  cells.slice(1).forEach(row => row.forEach((cell, index) => {
    if (!gridFields.includes(cell.getField() as GridField) || !editable(cell)) { skipped++; return }
    changes.push({ id: (cell.getRow().getData() as GridRow).item!.id, field: cell.getField() as GridField, value: cells[0]![index]!.getValue() })
  }))
  submit(changes, skipped)
}
function numberRows() {
  try {
    if (props.editingDisabled) throw new Error('请先保存或退出端子点编辑，再编号')
    if (numberPlan.value.error) throw new Error(numberPlan.value.error)
    // Apply the reviewed snapshot, not a fresh selection that could change while the dialog is open.
    submit(preview.value); numberDialog.value = false
  } catch (error) { feedback.value = (error as Error).message }
}
function keydown(event: KeyboardEvent) {
  if (event.isComposing) return
  const editing = !!(event.target as HTMLElement).closest('input,textarea,[contenteditable=true]')
  if (event.key === 'Escape' && expanded.value && !editing) { expanded.value = false; return }
  if ((event.ctrlKey || event.metaKey) && !editing) {
    if (event.key.toLowerCase() === 'z') { event.preventDefault(); event.stopImmediatePropagation(); event.shiftKey ? emit('redo') : emit('undo'); return }
    if (event.key.toLowerCase() === 'y') { event.preventDefault(); emit('redo'); return }
    if (event.key.toLowerCase() === 'd') { event.preventDefault(); fillDown(); return }
  }
  const focusedCell = table?.getRows('active').flatMap(row => row.getCells()).find(cell => cell.getElement() === document.activeElement) || activeCell
  if (!editing && focusedCell && (event.key === 'Tab' || event.key === 'Enter')) {
    event.preventDefault(); event.stopImmediatePropagation()
    navigate(focusedCell, event.key, event.shiftKey)
  }
}
function navigate(cell: CellComponent, key: string, reverse: boolean) {
  if (!table) return
  const rows = table.getRows('active'), columns = table.getColumns().filter(col => gridFields.includes(col.getField() as GridField))
  let r = rows.indexOf(cell.getRow()), c = columns.indexOf(cell.getColumn())
  const direction = reverse ? -1 : 1
  if (key === 'Enter') r += direction
  else { c += direction; if (c >= columns.length) { c = 0; r++ } if (c < 0) { c = columns.length - 1; r-- } }
  const target = rows[r]?.getCell(columns[c]?.getField() || '')
  if (target) {
    activeCell = target
    const range = table.getRanges()[0]
    if (range) range.setBounds(target, target)
    else table.addRange(target, target)
    target.getElement().focus()
    // Let the committing editor and range focus handlers finish before opening the next editor.
    setTimeout(() => { if (built && editable(target)) target.edit() }, 0)
  }
}
function textEditor(cell: CellComponent, onRendered: (cb: () => void) => void, success: (value: string) => void, cancel: (value: unknown) => void) {
  const input = document.createElement('input')
  input.type = 'text'; input.value = String(cell.getValue() ?? ''); input.maxLength = cell.getField() === 'tableNote' ? 1000 : 500
  input.setAttribute('aria-label', `${cell.getColumn().getDefinition().title}编辑`)
  input.style.cssText = 'width:100%;height:100%;box-sizing:border-box'
  let completed = false, composing = false
  const commit = () => {
    if (completed) return
    completed = true
    try { success(normalizeGridValue(cell.getField() as GridField, input.value) as string) }
    catch (error) { feedback.value = (error as Error).message; cancel(undefined) }
  }
  input.addEventListener('compositionstart', () => { composing = true })
  input.addEventListener('compositionend', () => { composing = false })
  input.addEventListener('blur', commit)
  input.addEventListener('keydown', event => {
    if (composing || event.isComposing) return
    if (event.key === 'Escape') { completed = true; cancel(undefined); event.stopPropagation() }
    if (event.key === 'Tab' || event.key === 'Enter') { event.preventDefault(); event.stopPropagation(); commit(); navigate(cell, event.key, event.shiftKey) }
  })
  onRendered(() => { input.focus(); input.select() })
  return input
}
function refresh() {
  if (!built || !table) return
  syncing = true
  const data = rowData(), ids = table.getRows().map(row => row.getIndex())
  // Update existing rows in place to preserve selection, sorting and any active editor.
  const same = ids.length === data.length && data.every(row => ids.includes(row.id))
  if (same) {
    const orderChanged = data.some((row, index) => ids[index] !== row.id)
    for (const row of data) {
      const existing = table.getRow(row.id)
      if (existing) {
        const patch: Partial<GridRow> = {}
        for (const key of ['terminalNumber', 'cable', 'manualConfirmed', 'tableNote', 'status', 'selected', 'index', 'hasTerminal', 'requiresTerminalReview'] as const) if (existing.getData()[key] !== row[key]) Object.assign(patch, { [key]: row[key] })
        if (Object.keys(patch).length) void existing.update(patch)
        if ('requiresTerminalReview' in patch) {
          const cell = existing.getCell('terminalNumber')
          if (cell && !cell.getElement().querySelector('input')) cell.getElement().textContent = row.terminalNumber
        }
        // Keep the DOM control in sync even if Tabulator retained the formatter element.
        const checkbox = existing.getElement().querySelector<HTMLInputElement>('[tabulator-field="selected"] input')
        if (checkbox) checkbox.checked = row.selected
        const confirmed = existing.getElement().querySelector<HTMLInputElement>('[tabulator-field="manualConfirmed"] input')
        if (confirmed) { confirmed.checked = row.manualConfirmed; confirmed.disabled = !!props.editingDisabled || !row.item }
        existing.getElement().classList.toggle('ocr-linked-row', row.item?.id === props.selectedId)
        existing.getElement().querySelector('.ocr-raw-review')?.classList.toggle('hidden', !row.item?.needsRawTextReview || !!row.item?.corrected)
      }
    }
    if (orderChanged) table.setSort('index', 'asc')
  } else { activeCell = undefined; void table.replaceData(data) }
  syncing = false
  scheduleNumberRange()
}
onMounted(() => {
  const textColumn = (title: string, field: GridField, minWidth: number): ColumnDefinition => ({ title, field, minWidth, editor: textEditor, editable, formatter: 'plaintext', headerSort: false })
  table = new Tabulator(host.value!, {
    index: 'id', data: rowData(), height: '100%', layout: 'fitColumns', placeholder: '没有匹配的识别结果',
    selectableRange: 1, selectableRangeColumns: false, selectableRangeRows: false, editTriggerEvent: 'dblclick',
    columns: [
      { title: '选择', field: 'selected', width: 58, headerSort: false, formatter(cell) { const input = document.createElement('input'); input.type = 'checkbox'; input.checked = !!cell.getValue(); input.setAttribute('aria-label', `选择第 ${(cell.getRow().getData() as GridRow).index} 行`); input.style.pointerEvents = 'none'; return input }, cellClick(event, cell) {
        const row = cell.getRow().getData() as GridRow, ids = table!.getRows('active').map(r => String(r.getIndex()))
        let selected = [...props.selectedIds]
        if ((event as MouseEvent).shiftKey && anchorId && ids.includes(anchorId)) { const a = ids.indexOf(anchorId), b = ids.indexOf(row.id); selected = [...new Set([...selected, ...ids.slice(Math.min(a, b), Math.max(a, b) + 1)])] }
        else { selected = selected.includes(row.id) ? selected.filter(id => id !== row.id) : [...selected, row.id]; anchorId = row.id }
        emit('selection', selected)
      } },
      { title: '序号', field: 'index', width: 62, headerSort: false },
      { ...textColumn('端子号', 'terminalNumber', 110), formatter(cell) { const text = document.createElement('span'); text.textContent = String(cell.getValue() || ''); return text }, cellClick(_event, cell) { if ((cell.getRow().getData() as GridRow).requiresTerminalReview) feedback.value = '该线号尚无关联端子；确有漏检时，请先补充并保存端子点' } }, { ...textColumn('线缆编号', 'cable', 170), formatter(cell) {
        const content = document.createElement('span'); content.textContent = String(cell.getValue() ?? '')
        const item = (cell.getRow().getData() as GridRow).item
        if (item?.needsRawTextReview && !item.corrected) { const badge = document.createElement('small'); badge.className = 'ocr-raw-review'; badge.textContent = ' 待核对原始标记'; content.appendChild(badge) }
        return content
      } },
      { title: '人工确认', field: 'manualConfirmed', width: 100, headerSort: false, formatter(cell) { const input = document.createElement('input'); input.type = 'checkbox'; input.checked = !!cell.getValue(); input.disabled = !editable(cell); input.style.pointerEvents = 'none'; return input }, cellClick(_event, cell) { if (editable(cell)) submit([{ id: (cell.getRow().getData() as GridRow).item!.id, field: 'manualConfirmed', value: !cell.getValue() }]) } },
      textColumn('备注', 'tableNote', 150),
    ],
    rowFormatter(row) { const data = row.getData() as GridRow; if (data.item) row.getElement().dataset.resultId = data.item.id; row.getElement().classList.toggle('ocr-linked-row', data.item?.id === props.selectedId) },
  })
  table.on('tableBuilt', () => { built = true; refresh() })
  table.on('rangeAdded', scheduleNumberRange)
  table.on('rangeChanged', scheduleNumberRange)
  table.on('rangeRemoved', scheduleNumberRange)
  table.on('cellClick', (_event, cell) => { activeCell = cell; const item = (cell.getRow().getData() as GridRow).item; if (item) emit('select', item.id) })
  table.on('cellEdited', cell => { if (!syncing) submit([{ id: (cell.getRow().getData() as GridRow).item!.id, field: cell.getField() as GridField, value: cell.getValue() }]) })
  host.value!.addEventListener('paste', paste, true)
  host.value!.addEventListener('copy', copy, true)
  host.value!.addEventListener('keydown', keydown, true)
  host.value!.addEventListener('mousedown', selectionMouseDown, true)
  document.addEventListener('mouseup', selectionMouseUp)
})
watch(() => [props.rows, props.revision, props.selectedIds, props.editingDisabled], refresh, { deep: true })
watch(() => props.selectedId, id => {
  refresh()
  const row = table?.getRow(id)
  if (built && row) void row.scrollTo('nearest', false)
})
watch(expanded, async () => { await nextTick(); table?.redraw(true) })
onBeforeUnmount(() => { built = false; host.value?.removeEventListener('paste', paste, true); host.value?.removeEventListener('copy', copy, true); host.value?.removeEventListener('keydown', keydown, true); host.value?.removeEventListener('mousedown', selectionMouseDown, true); document.removeEventListener('mouseup', selectionMouseUp); table?.destroy() })
</script>

<template>
  <section class="ocr-grid-shell" :class="{ expanded }" aria-label="OCR专业数据表格">
    <div class="ocr-grid-toolbar">
      <button :disabled="!canUndo" @click="emit('undo')">撤销</button><button :disabled="!canRedo" @click="emit('redo')">重做</button>
      <button @click="fillDown">向下填充</button>
      <button :disabled="editingDisabled || (!numberRangeIds.length && !selectedIds.length)" @click="openNumberDialog">顺序编号</button>
      <button @click="expanded = !expanded">{{ expanded ? '退出放大' : '放大表格' }}</button>
      <button v-if="Object.values(statuses).some(s => s.startsWith('保存失败'))" @click="Object.entries(statuses).filter(([, s]) => s.startsWith('保存失败')).forEach(([id]) => emit('retry', id))">重试失败项</button>
      <span>{{ Object.values(statuses).filter(s => s === '保存中').length }} 行保存中 / {{ Object.values(statuses).filter(s => s.startsWith('保存失败') || s.startsWith('版本冲突')).length }} 行失败或冲突</span>
    </div>
    <p class="ocr-grid-hint">双击编辑；Tab 左右、Enter 上下；拖选区域后 Ctrl+C/V；Ctrl+D 向下填充；选择列从未勾选行拖选可勾选，从已勾选行拖选可取消，支持 Shift 连选。</p>
    <p class="ocr-grid-hint">人工确认列支持纵向拖选：从未确认行开始批量确认，从已确认行开始批量取消；只读行跳过，整批操作可撤销。</p>
    <p v-if="editingDisabled" class="ocr-grid-hint">请先保存或退出端子点编辑，再修改表格或编号；当前显示的端子点可能尚未保存。</p>
    <div ref="host" class="ocr-grid-host" tabindex="0"></div>
    <p class="ocr-grid-feedback" role="status">{{ feedback }}</p>
    <div v-for="(status, id) in statuses" :key="id" class="ocr-grid-conflict">
      <template v-if="status.startsWith('版本冲突')">
        {{ id }}：{{ status }}；服务器端子号：{{ rows.find(row => row.item?.id === id)?.item?.terminalNumber || '空' }}；服务器线号：{{ rows.find(row => row.item?.id === id)?.item?.corrected || rows.find(row => row.item?.id === id)?.item?.text }}；服务器备注：{{ rows.find(row => row.item?.id === id)?.item?.tableNote || '空' }}；服务器确认：{{ rows.find(row => row.item?.id === id)?.item?.manualConfirmed ? '是' : '否' }}
        <button @click="emit('retry', String(id))">已核对，重试我的修改</button>
      </template>
    </div>
    <a-modal v-model:open="numberDialog" title="顺序编号" ok-text="应用编号" cancel-text="取消" :ok-button-props="{ disabled: !preview.length || !!numberPlan.error }" @ok="numberRows">
      <p v-if="terminalCount !== undefined" class="ocr-number-count">模型识别：{{ modelTerminalCount ?? '未知' }} 个端子；当前端子数量：{{ terminalCount }} 个（含已保存人工修正）。本次仅修改已有行的编号文字，不新增端子。按坐标排列仅为位置配对，请核对原图对应关系。</p>
      <p class="ocr-number-scope">目标范围：{{ numberSource === 'range' ? '端子号单元格选区' : '勾选行' }}，共 {{ numberTargets.length }} 行（表格行号：{{ numberTargets.map(row => row.index).join('、') }}）。</p>
      <p>端子号单元格选区优先于勾选行；仅修改此处预览的行。</p>
      <div class="ocr-number-form">
        <label>起始编号<input v-model.number="start" type="number" min="0" /></label><label>步长<input v-model.number="step" type="number" min="1" /></label>
        <label>数字位数<input v-model.number="width" type="number" min="1" max="20" /></label><label>前缀<input v-model="prefix" /></label><label>后缀<input v-model="suffix" /></label>
        <label><input v-model="overwrite" type="checkbox" />覆盖已有端子号</label>
      </div>
      <p>按当前显示顺序编号；默认跳过已有值且不消耗编号。</p>
      <p>预览 {{ preview.length }} 行，跳过 {{ numberTargets.length - preview.length }} 行。</p>
      <p v-if="numberPlan.error" role="alert">{{ numberPlan.error }}</p>
      <div class="ocr-number-preview">
        <table aria-label="编号修改前后预览"><thead><tr><th>表格行号</th><th>修改前</th><th>修改后</th><th>处理方式</th></tr></thead>
          <tbody><tr v-for="row in previewRows" :key="row.rowKey"><td>{{ row.index }}</td><td>{{ row.before || '（空白）' }}</td><td>{{ row.after || '（空白）' }}</td><td>{{ row.action }}</td></tr></tbody>
        </table>
      </div>
    </a-modal>
  </section>
</template>

<style scoped>
.ocr-grid-shell { display:flex; flex:1; flex-direction:column; min-height:320px; min-width:0; background:#fff; }
.ocr-grid-shell.expanded { position:fixed; inset:16px; z-index:1000; padding:16px; box-shadow:0 0 0 16px #0005; }
.ocr-grid-toolbar { display:flex; flex-wrap:wrap; gap:6px; align-items:center; padding:8px; }
button { border:1px solid #d9d9d9; background:#fff; border-radius:4px; padding:4px 10px; cursor:pointer; }
button:disabled { opacity:.45; cursor:default; }
.ocr-grid-hint,.ocr-grid-feedback { padding:0 8px; margin:4px 0 8px; font-size:12px; color:#536174; }
.ocr-grid-host { flex:1; min-height:230px; }
.ocr-grid-host.tabulator { background:#fff; border-color:#e2e8e5; }
.ocr-grid-conflict:empty { display:none; }
.ocr-grid-conflict { color:#a64000; padding:4px 8px; }
.ocr-number-form { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.ocr-number-form label { display:flex; flex-direction:column; gap:4px; }
.ocr-number-preview { max-height:280px; overflow:auto; }
.ocr-number-preview table { width:100%; border-collapse:collapse; }
.ocr-number-preview th,.ocr-number-preview td { padding:6px; border:1px solid #e2e8e5; text-align:left; overflow-wrap:anywhere; }
.ocr-number-preview th { position:sticky; top:0; background:#f5f8f7; }
.ocr-number-scope { overflow-wrap:anywhere; }
.ocr-grid-boundary { color:#ad6800; font-size:12px; padding:0 8px; }
.ocr-grid-host :deep(.ocr-linked-row) { background:#e6f4ff !important; }
.ocr-grid-host :deep(.tabulator-cell) { min-height:34px; }
.ocr-grid-host :deep(.tabulator-cell input[type=checkbox]) { accent-color:#1677ff; }
.ocr-grid-host :deep(.ocr-raw-review) { color:#ad6800; }
.ocr-grid-host :deep(.ocr-raw-review.hidden) { display:none; }
</style>
