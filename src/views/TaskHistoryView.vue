<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { DeleteOutlined, ExportOutlined, EyeOutlined, FileTextOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { Modal, message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { deleteTask as deleteOcrTask, exportTaskResults, getTasks } from '../api/ocr'
import { filterAndSortTasks } from '../taskFilters'
import { datasetButton, getDatasetStatuses, saveDatasetEntry, type DatasetStatus } from '../api/dataset'
import { isAxiosError } from 'axios'
import { runDatasetBatch, type BatchOutcome } from '../datasetBatch'
import type { OcrTask, TaskStatus, TaskTimeOrder } from '../types/task'
import { useAppSettings } from '../composables/useAppSettings'

const router = useRouter()
const { settings } = useAppSettings()
const tasks = ref<OcrTask[]>([])
const datasetStatuses = ref<Record<string, DatasetStatus>>({})
const savingDatasetIds = ref<string[]>([])
const selectedTaskIds = ref<string[]>([])
const batchSaving = ref(false)
const batchOutcomes = ref<BatchOutcome[]>([])
const batchTotal = ref(0)
const rowSelection = computed(() => ({
  selectedRowKeys: selectedTaskIds.value,
  preserveSelectedRowKeys: true,
  onChange: (keys: (string | number)[]) => { selectedTaskIds.value = keys.map(String) },
  getCheckboxProps: (task: OcrTask) => ({ disabled: batchSaving.value || savingDatasetIds.value.length > 0 || datasetButton(datasetStatuses.value[task.id]).disabled }),
}))

async function enterSelectedDatasets() {
  if (batchSaving.value || savingDatasetIds.value.length || !selectedTaskIds.value.length) return
  batchSaving.value = true
  batchOutcomes.value = []
  const selected = [...selectedTaskIds.value]
  batchTotal.value = selected.length
  try {
    await refreshDatasetStatuses()
    const jobs = selected.map(id => datasetStatuses.value[id]).filter((item): item is DatasetStatus => Boolean(item))
    savingDatasetIds.value = selected
    await runDatasetBatch(jobs, (outcome, updated) => {
      batchOutcomes.value.push(outcome)
      if (updated) datasetStatuses.value[outcome.jobId] = updated
      if (outcome.success) selectedTaskIds.value = selectedTaskIds.value.filter(id => id !== outcome.jobId)
    })
    const success = batchOutcomes.value.filter(item => item.success).length
    message.info(`批量入库完成：成功 ${success}，未入库 ${selected.length - success}`)
  } catch {
    message.error('复核状态刷新失败，尚未开始批量入库')
  } finally {
    try { await refreshDatasetStatuses() } catch { message.warning('状态刷新失败，可点击刷新状态重试') }
    savingDatasetIds.value = []
    batchSaving.value = false
  }
}

async function refreshDatasetStatuses() {
  const statuses = await getDatasetStatuses(tasks.value.map(task => task.id))
  datasetStatuses.value = Object.fromEntries(statuses.map(status => [status.job_id, status]))
  selectedTaskIds.value = selectedTaskIds.value.filter(id => !datasetButton(datasetStatuses.value[id]).disabled)
}

async function enterDataset(task: OcrTask) {
  if (batchSaving.value) return
  const status = datasetStatuses.value[task.id]
  if (datasetButton(status, savingDatasetIds.value.includes(task.id)).disabled || status?.reviewed_version == null) return
  savingDatasetIds.value.push(task.id)
  try {
    const saved = await saveDatasetEntry(task.id, status.reviewed_version)
    datasetStatuses.value[task.id] = saved
    if (saved.state === 'saved') selectedTaskIds.value = selectedTaskIds.value.filter(id => id !== task.id)
    message.success(saved.state === 'saved' ? '训练数据已入库' : '已保存复核版本，当前修改需要重新复核')
  } catch (error) {
    message.error(isAxiosError(error) ? error.response?.data?.error?.message || '入库未完成，请刷新状态后重试' : '入库失败，请重试')
    try { await refreshDatasetStatuses() } catch { datasetStatuses.value = {} }
  } finally {
    savingDatasetIds.value = savingDatasetIds.value.filter(id => id !== task.id)
  }
}
const exportingTaskId = ref<string>()
const deletingTaskId = ref<string>()
const search = ref('')
const status = ref<TaskStatus | 'all'>('all')
const timeOrder = ref<TaskTimeOrder>('newest')
const visibleTasks = computed(() => filterAndSortTasks(tasks.value, search.value, status.value, timeOrder.value))

onMounted(async () => {
  try {
    tasks.value = await getTasks()
    try { await refreshDatasetStatuses() } catch { message.error('入库状态加载失败，请点击刷新状态重试') }
  } catch {
    message.error('任务查询失败，请确认 FastAPI 服务已启动')
  }
})

const columns = [
  { title: '任务 / 文件', key: 'task', width: 270 },
  { title: '创建时间', dataIndex: 'createdAt', key: 'createdAt', width: 150 },
  { title: 'OCR 模型', dataIndex: 'modelName', key: 'modelName', width: 180 },
  { title: '页数', dataIndex: 'pageCount', key: 'pageCount', width: 65, align: 'center' as const },
  { title: '状态', dataIndex: 'status', key: 'status', width: 95 },
  { title: '识别耗时', dataIndex: 'durationMs', key: 'durationMs', width: 90 },
  { title: '识别区域', dataIndex: 'regionCount', key: 'regionCount', width: 85, align: 'center' as const },
  { title: '待复核', dataIndex: 'reviewCount', key: 'reviewCount', width: 75, align: 'center' as const },
  { title: '数据复核', key: 'dataset', width: 100 },
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
  exportingTaskId.value = task.id
  try {
    await exportTaskResults(task.id, task.name, settings.value.defaultExportMode)
    message.success(`${task.name} 已导出`)
  } catch {
    message.error('导出失败，请确认任务已完成并重试')
  } finally {
    exportingTaskId.value = undefined
  }
}

function deleteTask(task: OcrTask) {
  Modal.confirm({
    title: '删除任务？',
    content: `确认删除“${task.name}”吗？`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    icon: h(DeleteOutlined),
    onOk: async () => {
      deletingTaskId.value = task.id
      try {
        await deleteOcrTask(task.id)
        tasks.value = tasks.value.filter((item) => item.id !== task.id)
        selectedTaskIds.value = selectedTaskIds.value.filter(id => id !== task.id)
        message.success('任务已删除')
      } catch {
        message.error('任务删除失败，请稍后重试')
        throw new Error('Task deletion failed')
      } finally {
        deletingTaskId.value = undefined
      }
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
        <a-button size="small" :disabled="batchSaving" @click="refreshDatasetStatuses().catch(() => message.error('状态刷新失败'))">刷新状态</a-button>
      </div>

      <div class="dataset-batch-bar">
        <span>已选 {{ selectedTaskIds.length }} 项（支持跨页选择，仅已复核任务可选）</span>
        <a-button type="primary" :loading="batchSaving" :disabled="!selectedTaskIds.length || savingDatasetIds.length > 0" @click="enterSelectedDatasets">批量入库</a-button>
        <a-button :disabled="batchSaving || !selectedTaskIds.length" @click="selectedTaskIds = []">清空选择</a-button>
        <span v-if="batchSaving">已处理 {{ batchOutcomes.length }} / {{ batchTotal }}</span>
      </div>
      <div v-if="batchOutcomes.some(item => !item.success)" class="dataset-batch-errors" role="status">
        <div v-for="item in batchOutcomes.filter(value => !value.success)" :key="item.jobId">{{ tasks.find(task => task.id === item.jobId)?.name || item.jobId }}：{{ item.message }}</div>
      </div>

      <div class="task-table-wrap">
        <a-table :columns="columns" :data-source="visibleTasks" :row-selection="rowSelection" row-key="id" :pagination="{ pageSize: 8, showSizeChanger: false }" :scroll="{ x: 1350, y: 'calc(100vh - 390px)' }" size="middle">
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
            <template v-else-if="column.key === 'dataset'">
              <a-tag :color="datasetStatuses[record.id]?.state === 'saved' ? 'success' : datasetStatuses[record.id]?.state === 'unreviewed' ? 'default' : 'processing'">{{ !datasetStatuses[record.id] ? '待加载' : datasetStatuses[record.id]?.state === 'saved' ? '已入库' : datasetStatuses[record.id]?.state === 'unreviewed' ? '未复核' : '已复核' }}</a-tag>
            </template>
            <template v-else-if="column.key === 'actions'">
              <div class="task-actions">
                <button @click="openTask(record)"><EyeOutlined /> 查看</button>
                <button :disabled="!['succeeded', 'partial'].includes(record.status)" @click="openTask(record, true)">继续复核</button>
                <button :title="datasetButton(datasetStatuses[record.id], savingDatasetIds.includes(record.id)).hint" :disabled="datasetButton(datasetStatuses[record.id], savingDatasetIds.includes(record.id)).disabled" @click="enterDataset(record)">{{ datasetButton(datasetStatuses[record.id], savingDatasetIds.includes(record.id)).label }}</button>
                <button :disabled="!record.regionCount || exportingTaskId === record.id" @click="exportTask(record)"><ExportOutlined /> {{ exportingTaskId === record.id ? '导出中' : '导出' }}</button>
                <button class="danger" :disabled="batchSaving || savingDatasetIds.includes(record.id) || deletingTaskId === record.id" @click="deleteTask(record)"><DeleteOutlined /></button>
              </div>
            </template>
          </template>
          <template #emptyText><a-empty description="没有匹配的任务" /></template>
        </a-table>
      </div>
    </section>
  </main>
</template>
