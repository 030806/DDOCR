<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { HistoryOutlined, SettingOutlined } from '@ant-design/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { getTask } from '../api/ocr'
import UserMenu from './UserMenu.vue'

const emit = defineEmits<{ openSettings: [] }>()

const route = useRoute()
const router = useRouter()
const isTasksPage = computed(() => route.name === 'tasks')
const workspaceFile = ref('暂无任务')
let taskLoadSequence = 0

watch(() => route.params.taskId, async (taskId) => {
  const sequence = ++taskLoadSequence
  if (typeof taskId !== 'string') {
    workspaceFile.value = '暂无任务'
    return
  }
  workspaceFile.value = '正在加载…'
  try {
    const task = await getTask(taskId)
    if (sequence === taskLoadSequence) workspaceFile.value = task.fileName
  } catch {
    if (sequence === taskLoadSequence) workspaceFile.value = '任务加载失败'
  }
}, { immediate: true })
</script>

<template>
  <header class="topbar">
    <button class="brand-block brand-button" @click="router.push('/workspace')">
      <span class="brand-mark"><span></span><span></span><span></span></span>
      <span><strong>矩识 OCR</strong><small>INDUSTRIAL VISION</small></span>
    </button>
    <div class="project-chip">
      <span class="pulse"></span>
      <template v-if="isTasksPage">任务记录 <b>/</b> 历史 OCR 任务</template>
      <template v-else>产线文档检测台 <b>/</b> {{ workspaceFile }}</template>
    </div>
    <nav class="top-actions">
      <button :class="{ active: isTasksPage }" @click="router.push('/tasks')"><HistoryOutlined /> 任务记录</button>
      <button @click="emit('openSettings')"><SettingOutlined /> 设置</button>
      <UserMenu />
    </nav>
  </header>
</template>
