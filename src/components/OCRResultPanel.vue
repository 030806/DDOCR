<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { CommentOutlined, DeleteOutlined, EditOutlined, SearchOutlined, UndoOutlined, WarningOutlined } from '@ant-design/icons-vue'
import { Modal } from 'ant-design-vue'
import type { OcrItem, OcrPage, OcrReviewStatus } from '../types/ocr'
import type { ExportMode } from '../exportResults'
import type { ResultViewMode } from '../ocrLayout'
import { filterOcrItems } from '../resultVisibility'
import OcrLayoutView from './OcrLayoutView.vue'

const props = defineProps<{
  page: OcrPage
  pages: OcrPage[]
  selectedId: string
  modelLabel: string
  viewMode: ResultViewMode
  lowConfidenceThreshold: number
  showConfidence: boolean
  canUndoReview: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  correct: [item: OcrItem]
  comment: [item: OcrItem]
  export: [mode: ExportMode]
  review: [ids: string[], status: OcrReviewStatus]
  undo: []
  'visible-change': [ids: string[]]
  'update:viewMode': [mode: ResultViewMode]
}>()

const search = ref('')
const lowOnly = ref(false)
const minimumConfidencePercent = ref(0)
const showFalsePositive = ref(false)
const showDeleted = ref(false)
const selectedIds = ref<string[]>([])
const filteredItems = computed(() => filterOcrItems(props.page.items, {
  search: search.value,
  minimumConfidence: minimumConfidencePercent.value / 100,
  lowOnly: lowOnly.value,
  lowConfidenceThreshold: props.lowConfidenceThreshold,
  showFalsePositive: showFalsePositive.value,
  showDeleted: showDeleted.value,
}))
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

watch(filteredItems, items => emit('visible-change', items.map(item => item.id)), { immediate: true })
watch(() => props.page.no, () => { selectedIds.value = [] })
</script>

<template>
  <aside class="results-panel">
    <div class="results-head">
      <div class="results-heading"><h2>识别结果</h2><span>{{ page.items.length }} 个文本区域</span></div>
      <div class="result-view-switch" aria-label="识别结果展示模式">
        <button :class="{ active: viewMode === 'list' }" @click="emit('update:viewMode', 'list')">列表</button>
        <button :class="{ active: viewMode === 'layout' }" @click="emit('update:viewMode', 'layout')">原位布局</button>
      </div>
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
      <article v-for="item in filteredItems" :key="item.id" :data-result-id="item.id" class="result-card" :class="{ selected: selectedId === item.id, corrected: item.corrected }" @click="emit('select', item.id)">
        <a-checkbox class="result-select" :checked="selectedIds.includes(item.id)" @click.stop @update:checked="toggleSelected(item.id, $event)" />
        <div class="result-index">{{ String(page.items.indexOf(item) + 1).padStart(2, '0') }}</div>
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
      <a-empty v-if="!filteredItems.length" description="没有匹配的识别结果" />
    </div>
    <OcrLayoutView
      v-else
      :items="filteredItems"
      :selected-id="selectedId"
      :show-confidence="showConfidence"
      :source-width="page.sourceWidth"
      :source-height="page.sourceHeight"
      @select="emit('select', $event)"
      @correct="emit('correct', $event)"
      @comment="emit('comment', $event)"
    />
    <footer class="results-footer">
      <button v-if="canUndoReview" class="footer-undo-btn" @click="emit('undo')"><UndoOutlined /> 撤销上一次结果操作</button>
      <span>模型 {{ modelLabel }}</span>
    </footer>
  </aside>
</template>
