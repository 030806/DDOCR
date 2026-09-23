<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { isAxiosError } from 'axios'
import { exportTerminalTask, linkTerminalRows, reviewTerminalRows, type Side, type TerminalRow, type TerminalTask } from '../api/terminal'
import { filterTerminalRows, terminalRowStatus, terminalSidePath } from '../terminalState'

const props = defineProps<{ task: TerminalTask }>()
const emit = defineEmits<{ updated: [task: TerminalTask]; refresh: [] }>()
const router = useRouter()
const filter = ref('all')
const selected = ref<string[]>([])
const notes = reactive<Record<string, string>>({})
const busy = ref(false)
const linkOpen = ref(false)
const leftId = ref<string>()
const rightId = ref<string>()
const visible = computed(() => filterTerminalRows(props.task.rows, filter.value))
const hasDrafts = computed(() => props.task.rows.some(r => notes[r.id] !== undefined && notes[r.id] !== r.note))
function beforeUnload(event: BeforeUnloadEvent) {
  if (hasDrafts.value || busy.value) { event.preventDefault(); event.returnValue = '' }
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
function guard() {
  if (busy.value || hasDrafts.value) { message.warning('请先保存备注或等待操作完成'); return false }
  return true
}
onBeforeRouteLeave(guard)
onBeforeRouteUpdate(guard)
function error(e: unknown) {
  message.error(isAxiosError(e) ? e.response?.data?.error?.message || '操作失败，请重试' : '操作失败，请重试')
}
async function review(rows: TerminalRow[], confirmed?: boolean) {
  if (busy.value || !rows.length) return
  busy.value = true
  try {
    const task = await reviewTerminalRows(props.task, rows.map(r => ({ id: r.id, confirmed: confirmed ?? r.confirmed, note: notes[r.id] ?? r.note })))
    rows.forEach(r => delete notes[r.id])
    selected.value = []
    emit('updated', task)
  } catch (e) { error(e) }
  finally { busy.value = false }
}
async function link(left: string | null, right: string | null) {
  if (!guard()) return
  busy.value = true
  try {
    emit('updated', await linkTerminalRows(props.task, left, right))
    linkOpen.value = false
    selected.value = []
  } catch (e) { error(e) }
  finally { busy.value = false }
}
function openLink(row: TerminalRow) {
  leftId.value = row.left?.id
  rightId.value = row.right?.id
  linkOpen.value = true
}
function options(side: Side) {
  return props.task.rows.flatMap(r => r[side] ? [{ value: r[side]!.id, label: `${r[side]!.terminal_number || '编号未填写'} · ${r[side]!.text}` }] : [])
}
function source(row: TerminalRow, side: Side) {
  const value = row[side]
  if (!value || !guard()) return
  void router.push({ path: terminalSidePath(props.task.id, side, value.job_id), query: { page: value.page_no, result: value.id } })
}
async function download(scope: 'all' | 'confirmed') {
  if (!guard()) return
  busy.value = true
  try { await exportTerminalTask(props.task, scope) }
  catch (e) { error(e) }
  finally { busy.value = false }
}
function refresh() {
  if (busy.value) return
  emit('refresh')
}
function toggle(id: string, checked: boolean) {
  selected.value = checked ? [...new Set([...selected.value, id])] : selected.value.filter(x => x !== id)
}
</script>
<template>
  <section class="terminal-merged">
    <div class="terminal-toolbar">
      <a-segmented v-model:value="filter" :options="[{ label: '全部', value: 'all' }, { label: '待处理', value: 'pending' }, { label: '已确认', value: 'confirmed' }]" />
      <span>{{ task.rows.length }} 行 · {{ task.rows.filter(r => r.conflict).length }} 行冲突 · {{ task.rows.filter(r => !r.left || !r.right).length }} 行缺侧</span>
      <a-button :disabled="busy || !selected.length" @click="review(task.rows.filter(r => selected.includes(r.id)), true)">确认所选</a-button>
      <a-button :disabled="busy" @click="refresh">刷新结果</a-button>
      <a-button :disabled="busy || hasDrafts || task.rows.some(r => r.conflict)" @click="download('all')">导出全部</a-button>
      <a-button :disabled="busy || hasDrafts || task.rows.some(r => r.conflict)" @click="download('confirmed')">导出已确认</a-button>
    </div>
    <p>按端子编号对应；空编号或重复编号需处理后导出。缺侧可核对后确认。点击线缆号查看单侧原图。</p>
    <div class="terminal-table-scroll">
      <table class="terminal-table">
        <thead><tr><th><a-checkbox :checked="visible.length > 0 && visible.every(r => selected.includes(r.id))" aria-label="选择全部可见行" @update:checked="selected = $event ? visible.map(r => r.id) : []" /> 序号</th><th>端子编号</th><th>左侧线缆号</th><th>右侧线缆号</th><th>人工确认</th><th>备注</th><th>状态与操作</th></tr></thead>
        <tbody><tr v-for="(row, index) in visible" :key="row.id">
          <td><a-checkbox :checked="selected.includes(row.id)" :aria-label="`选择第 ${index + 1} 行`" @update:checked="toggle(row.id, $event)" /> {{ index + 1 }}</td>
          <td>{{ row.terminal_number || '待填写' }}</td>
          <td><button v-if="row.left" class="terminal-source" @click="source(row, 'left')">{{ row.left.text }}</button><span v-else>—</span></td>
          <td><button v-if="row.right" class="terminal-source" @click="source(row, 'right')">{{ row.right.text }}</button><span v-else>—</span></td>
          <td><a-checkbox :checked="row.confirmed" :disabled="busy || row.conflict" :aria-label="`确认端子 ${row.terminal_number}`" @update:checked="review([row], $event)">{{ row.confirmed ? '已确认' : '待确认' }}</a-checkbox></td>
          <td><a-input :value="notes[row.id] ?? row.note" :disabled="busy" :maxlength="4000" :aria-label="`端子 ${row.terminal_number} 备注`" @update:value="notes[row.id] = $event" /><a-button v-if="notes[row.id] !== undefined && notes[row.id] !== row.note" size="small" :loading="busy" @click="review([row])">保存备注</a-button></td>
          <td><a-tag :color="row.conflict ? 'error' : !row.left || !row.right ? 'warning' : 'success'">{{ terminalRowStatus(row) }}</a-tag>
            <a-button size="small" :disabled="busy || hasDrafts" @click="openLink(row)">调整对应</a-button>
            <a-button v-if="row.left && row.right" size="small" :disabled="busy || hasDrafts" @click="link(row.left.id, null)">解除对应</a-button>
          </td>
        </tr></tbody>
      </table>
      <a-empty v-if="!visible.length" description="暂无符合条件的结果，请先完成单侧识别" />
    </div>
    <a-modal v-model:open="linkOpen" title="人工调整左右侧对应" ok-text="保存对应" cancel-text="取消" :confirm-loading="busy" :ok-button-props="{ disabled: !leftId && !rightId }" @ok="link(leftId || null, rightId || null)">
      <p>各选一条进行对应；只选一侧表示明确保留为单侧行。编号不同请先核对来源，合并编号使用左侧编号。</p>
      <p>左侧</p><a-select v-model:value="leftId" allow-clear show-search option-filter-prop="label" style="width:100%" :options="options('left')" />
      <p>右侧</p><a-select v-model:value="rightId" allow-clear show-search option-filter-prop="label" style="width:100%" :options="options('right')" />
    </a-modal>
  </section>
</template>
