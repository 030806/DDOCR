<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute } from 'vue-router'
import type { OcrPage, OcrItem } from '../types/ocr'
import { loadTerminalDocument, saveTerminalDocument, type TerminalDocument, type TerminalRecord, type SourceChange } from '../api/terminalDocument'
import { businessSelection } from '../businessSelection'
import { transferBusinessRows, type BusinessClipboard } from '../businessClipboard'
import { normalizeGridValue, type GridChange, type GridValues } from '../ocrGridEditing'
import { sourceCorrectionUnavailable } from '../sourceCorrection'
import OcrResultGrid from './OcrResultGrid.vue'
import CorrectionModal from './CorrectionModal.vue'
const props = defineProps<{ page: OcrPage; selectedTerminalId?: string; selectedSourceId?: string; editingDisabled?: boolean }>()
const emit = defineEmits<{ selectTerminal: [pointId: string]; changed: []; selectSource: [id: string]; selectBusiness: [selection: { pointId: string; sourceId: string }] }>()
const job = String(useRoute().params.taskId)
const pageNo = props.page.no
const doc = ref<TerminalDocument>({ revision: 0, records: [] })
const busy = ref(false), loaded = ref(false), failed = ref(false)
const selected = ref<string[]>([]), active = ref('')
const sourceOpen = ref(false), sourceTarget = ref<OcrItem>(), sourceRecordId = ref('')
const syncSource = ref(true)
const pendingHistory = ref<boolean>()
const failedInput = ref<{ records: TerminalRecord[]; source?: SourceChange; syncId?: string }>()
type Operation = { before: TerminalRecord[]; after: TerminalRecord[]; sourceId?: string; beforeText?: string; afterText?: string; expectedSourceRevision?: number }
const undo = ref<Operation[]>([]), redo = ref<Operation[]>([])
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
watch(() => [props.selectedTerminalId, props.selectedSourceId, doc.value.records.length], () => {
  active.value = props.selectedTerminalId ? `terminal:${props.selectedTerminalId}` : doc.value.records.find(r => r.sourceResultId === props.selectedSourceId)?.id || ''
}, { immediate: true })
const sourceRecord = computed(() => doc.value.records.find(r => r.id === sourceRecordId.value))
const values = (id: string): GridValues => {
  const row = doc.value.records.find(r => r.id === id)!
  return { terminalNumber: row.terminalNumber, cable: row.cable, tableNote: row.tableNote, manualConfirmed: row.manualConfirmed }
}
const rows = computed(() => doc.value.records.filter(r => !r.orphaned).map(r => ({ selectionId: r.id, terminalNumber: r.terminalNumber,
  item: { id: r.id, text: r.cable, score: 1, bbox: [0, 0, 4, 4], comments: [] } as OcrItem,
  hasTerminal: true, requiresTerminalReview: false })))
