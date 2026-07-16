<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { DeleteOutlined, ExportOutlined, EyeOutlined, FileTextOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { Modal, message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { mockTasks } from '../mock/tasks'
import { pages } from '../mock'
import { filterAndSortTasks } from '../taskFilters'
import type { OcrTask, TaskStatus, TaskTimeOrder } from '../types/task'
import { exportOcrResults } from '../exportResults'
import { useAppSettings } from '../composables/useAppSettings'

const router = useRouter()
const { settings } = useAppSettings()
const tasks = ref<OcrTask[]>([...mockTasks])
const search = ref('')
const status = ref<TaskStatus | 'all'>('all')
const timeOrder = ref<TaskTimeOrder>('newest')
const visibleTasks = computed(() => filterAndSortTasks(tasks.value, search.value, status.value, timeOrder.value))

const columns = [
  { title: '任务 / 文件', key: 'task', width: 270 },
  { title: '创建时间', dataIndex: 'createdAt', key: 'createdAt', width: 150 },
  { title: 'OCR 模型', dataIndex: 'modelName', key: 'modelName', width: 180 },
  { title: '页数', dataIndex: 'pageCount', key: 'pageCount', width: 65, align: 'center' as const },
  { title: '状态', dataIndex: 'status', key: 'status', width: 95 },
  { title: '识别耗时', dataIndex: 'durationMs', key: 'durationMs', width: 90 },
  { title: '识别区域', dataIndex: 'regionCount', key: 'regionCount', width: 85, align: 'center' as const },
  { title: '待复核', dataIndex: 'reviewCount', key: 'reviewCount', width: 75, align: 'center' as const },
  { title: '操作', key: 'actions', width: 260, fixed: 'right' as const },
]

const statusMeta: Record<TaskStatus, { label: string; color: string }> = {
  queued: { label: '排队中', color: 'default' },
  running: { label: '识别中', color: 'processing' },
  succeeded: { label: '已完成', color: 'success' },
  partial: { label: '待复核', color: 'warning' },
  failed: { label: '失败', color: 'error' },
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))
}

function formatDuration(durationMs: number | null) {
  return durationMs === null ? '—' : `${(durationMs / 1000).toFixed(1)} 秒`
}

function openTask(task: OcrTask, review = false) {
  router.push({ path: `/workspace/${task.id}`, query: review ? { action: 'review' } : undefined })
}

async function exportTask(task: OcrTask) {
  const items = pages.filter((page) => task.mockPageNumbers.includes(page.no)).flatMap((page) => page.items)
  if (!items.length) return message.warning('该 Mock 任务暂无可导出结果')
  await exportOcrResults(items, settings.value.defaultExportMode, task.mockPageNumbers[0] || 1)
  message.success(`${task.name} 已导出`)
}

function deleteTask(task: OcrTask) {
  Modal.confirm({
    title: '删除任务？',
    content: `确认删除“${task.name}”吗？该操作仅影响当前 Mock 列表。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    icon: h(DeleteOutlined),
    onOk: () => {
      tasks.value = tasks.value.filter((item) => item.id !== task.id)
      message.success('任务已删除')
    },
  })
}
</script>

<template>
  <main class="task-history-view">
    <section class="task-page-heading">
      <div><span class="section-kicker">OCR TASK ARCHIVE</span><h1>任务记录</h1><p>查看历史识别任务，继续处理待复核结果。</p></div>
      <button class="back-workspace-btn" @click="router.push('/workspace')">返回工作台</button>
    </section>

    <section class="task-list-panel">
      <div class="task-toolbar">
        <a-input v-model:value="search" class="task-search" placeholder="搜索任务名称或文件名" allow-clear>
          <template #prefix><SearchOutlined /></template>
        </a-input>
        <a-select v-model:value="status" class="task-filter" :options="[
          { value: 'all', label: '全部状态' }, { value: 'queued', label: '排队中' }, { value: 'running', label: '识别中' },
          { value: 'succeeded', label: '已完成' }, { value: 'partial', label: '待复核' }, { value: 'failed', label: '失败' },
        ]" />
        <a-select v-model:value="timeOrder" class="task-filter" :options="[{ value: 'newest', label: '创建时间：最新' }, { value: 'oldest', label: '创建时间：最早' }]" />
        <span class="task-count">共 {{ visibleTasks.length }} 个任务</span>
      </div>

      <div class="task-table-wrap">
        <a-table :columns="columns" :data-source="visibleTasks" row-key="id" :pagination="{ pageSize: 8, showSizeChanger: false }" :scroll="{ x: 1250, y: 'calc(100vh - 330px)' }" size="middle">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'task'">
              <div class="task-name-cell">
                <span class="task-file-icon"><FileTextOutlined /></span>
                <div><b>{{ record.name }}</b><small>{{ record.fileName }} · {{ record.fileType }}</small></div>
              </div>
            </template>
            <template v-else-if="column.key === 'createdAt'">{{ formatTime(record.createdAt) }}</template>
            <template v-else-if="column.key === 'status'"><a-tag :color="statusMeta[record.status as TaskStatus].color">{{ statusMeta[record.status as TaskStatus].label }}</a-tag></template>
            <template v-else-if="column.key === 'durationMs'">{{ formatDuration(record.durationMs) }}</template>
            <template v-else-if="column.key === 'reviewCount'"><b :class="{ 'review-warning': record.reviewCount }">{{ record.reviewCount }}</b></template>
            <template v-else-if="column.key === 'actions'">
              <div class="task-actions">
                <button @click="openTask(record)"><EyeOutlined /> 查看</button>
                <button :disabled="!record.reviewCount" @click="openTask(record, true)">继续复核</button>
                <button :disabled="!record.regionCount" @click="exportTask(record)"><ExportOutlined /> 导出</button>
                <button class="danger" @click="deleteTask(record)"><DeleteOutlined /></button>
              </div>
            </template>
          </template>
          <template #emptyText><a-empty description="没有匹配的任务" /></template>
        </a-table>
      </div>
    </section>
  </main>
</template>
