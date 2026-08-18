<script setup lang="ts">
import { CheckCircleFilled, CheckOutlined, CloseOutlined, EditOutlined, FileTextOutlined, LeftOutlined, RedoOutlined, RightOutlined, SaveOutlined, UndoOutlined, ZoomInOutlined, ZoomOutOutlined } from '@ant-design/icons-vue'
import type { OcrPage, OcrPolygon } from '../types/ocr'
import BBoxLayer from './BBoxLayer.vue'

defineProps<{
  pages: OcrPage[]
  page: OcrPage
  currentPage: number
  selectedId: string
  zoom: number
  jobState: 'ready' | 'running' | 'done'
  progress: number
  editMode?: boolean
  canUndo?: boolean
  canRedo?: boolean
  hasUnsavedChanges?: boolean
  hasPendingGeometry?: boolean
}>()

const emit = defineEmits<{
  pageChange: [page: number]
  select: [id: string]
  zoomChange: [zoom: number]
  editToggle: []
  undo: []
  redo: []
  save: []
  polygonPreview: [id: string, polygon: OcrPolygon]
  geometryConfirm: []
  geometryCancel: []
  createBbox: [bbox: OcrPage['items'][number]['bbox']]
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
      <div class="document-name">{{ page.label }} <span>·</span> 原始尺寸 {{ page.sourceWidth || 2480 }} × {{ page.sourceHeight || 3508 }} px</div>
      <div class="zoom-control">
        <button :class="{ active: editMode }" @click="emit('editToggle')"><EditOutlined /> {{ editMode ? '退出编辑' : '编辑框' }}</button>
        <button @click="emit('zoomChange', Math.max(.55, zoom - .1))"><ZoomOutOutlined /></button>
        <span>{{ Math.round(zoom * 100) }}%</span>
        <button :disabled="zoom >= 3" @click="emit('zoomChange', Math.min(3, Number((zoom + .1).toFixed(2))))"><ZoomInOutlined /></button>
        <button @click="emit('zoomChange', .82)">适应窗口</button>
      </div>
    </div>
    <div v-if="editMode" class="edit-action-bar">
      <span class="edit-action-title"><EditOutlined /> 检测框编辑</span>
      <button type="button" :disabled="!canUndo" title="撤销" @click="emit('undo')"><UndoOutlined /> 撤销</button>
      <button type="button" :disabled="!canRedo" title="重做" @click="emit('redo')"><RedoOutlined /> 重做</button>
      <span v-if="hasPendingGeometry" class="geometry-pending-tip">当前框待确认</span>
      <button type="button" :disabled="!hasPendingGeometry" title="确认当前框" @click.stop="emit('geometryConfirm')"><CheckOutlined /> 确认本框</button>
      <button type="button" :disabled="!hasPendingGeometry" title="取消当前框修改" @click.stop="emit('geometryCancel')"><CloseOutlined /> 取消调整</button>
      <button type="button" :disabled="!hasUnsavedChanges || hasPendingGeometry" title="保存全部修改" @click.stop="emit('save')"><SaveOutlined /> 保存全部</button>
      <span class="edit-action-help">拖动框体移动，拖动四角调整形状</span>
    </div>
    <div class="canvas-viewport">
      <div class="page-canvas" :style="{ width: `${700 * zoom}px`, height: `${760 * zoom}px` }">
        <BBoxLayer :page="page" :selected-id="selectedId" :zoom="zoom" :edit-mode="editMode" @select="emit('select', $event)" @polygon-preview="(id, polygon) => emit('polygonPreview', id, polygon)" @create="emit('createBbox', $event)" />
      </div>
    </div>
    <div class="legend"><span><i class="neutral"></i> 普通检测框</span><span><i class="selected"></i> 当前选中</span><em>点击检测框可定位右侧结果</em></div>
  </section>
</template>
