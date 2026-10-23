<script setup lang="ts">
import { AimOutlined, CheckCircleFilled, CheckOutlined, CloseOutlined, EditOutlined, FileTextOutlined, LeftOutlined, RedoOutlined, RightOutlined, SaveOutlined, UndoOutlined, ZoomInOutlined, ZoomOutOutlined } from '@ant-design/icons-vue'
import { ref, watch } from 'vue'
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
  terminalEditMode?: boolean
  terminalDirty?: boolean
  terminalSaving?: boolean
  selectedTerminalId?: string
}>()

const railCollapsed = ref(false)
try { railCollapsed.value = localStorage.getItem('ddocr.pageRailCollapsed') === 'true' } catch { /* Storage may be unavailable. */ }
watch(railCollapsed, value => {
  try { localStorage.setItem('ddocr.pageRailCollapsed', String(value)) } catch { /* Keep the session preference. */ }
})

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
  createRegionJob: []
  terminalToggle: []
  terminalSave: []
  terminalCancel: []
  terminalDelete: []
  terminalCreate: [point: { x: number; y: number }]
  terminalSelect: [id: string]
  terminalMove: [id: string, point: { x: number; y: number }]
}>()
</script>

<template>
  <aside class="page-rail" :class="{ collapsed: railCollapsed }">
    <button class="rail-toggle" :aria-expanded="!railCollapsed" :aria-label="railCollapsed ? '展开页面栏' : '收起页面栏'" :title="railCollapsed ? '展开页面栏' : '收起页面栏'" @click="railCollapsed = !railCollapsed">
      <RightOutlined v-if="railCollapsed" /><LeftOutlined v-else /><span v-if="!railCollapsed">收起</span>
    </button>
    <div class="rail-title"><FileTextOutlined /> 页面 <span>{{ pages.length }}</span></div>
    <button v-for="p in pages" :key="p.no" class="page-thumb" :class="{ active: currentPage === p.no }" @click="emit('pageChange', p.no)">
      <div class="mini-paper"><div class="mini-brand"></div><i></i><i></i><i></i><i></i><i></i></div>
      <div><b>第 {{ p.no }} 页</b><small>{{ p.label }}</small></div>
      <CheckCircleFilled v-if="jobState === 'done'" />
    </button>
    <div class="job-summary">
      <span class="status-dot"></span>
      <div><b>{{ jobState === 'running' ? '正在识别' : '识别已完成' }}</b><small v-if="jobState === 'running'">{{ progress }}% · 正在处理页面</small></div>
    </div>
  </aside>

  <section class="canvas-panel">
    <div class="canvas-toolbar">
      <div class="page-stepper">
        <button :disabled="currentPage === 1" @click="emit('pageChange', currentPage - 1)"><LeftOutlined /></button>
        <span>{{ currentPage }} / {{ pages.length }}</span>
        <button :disabled="currentPage === pages.length" @click="emit('pageChange', currentPage + 1)"><RightOutlined /></button>
      </div>
      <div class="zoom-control">
        <button v-if="jobState === 'done'" :disabled="editMode || terminalEditMode" @click="emit('createRegionJob')"><AimOutlined /> 区域识别</button>
        <button :disabled="terminalEditMode" :class="{ active: editMode }" @click="emit('editToggle')"><EditOutlined /> {{ editMode ? '退出编辑' : '编辑框' }}</button>
        <button v-if="page.terminalPoints" :disabled="editMode || terminalSaving" :class="{ active: terminalEditMode }" @click="emit('terminalToggle')"><EditOutlined /> {{ terminalEditMode ? '退出端子编辑' : '编辑端子点' }}</button>
        <div class="zoom-buttons">
        <button @click="emit('zoomChange', Math.max(.55, zoom - .1))"><ZoomOutOutlined /></button>
        <span>{{ Math.round(zoom * 100) }}%</span>
        <button :disabled="zoom >= 3" @click="emit('zoomChange', Math.min(3, Number((zoom + .1).toFixed(2))))"><ZoomInOutlined /></button>
        <button @click="emit('zoomChange', .82)">适应窗口</button>
        </div>
      </div>
    </div>
      <div class="document-name" :title="page.label">{{ page.label }} <span>·</span> 原始尺寸 {{ page.sourceWidth || 2480 }} × {{ page.sourceHeight || 3508 }} px
        <span v-if="page.terminalPoints"> · 端子对 {{ page.terminalPoints.length }} 个<span v-if="page.terminalModelCount !== null && page.terminalModelCount !== undefined && page.terminalModelCount !== page.terminalPoints.length">（模型原始 {{ page.terminalModelCount }} 个）</span></span>
        <span v-else-if="page.terminalError"> · 端子检测不可用</span>
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
    <div v-if="terminalEditMode" class="edit-action-bar">
      <span class="edit-action-title">端子点编辑</span>
      <span>点击原图空白处补点；拖动蓝点调整位置，选中后可删除</span>
      <button type="button" :disabled="!selectedTerminalId || terminalSaving" @click="emit('terminalDelete')"><CloseOutlined /> 删除选中点</button>
      <button type="button" :disabled="!terminalDirty || terminalSaving" @click="emit('terminalSave')"><SaveOutlined /> 保存端子点</button>
      <button type="button" :disabled="terminalSaving" @click="emit('terminalCancel')">取消编辑</button>
    </div>
    <div v-if="page.terminalError" class="edit-action-bar"><span>端子检测不可用：{{ page.terminalError.message }}</span></div>
    <div class="canvas-viewport">
      <div class="page-canvas" :style="{ width: `${700 * zoom}px`, height: `${760 * zoom}px` }">
        <BBoxLayer :page="page" :selected-id="selectedId" :zoom="zoom" :edit-mode="editMode"
          :terminal-edit-mode="terminalEditMode && !terminalSaving" :selected-terminal-id="selectedTerminalId"
          @select="emit('select', $event)" @polygon-preview="(id, polygon) => emit('polygonPreview', id, polygon)"
          @create="emit('createBbox', $event)" @terminal-create="emit('terminalCreate', $event)"
          @terminal-select="emit('terminalSelect', $event)"
          @terminal-move="(id, point) => emit('terminalMove', id, point)" />
      </div>
    </div>
    <div class="legend"><span><i class="neutral"></i> 普通检测框</span><span><i class="selected"></i> 当前选中</span><span v-if="page.terminalPoints"><i style="background:#1677ff;border-radius:50%"></i> 端子对中心点</span><em>点击检测框可定位右侧结果</em></div>
  </section>
</template>
