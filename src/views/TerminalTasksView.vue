<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { isAxiosError } from 'axios'
import { createTerminalTask, deleteTerminalTask, listTerminalTasks, type TerminalSummary } from '../api/terminal'
import { TERMINAL_CREATE_PROMPT, terminalSidePath } from '../terminalState'
const router = useRouter()
const tasks = ref<TerminalSummary[]>([])
const name = ref('')
const busy = ref(false)
const deletingTaskId = ref('')
const failed = ref(false)
const nextOffset = ref<number | null>(0)
let createKey = crypto.randomUUID()
let submittedName = ''
async function load(reset = false) {
  busy.value = true
  try {
    const result = await listTerminalTasks(reset ? 0 : nextOffset.value || 0)
    tasks.value = reset ? result.items : [...tasks.value, ...result.items]
    nextOffset.value = result.next_offset
    failed.value = false
  } catch { failed.value = true; message.error('端子排任务加载失败') }
  finally { busy.value = false }
}
async function create() {
  if (!name.value.trim() || busy.value) return
  busy.value = true
  try {
    if (submittedName !== name.value.trim()) { createKey = crypto.randomUUID(); submittedName = name.value.trim() }
    const task = await createTerminalTask(name.value.trim(), createKey)
    await router.push(terminalSidePath(task.id, 'left'))
  } catch { message.error('创建失败，请重试') }
  finally { busy.value = false }
}
function confirmDelete(task: TerminalSummary) {
  if (busy.value || deletingTaskId.value) return
  Modal.confirm({
    title: '删除端子排任务？',
    content: `确认删除“${task.name}”吗？该任务将不再显示，左右侧原始 OCR 识别记录和上传文件会保留。`,
    okText: '删除', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      deletingTaskId.value = task.id
      try {
        await deleteTerminalTask(task)
        tasks.value = tasks.value.filter(item => item.id !== task.id)
        message.success('端子排任务已删除')
        await load(true)
      } catch (error) {
        if (isAxiosError(error) && error.response?.status === 409) {
          message.warning('任务已更新，请刷新后核对再删除')
          await load(true)
        } else message.error('删除端子排任务失败，请重试')
      } finally { deletingTaskId.value = '' }
    },
  })
}
onMounted(() => load(true))
</script>
<template>
  <main class="terminal-list">
    <h1>端子排任务</h1>
    <p>分别识别左右侧，按端子编号合并。每侧一次只显示一张图片。</p>
    <a-alert class="terminal-create-prompt" type="info" :message="TERMINAL_CREATE_PROMPT" show-icon />
    <div class="terminal-toolbar">
      <a-input v-model:value="name" :maxlength="200" placeholder="端子排名称，例如：控制柜 A / X1" @press-enter="create" />
      <a-button type="primary" :loading="busy" :disabled="!name.trim()" @click="create">新建端子排任务</a-button>
      <a-button @click="router.push('/tasks')">独立识别记录</a-button>
    </div>
    <a-alert v-if="failed" type="error" message="加载失败" show-icon><template #action><a-button @click="load(true)">重试</a-button></template></a-alert>
    <a-empty v-if="!tasks.length && !busy && !failed" description="尚无端子排任务" />
    <div v-for="task in tasks" :key="task.id" class="terminal-card">
      <div><strong>{{ task.name }}</strong><p>左侧：{{ task.sides.left ? task.sides.left.status === 'unavailable' ? '来源已删除' : '已识别' : '待上传' }} · 右侧：{{ task.sides.right ? task.sides.right.status === 'unavailable' ? '来源已删除' : '已识别' : '待上传' }}</p>
      <span>{{ task.row_count }} 行 · {{ task.confirmed_count }} 行已确认 · {{ task.conflict_count }} 行冲突</span></div>
      <a-button :disabled="Boolean(deletingTaskId)" @click="router.push(terminalSidePath(task.id, 'left', task.sides.left?.job_id))">打开任务</a-button>
      <a-button :disabled="Boolean(deletingTaskId)" @click="router.push(`/terminal-tasks/${task.id}/merged`)">合并结果</a-button>
      <a-button danger :loading="deletingTaskId === task.id" :disabled="busy || Boolean(deletingTaskId)" @click="confirmDelete(task)">删除</a-button>
    </div>
    <a-button v-if="nextOffset !== null" :loading="busy" @click="load()">加载更多</a-button>
  </main>
</template>
