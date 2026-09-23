<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { isAxiosError } from 'axios'
import { associateSide, getTerminalTask, type Side, type TerminalTask } from '../api/terminal'
import { getTasks, getTask } from '../api/ocr'
import type { OcrTask } from '../types/task'
import { readPendingSides, terminalSidePath, writePendingSides } from '../terminalState'
import TerminalMergedPanel from '../components/TerminalMergedPanel.vue'

const route = useRoute()
const router = useRouter()
const task = ref<TerminalTask>()
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const records = ref<OcrTask[]>([])
const selectedRecord = ref<string>()
const selectedPage = ref(1)
const recordPageCount = ref(1)
const picker = ref(false)
const candidateReady = ref(false)
const workspace = ref<{ prepareSideChange: () => Promise<boolean> }>()
const active = computed(() => route.params.side === 'right' ? 'right' : route.path.endsWith('/merged') ? 'merged' : 'left')
const side = computed<Side>(() => active.value === 'right' ? 'right' : 'left')
const taskId = computed(() => String(route.params.terminalId))
const pending = ref(readPendingSides(taskId.value))
let epoch = 0
let disposed = false
let navigatingAfterBind = false
function navigationGuard() {
  if (busy.value && !navigatingAfterBind) { message.info('请等待关联操作完成'); return false }
  return true
}
onBeforeRouteLeave(navigationGuard)
onBeforeRouteUpdate(navigationGuard)
onBeforeUnmount(() => { disposed = true; epoch++ })
function showError(e: unknown) {
  error.value = isAxiosError(e) ? e.response?.data?.error?.message || '操作失败，请重试' : '操作失败，请重试'
  message.error(error.value)
}
async function load() {
  const current = ++epoch
  loading.value = true
  try {
    const value = await getTerminalTask(taskId.value)
    if (current !== epoch || disposed) return
    task.value = value
    error.value = ''
  } catch (e) { if (current === epoch && !disposed) showError(e) }
  finally { if (current === epoch && !disposed) loading.value = false }
}
watch(taskId, id => { pending.value = readPendingSides(id); task.value = undefined })
watch(() => route.fullPath, () => {
  if (route.query.attach === '1' && typeof route.params.taskId === 'string' && route.params.taskId) {
    pending.value[side.value] = route.params.taskId
    writePendingSides(taskId.value, pending.value)
  }
  void load()
}, { immediate: true })
watch([() => route.params.taskId, () => route.params.side], () => { candidateReady.value = false })
async function navigate(tab: string) {
  if (!task.value || busy.value) return
  if (tab === 'merged') { await router.push(`/terminal-tasks/${taskId.value}/merged`); return }
  const target = tab as Side
  const candidate = pending.value[target]
  const association = task.value.sides[target]
  await router.push({ path: terminalSidePath(taskId.value, target, candidate || association?.job_id),
    query: candidate ? { attach: '1' } : association ? { page: association.page_no } : {} })
}
function sideLabel(target: Side) {
  if (pending.value[target]) return '待关联'
  return task.value?.sides[target]?.status === 'unavailable' ? '来源不可用' : task.value?.sides[target] ? '已识别' : '待上传'
}
async function openPicker() {
  busy.value = true
  try {
    records.value = (await getTasks()).filter(t => ['succeeded', 'partial_success'].includes(t.jobStatus || ''))
    selectedRecord.value = undefined
    selectedPage.value = 1
    picker.value = true
  } catch (e) { showError(e) }
  finally { busy.value = false }
}
async function bind(jobId: string, pageNo: number) {
  if (!task.value || busy.value) return
  if (workspace.value && !await workspace.value.prepareSideChange()) return
  epoch++
  loading.value = false
  busy.value = true
  const targetSide = side.value
  try {
    task.value = await associateSide(task.value, targetSide, jobId, pageNo)
    delete pending.value[targetSide]
    writePendingSides(taskId.value, pending.value)
    picker.value = false
    navigatingAfterBind = true
    await router.replace({ path: terminalSidePath(taskId.value, targetSide, jobId), query: { page: pageNo } })
    message.success('已关联识别结果')
  } catch (e) { showError(e); await load() }
  finally { navigatingAfterBind = false; busy.value = false }
}
async function completed(jobId: string, pageCount: number) {
  if (jobId !== route.params.taskId) return
  candidateReady.value = true
  recordPageCount.value = pageCount
  selectedPage.value = Number(route.query.page) || task.value?.sides[side.value]?.page_no || 1
  if (route.query.attach === '1' && pageCount === 1) {
    if (!task.value) await load()
    await bind(jobId, 1)
  }
}
async function useCurrent() {
  if (typeof route.params.taskId !== 'string') return
  // Recheck the server before associating a candidate, including after refresh.
  try {
    const candidate = await getTask(route.params.taskId)
    if (!['succeeded', 'partial_success'].includes(candidate.jobStatus || '')) { message.info('请等待识别完成'); return }
    await bind(candidate.id, selectedPage.value)
  } catch (e) { showError(e) }
}
</script>
<template>
  <main class="terminal-shell">
    <div class="terminal-heading">
      <strong>{{ task?.name || '正在加载端子排任务…' }}</strong>
      <a-tabs :active-key="active" class="terminal-tabs" @change="navigate(String($event))">
        <a-tab-pane key="left" :tab="`左侧 · ${sideLabel('left')}`" />
        <a-tab-pane key="right" :tab="`右侧 · ${sideLabel('right')}`" />
        <a-tab-pane key="merged" :tab="`合并结果 · ${task?.rows.filter(r => !r.confirmed).length || 0} 行待确认`" />
      </a-tabs>
      <a-button @click="router.push('/terminal-tasks')">所有端子排任务</a-button>
    </div>
    <a-alert v-if="error" type="error" :message="error" show-icon><template #action><a-button @click="load">刷新重试</a-button></template></a-alert>
    <div v-if="active === 'merged' && task" class="terminal-merge-container">
      <div v-if="loading" class="terminal-loading"><a-spin /><span>正在更新合并结果…</span></div>
      <TerminalMergedPanel :task="task" :inert="loading" @updated="task = $event" @refresh="load" />
    </div>
    <template v-else-if="task && active !== 'merged'">
      <div class="terminal-toolbar">
        <span>正在处理：{{ side === 'left' ? '左侧' : '右侧' }}（端子排实际方位）</span>
        <a-button :disabled="busy" @click="openPicker">关联已有识别结果</a-button>
        <template v-if="candidateReady">
          <span>关联页</span><a-input-number v-model:value="selectedPage" :min="1" :max="recordPageCount" :precision="0" />
          <a-button :loading="busy" @click="useCurrent">采用当前结果</a-button>
        </template>
        <a-button :disabled="busy" @click="navigate(side === 'left' ? 'right' : 'merged')">{{ side === 'left' ? '保存并查看右侧' : '查看合并结果' }}</a-button>
        <span v-if="route.query.attach === '1'">新识别完成后关联；原结果保留至采用成功</span>
      </div>
      <RouterView v-slot="{ Component }"><component :is="Component" ref="workspace" :key="`${side}:${route.params.taskId || 'new'}`" @completed="completed" /></RouterView>
    </template>
    <a-modal v-model:open="picker" title="关联已有单侧识别结果" ok-text="关联结果" cancel-text="取消" :confirm-loading="busy" :ok-button-props="{ disabled: !selectedRecord }" @ok="selectedRecord && bind(selectedRecord, selectedPage)">
      <p>请选择该端子排对应侧的识别记录。多页文件需指定页码。</p>
      <a-select v-model:value="selectedRecord" style="width:100%" show-search option-filter-prop="label" :options="records.map(r => ({ value: r.id, label: `${r.name} · ${r.fileName} · ${r.createdAt}` }))" @change="selectedPage = 1" />
      <p>页码 <a-input-number v-model:value="selectedPage" :min="1" :max="records.find(r => r.id === selectedRecord)?.pageCount || 1" :precision="0" /></p>
      <p>替换关联会重新计算对应关系，并将合并确认重置为待确认。</p>
    </a-modal>
  </main>
</template>
