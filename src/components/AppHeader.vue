<script setup lang="ts">
import { computed } from 'vue'
import { HistoryOutlined, SettingOutlined } from '@ant-design/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { findMockTask } from '../mock/tasks'
import UserMenu from './UserMenu.vue'

const emit = defineEmits<{ openSettings: [] }>()

const route = useRoute()
const router = useRouter()
const isTasksPage = computed(() => route.name === 'tasks')
const routeTask = computed(() => typeof route.params.taskId === 'string' ? findMockTask(route.params.taskId) : undefined)
const workspaceFile = computed(() => routeTask.value?.fileName || 'QC_Report_0714.pdf')
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
