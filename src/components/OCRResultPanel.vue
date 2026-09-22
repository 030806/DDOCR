<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { CommentOutlined, DeleteOutlined, EditOutlined, SearchOutlined, UndoOutlined, WarningOutlined } from '@ant-design/icons-vue'
import { Modal } from 'ant-design-vue'
import type { OcrItem, OcrPage, OcrReviewStatus } from '../types/ocr'
import type { ExportMode } from '../exportResults'
import { filterOcrItems } from '../resultVisibility'
import { sortOcrItemsByCoordinates } from '../ocrResultOrder'

const props = defineProps<{
  page: OcrPage
  pages: OcrPage[]
  selectedId: string
  modelLabel: string
  lowConfidenceThreshold: number
  showConfidence: boolean
  canUndoReview: boolean
  datasetReviewed?: boolean
  datasetReviewSaving?: boolean
  datasetReviewDisabled?: boolean
  saveTable: (item: OcrItem, values: { terminalNumber: string; manualConfirmed: boolean; tableNote: string }) => Promise<void>
  saveCable: (item: OcrItem, text: string) => Promise<void>
}>()

const emit = defineEmits<{
  select: [id: string]
  correct: [item: OcrItem]
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
type RowDraft = { terminalNumber: string; cable: string; manualConfirmed: boolean; tableNote: string }
const drafts = reactive<Record<string, RowDraft>>({})
const saving = reactive<Record<string, boolean>>({})
const errors = reactive<Record<string, string>>({})
const rowSaves = new Map<string, Promise<void>>()
function draftFor(item: OcrItem): RowDraft {
  return drafts[item.id] ||= {
    terminalNumber: item.terminalNumber || '', cable: item.corrected || item.text,
    manualConfirmed: item.manualConfirmed || false, tableNote: item.tableNote || '',
  }
}
function fieldKey(item: OcrItem, field: keyof RowDraft) { return `${item.id}:${field}` }
async function saveField(item: OcrItem, field: keyof RowDraft) {
  const key = fieldKey(item, field)
  if (saving[key]) return
  saving[key] = true
  const previous = rowSaves.get(item.id)
  if (previous) await previous
  const submittedValue = draftFor(item)[field]
  const operation = persistField(item, field, key)
  rowSaves.set(item.id, operation)
  try { await operation } finally {
    if (rowSaves.get(item.id) === operation) rowSaves.delete(item.id)
    saving[key] = false
    const draft = draftFor(item)
    const current = field === 'cable' ? item.corrected || item.text : field === 'terminalNumber' ? item.terminalNumber || '' : field === 'tableNote' ? item.tableNote || '' : item.manualConfirmed || false
    if (!errors[key] && draft[field] !== submittedValue && draft[field] !== current) void saveField(item, field)
  }
}
async function persistField(item: OcrItem, field: keyof RowDraft, key: string) {
  const draft = draftFor(item)
  const value = draft[field]
  const original = field === 'cable' ? item.corrected || item.text :
    field === 'terminalNumber' ? item.terminalNumber || '' :
    field === 'tableNote' ? item.tableNote || '' : item.manualConfirmed || false
  if (value === original) { delete errors[key]; return }
  if (field === 'cable' && !String(value).trim()) { errors[key] = '线缆编号不能为空'; return }
  delete errors[key]
  try {
    if (field === 'cable') await props.saveCable(item, String(value).trim())
    else await props.saveTable(item, {
      terminalNumber: draft.terminalNumber.trim(), manualConfirmed: draft.manualConfirmed,
      tableNote: draft.tableNote.trim(),
    })
    if (draft[field] === value) {
      if (field === 'cable') draft.cable = item.corrected || item.text
      else if (field === 'terminalNumber') draft.terminalNumber = item.terminalNumber || ''
      else if (field === 'tableNote') draft.tableNote = item.tableNote || ''
    }
  } catch {
    errors[key] = '保存失败，点击重试'
  }
}
function hasPendingEdits() {
  return Object.values(saving).some(Boolean) || Object.values(errors).some(Boolean)
    || props.page.items.some(item => {
      const draft = drafts[item.id]
      return draft && (draft.cable !== (item.corrected || item.text)
        || draft.terminalNumber !== (item.terminalNumber || '')
        || draft.manualConfirmed !== (item.manualConfirmed || false)
        || draft.tableNote !== (item.tableNote || ''))
    })
}
defineExpose({ hasPendingEdits })
const filteredItems = computed(() => filterOcrItems(props.page.items, {
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
const activeItems = computed(() => props.page.items.filter(item => item.reviewStatus !== 'deleted' && item.reviewStatus !== 'false_positive'))
const falsePositiveCount = computed(() => props.page.items.filter(item => item.reviewStatus === 'false_positive').length)
const deletedCount = computed(() => props.page.items.filter(item => item.reviewStatus === 'deleted').length)
const activeLowConfidenceThreshold = computed(() => minimumConfidencePercent.value > 0 ? minimumConfidencePercent.value / 100 : props.lowConfidenceThreshold)
const lowConfidenceCount = computed(() => props.page.items.filter(item =>
  item.reviewStatus !== 'deleted'
  && item.reviewStatus !== 'false_positive'
  && item.score < activeLowConfidenceThreshold.value,
).length)
const allVisibleSelected = computed(() => filteredItems.value.length > 0 && filteredItems.value.every(item => selectedIds.value.includes(item.id)))
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
  const visible = new Set(filteredItems.value.map(item => item.id))
  selectedIds.value = checked
    ? [...new Set([...selectedIds.value, ...visible])]
    : selectedIds.value.filter(id => !visible.has(id))
}

function reviewSelected(status: OcrReviewStatus) {
  if (!selectedIds.value.length) return
  const apply = () => {
    emit('review', selectedIds.value, status)
    selectedIds.value = []
  }
  if (status === 'deleted' || status === 'false_positive') {
    Modal.confirm({
      title: status === 'deleted' ? '确认删除识别结果' : '确认标记误检',
      content: `本次操作将影响 ${selectedIds.value.length} 条结果，可通过恢复或撤销找回。`,
      okText: '确认', cancelText: '取消', onOk: apply,
    })
  } else apply()
}

watch(displayedItems, items => emit('visible-change', items.map(item => item.id)), { immediate: true })
watch(() => props.page.no, () => { selectedIds.value = []; coordinateSorted.value = false; Object.keys(drafts).forEach(key => delete drafts[key]) })
</script>

<template>
  <aside class="results-panel">
    <div class="results-head">
      <div class="results-heading"><h2>识别结果</h2><span>{{ page.items.length }} 个文本区域</span></div>
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
    <div class="result-mode-row" role="group" aria-label="识别结果显示方式">
      <button :class="{ active: viewMode === 'list' }" :aria-pressed="viewMode === 'list'" @click="viewMode = 'list'">列表显示</button>
      <button :class="{ active: viewMode === 'table' }" :aria-pressed="viewMode === 'table'" @click="viewMode = 'table'">表格显示</button>
      <span v-if="viewMode === 'table'">修改后离开单元格自动保存</span>
    </div>
    <!-- <div class="metrics">
      <div><span>全文字符</span><b>{{ stats.count * 8 + 76 }}</b></div>
      <div><span>平均置信度</span><b>{{ (stats.average * 100).toFixed(1) }}%</b></div>
      <div><span>待复核</span><b class="warning">{{ stats.low }}</b></div>
    </div> -->
    <div class="filter-row">
      <a-input v-model:value="search" placeholder="搜索识别内容" allow-clear><template #prefix><SearchOutlined /></template></a-input>
      <button class="filter-btn" :class="{ active: lowOnly }" @click="lowOnly = !lowOnly">低置信度 &lt;{{ Math.round(activeLowConfidenceThreshold * 100) }}% <span>{{ lowConfidenceCount }}</span></button>
    </div>
    <div class="confidence-filter">
      <span>最低置信度</span>
      <a-slider v-model:value="minimumConfidencePercent" :min="0" :max="100" :step="1" />
      <b>{{ minimumConfidencePercent }}%</b>
      <button v-for="value in [0, 50, 70, 90]" :key="value" :class="{ active: minimumConfidencePercent === value }" @click="minimumConfidencePercent = value">{{ value ? `${value}%` : '全部' }}</button>
    </div>
    <div class="review-filter-row">
      <a-checkbox :checked="showFalsePositive" @update:checked="showFalsePositive = $event">显示误检（{{ falsePositiveCount }}）</a-checkbox>
      <a-checkbox :checked="showDeleted" @update:checked="showDeleted = $event">显示已删除（{{ deletedCount }}）</a-checkbox>
      <span>可见 {{ filteredItems.length }} / 有效 {{ activeItems.length }} / 总计 {{ page.items.length }}</span>
    </div>
    <div class="batch-review-bar">
      <a-checkbox :checked="allVisibleSelected" @update:checked="toggleAllVisible($event)">全选当前</a-checkbox>
      <span>已选 {{ selectedIds.length }} 项</span>
      <button :disabled="!selectedIds.length" @click="reviewSelected('false_positive')"><WarningOutlined /> 标记误检</button>
      <button class="danger" :disabled="!selectedIds.length" @click="reviewSelected('deleted')"><DeleteOutlined /> 删除</button>
      <button :disabled="!selectedIds.length" @click="reviewSelected('unreviewed')"><UndoOutlined /> 恢复</button>
    </div>
    <div v-if="viewMode === 'list'" class="result-list">
      <article v-for="(item, displayIndex) in displayedItems" :key="item.id" :data-result-id="item.id" class="result-card" :class="{ selected: selectedId === item.id, corrected: item.corrected }" @click="emit('select', item.id)">
        <a-checkbox class="result-select" :checked="selectedIds.includes(item.id)" @click.stop @update:checked="toggleSelected(item.id, $event)" />
        <div class="result-index">{{ String(displayIndex + 1).padStart(2, '0') }}</div>
        <div class="result-main">
          <p>{{ item.corrected || item.text }}</p>
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
    <div v-else class="result-table-scroll">
      <table class="result-table">
        <thead><tr><th scope="col">序号</th><th scope="col">端子号</th><th scope="col">线缆编号</th><th scope="col">人工确认</th><th scope="col">备注</th></tr></thead>
        <tbody>
          <tr v-for="(item, index) in displayedItems" :key="item.id" :class="{ selected: selectedId === item.id }" :data-result-id="item.id" @click="emit('select', item.id)">
            <td class="table-index"><a-checkbox :checked="selectedIds.includes(item.id)" :aria-label="`选择第 ${index + 1} 条结果`" @click.stop @update:checked="toggleSelected(item.id, $event)" /> {{ String(index + 1).padStart(2, '0') }}</td>
            <td><input v-model="draftFor(item).terminalNumber" maxlength="500" placeholder="填写端子号" :aria-label="`第 ${index + 1} 行端子号`" :class="{ 'save-error': errors[fieldKey(item, 'terminalNumber')] }" @click.stop @blur="saveField(item, 'terminalNumber')" @keydown.enter.prevent="($event.target as HTMLInputElement).blur()" /><button v-if="errors[fieldKey(item, 'terminalNumber')]" class="retry-save" :title="errors[fieldKey(item, 'terminalNumber')]" @click.stop="saveField(item, 'terminalNumber')">重试</button></td>
            <td><input v-model="draftFor(item).cable" maxlength="500" :aria-label="`第 ${index + 1} 行线缆编号`" :class="{ 'save-error': errors[fieldKey(item, 'cable')] }" @click.stop @blur="saveField(item, 'cable')" @keydown.enter.prevent="($event.target as HTMLInputElement).blur()" /><button v-if="errors[fieldKey(item, 'cable')]" class="retry-save" :title="errors[fieldKey(item, 'cable')]" @click.stop="saveField(item, 'cable')">重试</button></td>
            <td class="confirm-cell"><a-checkbox v-model:checked="draftFor(item).manualConfirmed" :aria-label="`第 ${index + 1} 行人工确认`" @click.stop @change="saveField(item, 'manualConfirmed')" /> <span v-if="saving[fieldKey(item, 'manualConfirmed')]">保存中</span><button v-if="errors[fieldKey(item, 'manualConfirmed')]" class="retry-save" @click.stop="saveField(item, 'manualConfirmed')">重试</button></td>
            <td><input v-model="draftFor(item).tableNote" maxlength="1000" placeholder="填写备注" :aria-label="`第 ${index + 1} 行备注`" :class="{ 'save-error': errors[fieldKey(item, 'tableNote')] }" @click.stop @blur="saveField(item, 'tableNote')" @keydown.enter.prevent="($event.target as HTMLInputElement).blur()" /><button v-if="errors[fieldKey(item, 'tableNote')]" class="retry-save" :title="errors[fieldKey(item, 'tableNote')]" @click.stop="saveField(item, 'tableNote')">重试</button></td>
          </tr>
        </tbody>
      </table>
      <a-empty v-if="!displayedItems.length" description="没有匹配的识别结果" />
    </div>
    <footer class="results-footer">
      <button v-if="canUndoReview" class="footer-undo-btn" @click="emit('undo')"><UndoOutlined /> 撤销上一次结果操作</button>
      <span class="dataset-review-hint">确认当前任务的文字和标注框已全部复核</span>
      <a-button type="primary" :loading="datasetReviewSaving" :disabled="datasetReviewed || datasetReviewDisabled" @click="emit('complete-review')"><span style="color: #fff">{{ datasetReviewed ? '已复核' : '复核完成' }}</span></a-button>
    </footer>
  </aside>
</template>
