<script setup lang="ts">
import { computed, ref } from 'vue'
import { CheckCircleFilled, CommentOutlined, EditOutlined, SearchOutlined } from '@ant-design/icons-vue'
import type { MockPage, OcrItem } from '../mock'
import type { ExportMode } from '../exportResults'
import type { ResultViewMode } from '../ocrLayout'
import OcrLayoutView from './OcrLayoutView.vue'

const props = defineProps<{
  page: MockPage
  pages: MockPage[]
  selectedId: string
  modelLabel: string
  viewMode: ResultViewMode
  lowConfidenceThreshold: number
  showConfidence: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  correct: [item: OcrItem]
  comment: [item: OcrItem]
  export: [mode: ExportMode]
  'update:viewMode': [mode: ResultViewMode]
}>()

const search = ref('')
const lowOnly = ref(false)
const filteredItems = computed(() => props.page.items.filter((item) => {
  const term = search.value.trim().toLowerCase()
  const matches = !term || (item.corrected || item.text).toLowerCase().includes(term)
  return matches && (!lowOnly.value || item.score < props.lowConfidenceThreshold)
}))
const stats = computed(() => {
  const all = props.pages.flatMap((page) => page.items)
  return { count: all.length, average: all.reduce((sum, item) => sum + item.score, 0) / all.length, low: all.filter((item) => item.score < props.lowConfidenceThreshold).length }
})

function scoreColor(score: number) {
  if (score < 0.90) return '#ef5350'
  if (score < 0.95) return '#42a5f5'
  return '#66bb6a'
}

function handleExportSelect({ key }: { key: string | number }) {
  if (key === 'simple' || key === 'full') emit('export', key)
}
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
      <button class="filter-btn" :class="{ active: lowOnly }" @click="lowOnly = !lowOnly">低置信度 <span>{{ stats.low }}</span></button>
    </div>
    <div v-if="viewMode === 'list'" class="result-list">
      <article v-for="item in filteredItems" :key="item.id" :data-result-id="item.id" class="result-card" :class="{ selected: selectedId === item.id, corrected: item.corrected }" @click="emit('select', item.id)">
        <div class="result-index">{{ String(page.items.indexOf(item) + 1).padStart(2, '0') }}</div>
        <div class="result-main">
          <p>{{ item.corrected || item.text }}</p>
          <div class="result-meta">
            <span v-if="showConfidence" :class="item.score < lowConfidenceThreshold ? 'low-score' : ''"><i :style="{ background: scoreColor(item.score) }"></i>{{ (item.score * 100).toFixed(1) }}%</span>
            <span v-if="item.corrected" class="corrected-tag">已纠正</span>
            <span v-if="item.comments.length"><CommentOutlined /> {{ item.comments.length }}</span>
          </div>
        </div>
        <div class="hover-actions">
          <button title="纠正识别文字" @click.stop="emit('correct', item)"><EditOutlined /> 纠正</button>
          <button title="添加或查看留言" @click.stop="emit('comment', item)"><CommentOutlined /> 留言</button>
        </div>
      </article>
      <a-empty v-if="!filteredItems.length" description="没有匹配的识别结果" />
    </div>
    <OcrLayoutView
      v-else
      :items="filteredItems"
      :selected-id="selectedId"
      :show-confidence="showConfidence"
      @select="emit('select', $event)"
      @correct="emit('correct', $event)"
      @comment="emit('comment', $event)"
    />
    <footer class="results-footer"><span><CheckCircleFilled /> 已完成 · Mock 数据</span><span>模型 {{ modelLabel.split('·')[1] }}</span></footer>
  </aside>
</template>
