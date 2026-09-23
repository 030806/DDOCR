<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { createTerminalTask, listTerminalTasks, type TerminalSummary } from '../api/terminal'
import { TERMINAL_CREATE_PROMPT, terminalSidePath } from '../terminalState'
const router = useRouter()
const tasks = ref<TerminalSummary[]>([])
const name = ref('')
const busy = ref(false)
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
      <a-button @click="router.push(terminalSidePath(task.id, 'left', task.sides.left?.job_id))">打开任务</a-button>
      <a-button @click="router.push(`/terminal-tasks/${task.id}/merged`)">合并结果</a-button>
    </div>
    <a-button v-if="nextOffset !== null" :loading="busy" @click="load()">加载更多</a-button>
  </main>
</template>
