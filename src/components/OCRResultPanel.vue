<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { CommentOutlined, DeleteOutlined, EditOutlined, UndoOutlined, WarningOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import type { OcrItem, OcrPage, OcrReviewStatus } from '../types/ocr'
import type { ExportMode } from '../exportResults'
import { filterOcrItems } from '../resultVisibility'
import { sortOcrItemsByCoordinates } from '../ocrResultOrder'
import { terminalNumberFillValues } from '../terminalNumberFill'
import { createGridEditing, type GridChange } from '../ocrGridEditing'
import { useRoute } from 'vue-router'
import TerminalBusinessGrid from './TerminalBusinessGrid.vue'
import { terminalTableRows } from '../terminalPairTable'

const OcrResultGrid = defineAsyncComponent(() => import('./OcrResultGrid.vue'))

const props = defineProps<{
  page: OcrPage
  pages: OcrPage[]
  selectedId: string
  selectedTerminalId?: string
  modelLabel: string
  lowConfidenceThreshold: number
  showConfidence: boolean
  canUndoReview: boolean
  datasetReviewed?: boolean
  datasetReviewSaving?: boolean
  datasetReviewDisabled?: boolean
  editingDisabled?: boolean
  saveTable: (item: OcrItem, values: { terminalNumber: string; manualConfirmed: boolean; tableNote: string }) => Promise<void>
  saveCable: (item: OcrItem, text: string) => Promise<void>
}>()

const emit = defineEmits<{
  select: [id: string]
  selectTerminal: [id: string]
  selectBusiness: [selection: { pointId: string; sourceId: string }]
  businessChanged: []
  correct: [item: OcrItem]
  correctSource: [item: OcrItem]
  comment: [item: OcrItem]
  export: [mode: ExportMode]
  review: [ids: string[], status: OcrReviewStatus]
  undo: []
  'complete-review': []
  'visible-change': [ids: string[]]
}>()

const search = ref('')
const lowOnly = ref(false)
const minimumConfidencePercent = ref(0)
const showFalsePositive = ref(false)
const showDeleted = ref(false)
const selectedIds = ref<string[]>([])
const coordinateSorted = ref(false)
const viewMode = ref<'list' | 'table'>('list')
const route = useRoute()
const businessGrid = ref<InstanceType<typeof TerminalBusinessGrid>>()
const changeMode = async (mode: 'list' | 'table') => { if (await flushPendingEdits()) { selectedIds.value = []; viewMode.value = mode } else message.warning('请先完成保存或处理失败') }
const editing = createGridEditing(() => props.page.items, props.saveTable, props.saveCable, change => {
  if (props.editingDisabled) throw new Error('请先保存或退出端子点编辑，再修改表格')
  if (change.field === 'terminalNumber' && hasTerminalResult.value && !terminalRows.value.some(row => row.item?.id === change.id && row.hasTerminal)) {
    throw new Error('该线号未匹配到端子点，请核对原图和位置；确有漏检时，先补充并保存端子点')
  }
})
function applyHistory(redo = false) { try { editing.history(redo) } catch (error) { message.warning((error as Error).message) } }
const terminalNumberFilling = ref(false)
const hasPendingEdits = () => !!businessGrid.value?.pending() || editing.pending()
const flushPendingEdits = async () => { if (businessGrid.value && !await businessGrid.value.flush()) return false; return editing.flush() }
const syncCorrection = editing.syncCorrection
function applyGridChanges(changes: GridChange[]) {
  try { editing.apply(changes) } catch (error) { message.error(String(error)) }
}

defineExpose({ hasPendingEdits, flushPendingEdits, syncCorrection, exportItems: () => viewMode.value === 'table' ? businessGrid.value?.exportItems() : undefined })
const filteredItems = computed(() => filterOcrItems(props.page.items.filter(item => !item.terminalPointId), {
  search: search.value,
  minimumConfidence: minimumConfidencePercent.value / 100,
  lowOnly: lowOnly.value,
  lowConfidenceThreshold: props.lowConfidenceThreshold,
  showFalsePositive: showFalsePositive.value,
  showDeleted: showDeleted.value,
}))
const displayedItems = computed(() => coordinateSorted.value
  ? sortOcrItemsByCoordinates(filteredItems.value)
  : filteredItems.value)
const hasTerminalResult = computed(() => Array.isArray(props.page.terminalPoints))
const terminalRows = computed(() => terminalTableRows(props.page.terminalPoints || [], props.page.items))
const visibleSelectionIds = computed(() => viewMode.value === 'table' && hasTerminalResult.value
  ? terminalRows.value.filter(row => !row.item || displayedItems.value.some(item => item.id === row.item!.id)).map(row => row.selectionId) : displayedItems.value.map(item => item.id))
const selectedReviewIds = computed(() => props.page.items.filter(item => selectedIds.value.includes(item.id)).map(item => item.id))
const allVisibleSelected = computed(() => visibleSelectionIds.value.length > 0 && visibleSelectionIds.value.every(id => selectedIds.value.includes(id)))
function scoreColor(score: number) {
  if (score < 0.90) return '#ef5350'
  if (score < 0.95) return '#42a5f5'
  return '#66bb6a'
}

function handleExportSelect({ key }: { key: string | number }) {
  if (key === 'simple' || key === 'full') emit('export', key)
}

function toggleSelected(id: string, checked: boolean) {
  selectedIds.value = checked ? [...new Set([...selectedIds.value, id])] : selectedIds.value.filter(value => value !== id)
}

function toggleAllVisible(checked: boolean) {
  const visible = new Set(visibleSelectionIds.value)
  selectedIds.value = checked
    ? [...new Set([...selectedIds.value, ...visible])]
    : selectedIds.value.filter(id => !visible.has(id))
}

function reviewSelected(status: OcrReviewStatus) {
  const ids = [...selectedReviewIds.value]
  if (!ids.length) return
  const apply = () => {
    emit('review', ids, status)
    selectedIds.value = []
  }
  if (status === 'deleted' || status === 'false_positive') {
    Modal.confirm({
      title: status === 'deleted' ? '确认删除识别结果' : '确认标记误检',
      content: `本次操作将影响 ${ids.length} 条 OCR 结果，可通过恢复或撤销找回。`,
      okText: '确认', cancelText: '取消', onOk: apply,
    })
  } else apply()
}

async function fillSelectedTerminalNumbers() {
  if (terminalNumberFilling.value) return
  const values = terminalNumberFillValues(displayedItems.value, selectedIds.value)
  editing.apply([...values].filter(([id]) => !editing.values(id).terminalNumber.trim()).map(([id, value]) => ({ id, field: 'terminalNumber', value })))
  terminalNumberFilling.value = true
  try { await editing.flush() } finally { terminalNumberFilling.value = false }
}
const gridRows = computed(() => hasTerminalResult.value
  ? terminalRows.value.filter(row => !row.item || displayedItems.value.some(item => item.id === row.item!.id))
  : displayedItems.value.map(item => ({ selectionId: item.id, terminalNumber: item.terminalNumber || '', item, hasTerminal: true, hasOcrResult: true, requiresTerminalReview: false })))

watch(displayedItems, items => emit('visible-change', items.map(item => item.id)), { immediate: true })
watch(visibleSelectionIds, ids => { selectedIds.value = selectedIds.value.filter(id => ids.includes(id)) })
watch(() => props.page, () => { selectedIds.value = []; coordinateSorted.value = false; editing.reset() })
</script>

<template>
  <aside class="results-panel">
    <div class="results-head">
<!--      <div class="results-heading"><h2>识别结果</h2><span>{{ page.items.length }} 个文本区域</span></div>-->
      <div class="result-mode-row" role="group" aria-label="识别结果显示方式">
      <button :class="{ active: viewMode === 'list' }" :aria-pressed="viewMode === 'list'" @click="changeMode('list')">列表显示</button>
      <button :class="{ active: viewMode === 'table' }" :aria-pressed="viewMode === 'table'" @click="changeMode('table')">表格显示</button>
      <span v-if="viewMode === 'table'">修改后离开单元格自动保存</span>
    </div>
      <button class="copy-btn" :disabled="page.items.length < 2" @click="coordinateSorted = true">{{ coordinateSorted ? '已按坐标排序' : '按坐标排序' }}</button>
      <a-dropdown :trigger="['click']">
        <button class="copy-btn">导出结果</button>
        <template #overlay>
          <a-menu @click="handleExportSelect">
            <a-menu-item key="simple">精简导出</a-menu-item>
            <a-menu-item key="full">完整导出</a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </div>

    <!-- <div class="metrics">
      <div><span>全文字符</span><b>{{ stats.count * 8 + 76 }}</b></div>
      <div><span>平均置信度</span><b>{{ (stats.average * 100).toFixed(1) }}%</b></div>
      <div><span>待复核</span><b class="warning">{{ stats.low }}</b></div>
    </div> -->
<!--    <div class="filter-row">-->
<!--      <a-input v-model:value="search" placeholder="搜索识别内容" allow-clear><template #prefix><SearchOutlined /></template></a-input>-->
<!--&lt;!&ndash;      <button class="filter-btn" :class="{ active: lowOnly }" @click="lowOnly = !lowOnly">低置信度 &lt;{{ Math.round(activeLowConfidenceThreshold * 100) }}% <span>{{ lowConfidenceCount }}</span></button>&ndash;&gt;-->
<!--    </div>-->
<!--    <div class="confidence-filter">-->
<!--      <span>最低置信度</span>-->
<!--      <a-slider v-model:value="minimumConfidencePercent" :min="0" :max="100" :step="1" />-->
<!--      <b>{{ minimumConfidencePercent }}%</b>-->
<!--      <button v-for="value in [0, 50, 70, 90]" :key="value" :class="{ active: minimumConfidencePercent === value }" @click="minimumConfidencePercent = value">{{ value ? `${value}%` : '全部' }}</button>-->
<!--    </div>-->
<!--    <div class="review-filter-row">-->
<!--      <a-checkbox :checked="showFalsePositive" @update:checked="showFalsePositive = $event">显示误检（{{ falsePositiveCount }}）</a-checkbox>-->
<!--      <a-checkbox :checked="showDeleted" @update:checked="showDeleted = $event">显示已删除（{{ deletedCount }}）</a-checkbox>-->
<!--      <span>可见 {{ filteredItems.length }} / 有效 {{ activeItems.length }} / 总计 {{ page.items.length }}</span>-->
<!--    </div>-->
    <div v-if="viewMode === 'list' || !hasTerminalResult" class="batch-review-bar">
      <a-checkbox :checked="allVisibleSelected" @update:checked="toggleAllVisible($event)">全选当前</a-checkbox>
      <span>已选 {{ selectedIds.length }} 项</span>
      <button v-if="viewMode === 'list'" :disabled="!selectedReviewIds.length" @click="reviewSelected('false_positive')"><WarningOutlined /> 标记误检</button>
      <button v-else-if="!hasTerminalResult" :disabled="!selectedIds.length || terminalNumberFilling" @click="fillSelectedTerminalNumbers"><EditOutlined /> {{ terminalNumberFilling ? '填充中' : '一键填充端子号' }}</button>
      <button class="danger" :disabled="!selectedReviewIds.length" @click="reviewSelected('deleted')"><DeleteOutlined /> 删除</button>
      <button :disabled="!selectedReviewIds.length" @click="reviewSelected('unreviewed')"><UndoOutlined /> 恢复</button>
      <span v-if="viewMode === 'table' && hasTerminalResult">删除和恢复仅作用于所选行中的 OCR 结果</span>
    </div>
    <div v-if="viewMode === 'list'" class="result-list">
      <article v-for="(item, displayIndex) in displayedItems" :key="item.id" :data-result-id="item.id" class="result-card" :class="{ selected: selectedId === item.id, corrected: item.corrected }" @click="emit('select', item.id)">
        <a-checkbox class="result-select" :checked="selectedIds.includes(item.id)" @click.stop @update:checked="toggleSelected(item.id, $event)" />
        <div class="result-index">{{ String(displayIndex + 1).padStart(2, '0') }}</div>
        <div class="result-main">
          <p>
            {{ item.corrected ?? item.text }}
            <span v-if="item.needsRawTextReview && !item.corrected" class="raw-text-review-tag">待核对原始标记</span>
          </p>
          <div class="result-meta">
            <span v-if="item.editSource === 'manual'" class="manual-result-tag">人工新增</span>
            <span v-else-if="showConfidence" :class="item.score < lowConfidenceThreshold ? 'low-score' : ''"><i :style="{ background: scoreColor(item.score) }"></i>{{ (item.score * 100).toFixed(1) }}%</span>
            <span v-if="item.corrected" class="corrected-tag">已纠正</span>
            <span v-if="item.comments.length"><CommentOutlined /> {{ item.comments.length }}</span>
            <span v-if="item.reviewStatus === 'false_positive'" class="review-status-tag">误检</span>
            <span v-if="item.reviewStatus === 'deleted'" class="review-status-tag deleted">已删除</span>
          </div>
        </div>
        <div class="hover-actions">
          <button title="纠正识别文字" @click.stop="emit('correct', item)"><EditOutlined /> 纠正</button>
          <button title="添加或查看留言" @click.stop="emit('comment', item)"><CommentOutlined /> 留言</button>
          <button title="标记为误检" @click.stop="emit('review', [item.id], 'false_positive')"><WarningOutlined /> 误检</button>
          <button title="删除结果" @click.stop="emit('review', [item.id], 'deleted')"><DeleteOutlined /> 删除</button>
        </div>
      </article>
      <a-empty v-if="!displayedItems.length" description="没有匹配的识别结果" />
    </div>
    <TerminalBusinessGrid v-if="hasTerminalResult" v-show="viewMode === 'table'" :key="`${route.params.taskId}:${page.no}`" ref="businessGrid" :selected-terminal-id="selectedTerminalId" :selected-source-id="selectedId" :page="page" :editing-disabled="editingDisabled" @select-business="emit('selectBusiness', $event)" @select-terminal="emit('selectTerminal', $event)" @changed="emit('businessChanged')" @select-source="emit('select', $event)" />
    <OcrResultGrid v-if="viewMode === 'table' && !hasTerminalResult" :rows="gridRows" :selected-id="selectedId"
      :terminal-count="hasTerminalResult ? (page.terminalPoints?.length || 0) : undefined" :model-terminal-count="page.terminalModelCount" :editing-disabled="editingDisabled"
      :selected-ids="selectedIds" :values="editing.values" :statuses="editing.state.status" :revision="editing.state.revision"
      :can-undo="!!editing.state.undo.length" :can-redo="!!editing.state.redo.length"
      @correct-source="async item => { if (await flushPendingEdits()) emit('correctSource', item); else message.warning('请先完成表格保存并处理失败或冲突') }"
      @change="applyGridChanges" @select="emit('select', $event)" @selection="selectedIds = $event"
      @undo="applyHistory()" @redo="applyHistory(true)" @retry="editing.retry($event)" />
    <footer class="results-footer">
      <button v-if="canUndoReview" class="footer-undo-btn" @click="emit('undo')"><UndoOutlined /> 撤销上一次结果操作</button>
      <span class="dataset-review-hint">确认当前任务的文字和标注框已全部复核</span>
      <a-button type="primary" :loading="datasetReviewSaving" :disabled="datasetReviewed || datasetReviewDisabled || hasPendingEdits()" @click="emit('complete-review')"><span style="color: #fff">{{ datasetReviewed ? '已复核' : '复核完成' }}</span></a-button>
    </footer>
  </aside>
</template>
