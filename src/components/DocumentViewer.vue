<script setup lang="ts">
import { CheckCircleFilled, FileTextOutlined, LeftOutlined, RightOutlined, ZoomInOutlined, ZoomOutOutlined } from '@ant-design/icons-vue'
import type { MockPage } from '../mock'
import BBoxLayer from './BBoxLayer.vue'

defineProps<{
  pages: MockPage[]
  page: MockPage
  currentPage: number
  selectedId: string
  zoom: number
  jobState: 'ready' | 'running' | 'done'
  progress: number
}>()

const emit = defineEmits<{
  pageChange: [page: number]
  select: [id: string]
  zoomChange: [zoom: number]
}>()
</script>

<template>
  <aside class="page-rail">
    <div class="rail-title"><FileTextOutlined /> 页面 <span>{{ pages.length }}</span></div>
    <button v-for="p in pages" :key="p.no" class="page-thumb" :class="{ active: currentPage === p.no }" @click="emit('pageChange', p.no)">
      <div class="mini-paper"><div class="mini-brand"></div><i></i><i></i><i></i><i></i><i></i></div>
      <div><b>第 {{ p.no }} 页</b><small>{{ p.label }}</small></div>
      <CheckCircleFilled v-if="jobState === 'done'" />
    </button>
    <div class="job-summary">
      <span class="status-dot"></span>
      <div><b>{{ jobState === 'running' ? '正在识别' : '识别已完成' }}</b><small>{{ jobState === 'running' ? `${progress}% · 正在处理页面` : '用时 1.8 秒' }}</small></div>
    </div>
  </aside>

  <section class="canvas-panel">
    <div class="canvas-toolbar">
      <div class="page-stepper">
        <button :disabled="currentPage === 1" @click="emit('pageChange', currentPage - 1)"><LeftOutlined /></button>
        <span>{{ currentPage }} / {{ pages.length }}</span>
        <button :disabled="currentPage === pages.length" @click="emit('pageChange', currentPage + 1)"><RightOutlined /></button>
      </div>
      <div class="document-name">{{ page.label }} <span>·</span> 原始尺寸 2480 × 3508 px</div>
      <div class="zoom-control">
        <button @click="emit('zoomChange', Math.max(.55, zoom - .1))"><ZoomOutOutlined /></button>
        <span>{{ Math.round(zoom * 100) }}%</span>
        <button @click="emit('zoomChange', Math.min(1.15, zoom + .1))"><ZoomInOutlined /></button>
        <button @click="emit('zoomChange', .82)">适应窗口</button>
      </div>
    </div>
    <div class="canvas-viewport">
      <div class="page-canvas" :style="{ width: `${700 * zoom}px`, height: `${760 * zoom}px` }">
        <BBoxLayer :page="page" :selected-id="selectedId" :zoom="zoom" @select="emit('select', $event)" />
      </div>
    </div>
    <div class="legend"><span><i class="green"></i> ≥95%</span><span><i class="amber"></i> 90–95%</span><span><i class="red"></i> &lt;90%</span><em>点击检测框可定位右侧结果</em></div>
  </section>
</template>