async function load() {
  busy.value = true
  try {
    const fresh = await loadTerminalDocument(job, pageNo)
    if (loaded.value && fresh.revision !== doc.value.revision) { undo.value = []; redo.value = []; pendingHistory.value = undefined }
    doc.value = fresh
    for (const r of doc.value.records) {
      const source = props.page.items.find(i => i.id === r.sourceResultId)
      if (source && r.currentSourceRevision !== undefined && r.sourceText !== undefined) {
        if (r.currentSourceRevision > (source.revision || 0)) source.corrected = r.sourceText
        source.revision = r.currentSourceRevision
      }
    }
    loaded.value = true; failed.value = false
  }
  catch { failed.value = true; message.error('端子业务记录加载失败，请重试') }
  finally { busy.value = false }
}
onMounted(load)
watch(() => JSON.stringify([props.page.items.map(i => [i.id, i.revision, i.reviewStatus]), props.page.terminalPoints]), () => { if (!busy.value && !failedInput.value) void load() })
function reflectSource(source?: SourceChange, revision?: number) {
  if (!source) return
  const item = props.page.items.find(i => i.id === source.result_id)
  if (item) { item.corrected = source.text; item.revision = revision }
  for (const operation of [...undo.value, ...redo.value]) if (operation.sourceId === source.result_id) operation.expectedSourceRevision = revision
}
async function commit(records: TerminalRecord[], source?: SourceChange, syncId?: string) {
  busy.value = true
  try {
    const saved = await saveTerminalDocument(job, pageNo, { revision: doc.value.revision, records }, source, syncId)
    doc.value = saved
    failed.value = false
    failedInput.value = undefined
    reflectSource(source, saved.correction?.revision)
    emit('changed')
    return true
  } catch { failed.value = true; failedInput.value = { records: clone(records), source, syncId }; message.error('保存失败或版本冲突，整批输入已保留；可重试或重新加载核对') ; return false }
  finally { busy.value = false }
}
async function change(changes: GridChange[]) {
  if (busy.value || props.editingDisabled) return
  const before = clone(doc.value.records), after = clone(before)
  try {
    for (const c of changes) {
      const row = after.find(r => r.id === c.id)
      if (!row) throw new Error('端子记录不存在')
      Object.assign(row, { [c.field]: normalizeGridValue(c.field, c.value), manual: true })
      if (c.field === 'cable' && c.clearSource) Object.assign(row, { sourceResultId: null, sourceRevision: 0, manualConfirmed: false })
    }
    if (await commit(after)) { undo.value.push({ before, after: clone(doc.value.records) }); redo.value = [] }
  } catch (error) { message.error(String(error)) }
}
function clipboardSource(id: string): BusinessClipboard['rows'][number] {
  const r = doc.value.records.find(r => r.id === id)!
  return { id: r.id, cable: r.cable, sourceResultId: r.sourceResultId, sourceRevision: r.sourceRevision }
}
async function transfer(payload: BusinessClipboard, targets: string[]) {
  if (busy.value || props.editingDisabled || payload.scope !== `${job}:${pageNo}`) return
  try {
    const before = clone(doc.value.records), after = transferBusinessRows(before, payload, targets)
    if (await commit(after)) { undo.value.push({ before, after: clone(doc.value.records) }); redo.value = [] }
  } catch (error) { message.error(String(error)) }
}
function select(id: string) {
  active.value = id
  const row = doc.value.records.find(r => r.id === id)
  if (row) emit('selectBusiness', businessSelection(row))
}
function sourceReason(item?: OcrItem) {
  const record = doc.value.records.find(r => r.id === item?.id)
  return sourceCorrectionUnavailable(props.page.items.find(i => i.id === record?.sourceResultId))
}
function correctSource(item: OcrItem) {
  const row = doc.value.records.find(r => r.id === item.id)
  const source = props.page.items.find(i => i.id === row?.sourceResultId)
  const reason = sourceCorrectionUnavailable(source)
  if (reason) { message.warning(reason); return }
  sourceTarget.value = source
  sourceRecordId.value = row!.id
  syncSource.value = true
  sourceOpen.value = true
  select(row!.id)
  emit('selectBusiness', { pointId: row!.terminalPointId || '', sourceId: source!.id })
}
async function saveSource(text: string) {
  const source = sourceTarget.value
  if (!source || busy.value) return
  const before = clone(doc.value.records), beforeText = source.corrected ?? source.text
  if (await commit(clone(before), { result_id: source.id, base_revision: source.revision || 0, text }, syncSource.value && (sourceRecord.value?.manual || sourceRecord.value?.manualConfirmed) ? sourceRecordId.value : undefined)) {
    undo.value.push({ before, after: clone(doc.value.records), sourceId: source.id, beforeText, afterText: text, expectedSourceRevision: source.revision })
    redo.value = []; sourceOpen.value = false
  }
}
async function history(forward = false) {
  if (busy.value || props.editingDisabled) return
  const stack = forward ? redo.value : undo.value
  const op = stack[stack.length - 1]
  if (!op) return
  const item = props.page.items.find(i => i.id === op.sourceId)
  if (op.sourceId && item?.revision !== op.expectedSourceRevision) { message.warning('来源文字已被其他操作修改，不能直接撤销，请核对当前值'); return }
  const source = op.sourceId && item ? { result_id: op.sourceId, base_revision: item.revision || 0, text: (forward ? op.afterText : op.beforeText)! } : undefined
  pendingHistory.value = forward
  if (await commit(clone(forward ? op.after : op.before), source)) {
    pendingHistory.value = undefined
    if (item) op.expectedSourceRevision = item.revision
    stack.pop(); (forward ? undo.value : redo.value).push(op)
  }
}
async function adoptSource(record: TerminalRecord) {
  const source = props.page.items.find(i => i.id === record.sourceResultId)
  if (!source || busy.value) return
  const before = clone(doc.value.records), after = clone(before)
  Object.assign(after.find(r => r.id === record.id)!, { cable: source.corrected ?? source.text, manual: true, manualConfirmed: false, sourceRevision: source.revision || 0 })
  if (await commit(after)) { undo.value.push({ before, after: clone(doc.value.records) }); redo.value = [] }
}
async function retry() {
  if (pendingHistory.value !== undefined) { await history(pendingHistory.value); return }
  const input = failedInput.value
  if (!input || busy.value) return
  const before = clone(doc.value.records)
  const sourceItem = props.page.items.find(i => i.id === input.source?.result_id)
  const beforeText = sourceItem ? sourceItem.corrected ?? sourceItem.text : undefined
  if (await commit(input.records, input.source, input.syncId)) {
    undo.value.push({ before, after: clone(doc.value.records), sourceId: input.source?.result_id, beforeText, afterText: input.source?.text, expectedSourceRevision: sourceItem?.revision })
    redo.value = []; sourceOpen.value = false
  }
}
function exportItems(): OcrItem[] {
  return doc.value.records.filter(r => !r.orphaned).map(r => ({ id: r.id, text: r.cable, corrected: r.cable, score: 1, bbox: [0, 0, 4, 4], comments: [], terminalPointId: r.terminalPointId || undefined, terminalNumber: r.terminalNumber, tableNote: r.tableNote, manualConfirmed: r.manualConfirmed }))
}
defineExpose({ pending: () => busy.value || !loaded.value || failed.value, flush: async () => !busy.value && loaded.value && !failed.value, exportItems })
</script>
<template>
  <div class="business-grid">
    <p class="business-hint">端子最终结果：编辑、粘贴和清空不修改 OCR 列表。包含全部有效识别编号；未匹配端子点的编号点击后定位识别框。</p>
    <div v-if="failed"><button v-if="failedInput" @click="retry">重试保留的整批输入</button><button @click="async () => { await load(); if (!failed) failedInput = undefined }">重新加载（放弃保留输入）</button><details v-if="failedInput"><summary>查看保留的输入</summary><pre>{{ failedInput.records }}</pre></details></div>
    <OcrResultGrid v-if="loaded" :rows="rows" :clipboard-scope="`${job}:${pageNo}`" :clipboard-source="clipboardSource" @transfer="transfer" :source-reason="sourceReason" :selected-id="active" :selected-ids="selected" :values="values" :statuses="{}" :revision="doc.revision" :can-undo="!!undo.length && !busy" :can-redo="!!redo.length && !busy" :editing-disabled="busy || failed || editingDisabled" @change="change" @select="select" @selection="selected = $event" @undo="history()" @redo="history(true)" @correct-source="correctSource" />
    <p v-if="busy" role="status">正在加载或保存整批操作…</p>
    <details><summary>识别来源状态</summary><p v-for="r in doc.records.filter(r => r.sourceChanged || r.sourceUnavailable || r.orphaned)" :key="r.id">{{ r.terminalNumber }}：{{ r.orphaned ? '端子点已移除，记录保留待核对' : r.sourceUnavailable ? '识别来源已失效，业务值已保留' : '识别来源已更新，业务值已保留' }} <button v-if="r.sourceChanged && !r.sourceUnavailable" @click="correctSource({ id: r.id } as OcrItem)">查看来源</button><button v-if="r.sourceChanged && !r.sourceUnavailable" @click="adoptSource(r)">采用识别值</button></p></details>
    <CorrectionModal v-model:open="sourceOpen" :item="sourceTarget" :saving="busy" source-mode :independent="true" :image-url="page.imageUrl" :source-width="page.sourceWidth" :source-height="page.sourceHeight" @save="saveSource">
      <template #default="{ text }">
      <p>当前端子最终编号：{{ sourceRecord?.cable || '（空白）' }}</p>
      <p v-if="!sourceRecord?.manual && !sourceRecord?.manualConfirmed">此行尚未人工修改，来源纠正后自动跟随。</p>
      <label v-else><input v-model="syncSource" type="checkbox" />同时修改当前端子的最终线缆编号（修改后重新待确认）</label>
      <p v-if="syncSource">表格将从 {{ sourceRecord?.cable || '（空白）' }} 改为 {{ text || '（空白）' }}</p>
      </template>
    </CorrectionModal>
  </div>
</template>
<style scoped>
.business-grid { display:flex; flex:1; flex-direction:column; min-height:0; }
.business-hint,details { margin:6px 8px; font-size:12px; color:#65736e; }
</style>
