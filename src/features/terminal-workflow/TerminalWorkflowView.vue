<script setup lang="ts">
import { computed, ref, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { apiClient } from '../../api/client'
import { uploadOcrFile } from '../../api/ocr'
import type { RegionDraft } from '../../api/ocr'
import { CheckOutlined, ZoomInOutlined, ZoomOutOutlined, ExpandOutlined, ArrowRightOutlined, ScanOutlined, UploadOutlined } from '@ant-design/icons-vue'
import { isPreviewableImage, MAX_UPLOAD_SIZE_BYTES } from '../../imageUpload'
import { terminalLabel, type TerminalNumbering } from './terminalNumbering'
import type { IlluminationMode } from '../../types/ocr'
import IlluminationSelect from '../../components/IlluminationSelect.vue'
import UploadDropzone from './UploadDropzone.vue'
import SkeletonToolbar from './SkeletonToolbar.vue'
import UploadPreviewModal from '../../components/UploadPreviewModal.vue'

type Box = [number, number, number, number]
type Point = { id: string; x: number; y: number; source?:string }
type Flow = { illumination?: IlluminationMode; id: string; revision: number; confirmed: number; regions: {id:string; bbox:Box}[]; side: string | null; points: Point[]; start_point_id: string | null; ordering: (TerminalNumbering & {naming:string; prefix?:string}) | null; width:number; height:number; job_id:string|null }
const props=defineProps<{terminalId?:string;taskSide?:'left'|'right';newAttempt?:boolean}>()
const router = useRouter(), route = useRoute()
let disposed=false
let submitting=false
const flow = ref<Flow>(), busy = ref(false), file = ref<File>(), preview = ref(false), imageUrl = ref('')
const replacementFile=ref<File>(), replacementInput=ref<HTMLInputElement>()
const layout=ref<HTMLElement>(), operationWidth=ref(310), resizing=ref(false)
function resizeLayout(event:PointerEvent) {
  if(!resizing.value || !layout.value) return
  const rect=layout.value.getBoundingClientRect()
  operationWidth.value=Math.round(Math.max(280,Math.min(rect.width-380,rect.right-event.clientX-6)))
}
function beginResize(event:PointerEvent) { if(event.button!==0) return; resizing.value=true; (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId); event.preventDefault() }
function resizeKey(event:KeyboardEvent) {
  if(event.key==='Home') operationWidth.value=310
  else if(event.key==='ArrowLeft' || event.key==='ArrowRight') operationWidth.value=Math.max(280,Math.min((layout.value?.clientWidth || 1000)-380,operationWidth.value+(event.key==='ArrowLeft'?20:-20)))
  else return
  event.preventDefault()
}
function closePreview() {preview.value=false;replacementFile.value=undefined}
function chooseReplacement(event:Event) {
  const input=event.target as HTMLInputElement, value=input.files?.[0]; input.value=''
  if(!value || busy.value) return
  if(!isPreviewableImage(value)) {message.warning('请选择图片文件');return}
  if(value.size>MAX_UPLOAD_SIZE_BYTES) {message.warning('图片不能超过 200 MB');return}
  replacementFile.value=value;preview.value=true
}
const titles = ['文字区域','左右方向','结构骨架','起始端子','编排及命名','文字识别']
const editing = ref(1), selectedPoint = ref(''), tool = ref('select')
const side = ref(props.taskSide || ''), start = ref(1), naming = ref(''), prefix = ref('')
const numberPrefix=ref('')
const illumination=ref<IlluminationMode>('none')
const numberingMode=ref<'numeric'|'alpha'>('numeric'), letterStart=ref('A'), letterCase=ref<'upper'|'lower'>('upper')
const orderingDraft=computed(()=>({start:start.value,naming:naming.value,prefix:prefix.value,numbering_mode:numberingMode.value,letter_start:letterStart.value,letter_case:letterCase.value,number_prefix:numberPrefix.value}))
const numberingPreview=computed(()=>Array.from({length:Math.min(ordered.value.length,5)},(_,i)=>terminalLabel(orderingDraft.value,i)).filter(Boolean).join(' → '))
const pointX=ref(0), pointY=ref(0)
const zoom=ref(100)
const pointHistory=ref<Point[][]>([])
const selected=computed(()=>flow.value?.points.find(p=>p.id===selectedPoint.value))
const confirmLabels=['确认区域','确认方向','确认骨架','确认起始端子','确认编排']
const stepHints=['确认图片中的文字识别区域，可选择多个区域。','请核对本次图片所属的端子排方向。','检查端子孔位，补充漏检或移除误检。','在图片上点击作为编排基准的起始端子。','核对从上到下的顺序，并设置编号和命名规律。','配置已就绪，识别后将自动匹配端子点与文字。']
function selectFile(value:File) {
  if(!isPreviewableImage(value)) { message.warning('请选择图片文件'); return }
  if(value.size>MAX_UPLOAD_SIZE_BYTES) { message.warning('图片不能超过 200 MB'); return }
  file.value=value; preview.value=true
}
async function updatePoints(points:Point[]) {
  const before=flow.value!.points.map(p=>({...p}))
  await patch({points})
  pointHistory.value=[...pointHistory.value.slice(-19),before]
  if(!selected.value) selectedPoint.value=''
}
async function undoPoints() {
  const before=pointHistory.value[pointHistory.value.length-1]
  if(!before) return
  await run(async()=>{await patch({points:before});pointHistory.value=pointHistory.value.slice(0,-1);selectedPoint.value=''})
}
async function detectSkeleton() {
  await run(async()=>{flow.value=await call('skeleton-detections');pointHistory.value=[];selectedPoint.value=''})
}
const initialRegions=computed(()=>flow.value?.regions.map(r=>({clientId:r.id,bbox:r.bbox})) || [])
const step = computed(() => editing.value)
const ordered = computed(() => {
  const f = flow.value
  if (!f) return []
  const p = [...f.points].sort((a,b)=>a.y-b.y || a.x-b.x || a.id.localeCompare(b.id))
  const index = p.findIndex(p=>p.id===f.start_point_id)
  return index < 0 ? [] : p.slice(index)
})
async function run(action: () => Promise<void>) {
  busy.value = true
  try { await action() } catch (e:any) { message.error(e.response?.data?.error?.message || '操作失败，请重试') }
  finally { busy.value = false }
}
async function call(action:string, body:object = {}) {
  const f = flow.value!
  const response = await apiClient.post(`/terminal-workflows/${f.id}/${action}`, {base_revision:f.revision,...body}, {timeout: ['skeleton-detections','position-previews'].includes(action)?150000:10000})
  return response.data.data
}
async function patch(changes:object) { flow.value = await call('configuration',{changes}) }
async function saveFile(value:File, regions:RegionDraft[]) {
  if (!regions.length) { message.warning('请至少框选一个文字区域'); return }
  preview.value = false
  await run(async()=>{
    if(flow.value && !replacementFile.value) {
      await patch({regions:regions.map(r=>({id:r.clientId,bbox:r.bbox}))})
      editing.value=1
      return
    }
    const uploaded = await uploadOcrFile(value)
    const selectedRegions=regions.map(r=>({id:r.clientId,bbox:r.bbox}))
    let created:Flow
    if(props.terminalId && props.taskSide) {
      created=(await apiClient.post(`/terminal-tasks/${props.terminalId}/sides/${props.taskSide}/workflows`, {file_id:uploaded.id,replace:!!props.newAttempt || !!replacementFile.value,regions:selectedRegions})).data.data
    } else {
      const draft=(await apiClient.post('/terminal-workflows',{file_id:uploaded.id})).data.data
      created=(await apiClient.post(`/terminal-workflows/${draft.id}/configuration`,{base_revision:draft.revision,changes:{regions:selectedRegions}})).data.data
    }
    illumination.value=created.illumination ?? 'none'
    flow.value=created;file.value=value;replacementFile.value=undefined
    selectedPoint.value='';pointHistory.value=[];tool.value='select';zoom.value=100
    side.value=props.taskSide || '';start.value=1;naming.value='';prefix.value=''
    numberPrefix.value='';numberingMode.value='numeric';letterStart.value='A';letterCase.value='upper'
    if(imageUrl.value) URL.revokeObjectURL(imageUrl.value)
    imageUrl.value = URL.createObjectURL(value)
    if(!props.terminalId) {submitting=true;try {await router.replace({query:{...route.query,workflow:created.id}})} finally {submitting=false}}

    editing.value = 1
  })
  replacementFile.value=undefined
}
async function confirm() {
  if(step.value===5 && !naming.value) { message.warning('请选择线号管命名规律'); return }
  await run(async()=>{
    if(step.value===2) await patch({side:side.value})
    if(step.value===5) await patch({ordering:orderingDraft.value})
    if(flow.value!.confirmed<step.value) flow.value = await call('confirmations',{step:step.value})
    editing.value = Math.min(6,flow.value!.confirmed+1)
  })
}
function source(event:PointerEvent) {
  const svg = event.currentTarget as SVGSVGElement
  const point = svg.createSVGPoint(); point.x=event.clientX; point.y=event.clientY
  return point.matrixTransform(svg.getScreenCTM()!.inverse())
}
function down(event:PointerEvent) {
  if(busy.value || !flow.value || step.value!==3) return
  const p = source(event)
  if(step.value===3 && tool.value==='add') void run(()=>updatePoints([...flow.value!.points,{id:crypto.randomUUID(),x:p.x,y:p.y,source:'manual'}]))
}
function clickPoint(p:Point) {
  if(busy.value) return
  selectedPoint.value=p.id; pointX.value=p.x; pointY.value=p.y
  if(step.value===4) void run(()=>patch({start_point_id:p.id}))
  if(step.value===3 && tool.value==='delete') void run(()=>updatePoints(flow.value!.points.filter(q=>q.id!==p.id)))
}
async function setIllumination(value:IlluminationMode) {
  if(busy.value || !flow.value || flow.value.job_id) return
  await run(()=>patch({illumination:value}))
  illumination.value=flow.value.illumination ?? 'none'
}
async function submit() {
  await run(async()=>{ const result = await call('recognitions'); if(result.id==='submitting') throw new Error('提交处理中'); submitting=true; await router.push(props.terminalId ? `/terminal-tasks/${encodeURIComponent(props.terminalId)}/${props.taskSide}/${result.id}` : `/workspace/${result.id}`) })
}
if(props.terminalId || typeof route.query.workflow==='string') void run(async()=>{
  if(props.terminalId && props.taskSide) {
    const restored=(await apiClient.get(`/terminal-tasks/${props.terminalId}/sides/${props.taskSide}/workflow`)).data.data
    if(disposed || !restored || (props.newAttempt && restored.job_id)) return
    flow.value=restored
  } else flow.value=(await apiClient.get(`/terminal-workflows/${route.query.workflow}`)).data.data
  illumination.value=flow.value!.illumination ?? 'none'
  editing.value=Math.min(6,flow.value!.confirmed+1)
  side.value=props.taskSide || flow.value!.side || ''
  start.value=flow.value!.ordering?.start ?? 1; naming.value=['auto','existing','temp','new'].includes(flow.value!.ordering?.naming || '') ? flow.value!.ordering!.naming : 'auto'; prefix.value=flow.value!.ordering?.prefix ?? ''
  numberPrefix.value=flow.value!.ordering?.number_prefix ?? ''
  numberingMode.value=flow.value!.ordering?.numbering_mode ?? 'numeric'; letterStart.value=flow.value!.ordering?.letter_start ?? 'A'; letterCase.value=flow.value!.ordering?.letter_case ?? 'upper'
  // Authorized file content is loaded through the API, never a public storage URL.
  const data=await apiClient.get(`/files/${(flow.value as any).file_id}/content`,{responseType:'blob'})
  if(disposed) return
  imageUrl.value=URL.createObjectURL(data.data)
  file.value=new File([data.data],'source.png',{type:data.data.type})
})
async function prepareSideChange() {
  if(submitting) return true
  if(busy.value && !submitting) { message.info('请等待当前操作完成'); return false }
  if(flow.value && !flow.value.job_id && step.value===2 && side.value!==flow.value.side) { await run(()=>patch({side:side.value})); return flow.value.side===side.value }
  if(flow.value && !flow.value.job_id && step.value===5) {
    const next=orderingDraft.value
    if(JSON.stringify(next)!==JSON.stringify(flow.value.ordering)) { await run(()=>patch({ordering:next})); return JSON.stringify(next)===JSON.stringify(flow.value.ordering) }
  }
  return true
}
defineExpose({prepareSideChange})
onBeforeRouteLeave(prepareSideChange)
onBeforeRouteUpdate(prepareSideChange)
onBeforeUnmount(()=>{disposed=true;if(imageUrl.value) URL.revokeObjectURL(imageUrl.value)})
</script>

<template>
  <main class="workflow">
    <UploadDropzone v-if="!flow" :busy="busy" :side="props.taskSide" @select="selectFile" />
    <UploadPreviewModal :default-region-selection="true" :open="preview" :file="replacementFile || file" :initial-regions="replacementFile ? [] : initialRegions" @close="closePreview" @delete="replacementFile ? closePreview() : (file=undefined,preview=false)" @save="saveFile" />
    <template v-if="flow">
      <nav class="workflow-steps" aria-label="识别步骤">
        <button v-for="(title,index) in titles" :key="title" :disabled="busy || index>flow.confirmed || !!flow.job_id" :class="{active:step===index+1,complete:flow.confirmed>index}" :aria-current="step===index+1?'step':undefined" @click="editing=index+1;tool='select'">
          <span class="step-number"><CheckOutlined aria-hidden="true" v-if="flow.confirmed>index"/><template v-else>{{index+1}}</template></span><span>{{title}}</span>
        </button>
      </nav>
      <div class="workflow-file-bar"><span>{{file?.name || '当前图片'}}<small>更换图片后将重新确认区域、骨架和编排</small></span><input ref="replacementInput" class="replacement-input" type="file" accept="image/*" aria-label="重新上传端子排图片" :disabled="busy || !!flow.job_id" @change="chooseReplacement"/><a-button :disabled="busy || !!flow.job_id" @click="replacementInput?.click()"><UploadOutlined aria-hidden="true" /> 更换图片</a-button></div>
      <div ref="layout" class="layout" :class="{resizing}" :style="{'--operation-width':`${operationWidth}px`}">
        <div class="image-card">
          <SkeletonToolbar v-if="step===3" :mode="tool" :busy="busy" :can-undo="!!pointHistory.length" :count="flow.points.length" @mode="tool=$event" @undo="undoPoints" @detect="detectSkeleton" />
          <div class="image-heading" v-else><span><ScanOutlined aria-hidden="true" /> 原图与标注</span><span>{{flow.regions.length}} 个文字区域 · {{flow.points.length}} 个端子</span></div>
          <div class="canvas-hint" :class="{danger:step===3 && tool==='delete'}"><span>{{step===3 ? (tool==='add'?'点击图片空白处添加端子':tool==='delete'?'点击要删除的端子，可使用撤销恢复':'点击端子查看位置，或切换工具补充、删除孔位') : step===4?'点击端子圆点，设置编排起点':'向下滚动查看完整图片'}}</span><span class="zoom-controls"><button aria-label="缩小图片" :disabled="zoom<=50" @click="zoom=Math.max(50,zoom-25)"><ZoomOutOutlined aria-hidden="true" /></button><span>{{zoom}}%</span><button aria-label="放大图片" :disabled="zoom>=250" @click="zoom=Math.min(250,zoom+25)"><ZoomInOutlined aria-hidden="true" /></button><button aria-label="适应宽度" @click="zoom=100"><ExpandOutlined aria-hidden="true" /></button></span></div>
          <div class="image-scroll" tabindex="0" aria-label="图片滚动区域">
            <svg :viewBox="`0 0 ${flow.width} ${flow.height}`" :style="{width:`${zoom}%`}" :class="{adding:step===3 && tool==='add',deleting:step===3 && tool==='delete'}" @pointerdown="down">
              <image :href="imageUrl" :width="flow.width" :height="flow.height" />
              <rect v-for="r in flow.regions" :key="r.id" :x="r.bbox[0]" :y="r.bbox[1]" :width="r.bbox[2]-r.bbox[0]" :height="r.bbox[3]-r.bbox[1]" fill="#168b6c08" stroke="#168b6c" stroke-width="2" pointer-events="none" />
              <g v-for="p in flow.points" :key="p.id" class="terminal-marker" @pointerdown.stop @click="clickPoint(p)">
                <circle v-if="p.id===selectedPoint || p.id===flow.start_point_id" :cx="p.x" :cy="p.y" r="16" fill="none" :stroke="p.id===flow.start_point_id?'#ed9d32':'#168b6c'" stroke-width="3" />
                <circle class="point-halo" :cx="p.x" :cy="p.y" r="12" fill="none" :stroke="p.id===flow.start_point_id?'#a85c00':p.id===selectedPoint?'#07583f':'#074a9a'" stroke-width="1.5" pointer-events="none" />
                <circle class="point-dot" :cx="p.x" :cy="p.y" r="9" :fill="p.id===flow.start_point_id?'#fa8c16':p.id===selectedPoint?'#168b6c':'#1677ff'" stroke="#ffffff" stroke-width="3"/>
                <text :x="p.x+21" :y="p.y+6" font-size="19" fill="#244936" stroke="white" stroke-width="4" paint-order="stroke" pointer-events="none">{{p.id===flow.start_point_id?'起点 · ':''}}{{ordered.findIndex(q=>q.id===p.id)>=0 ? terminalLabel(orderingDraft,ordered.findIndex(q=>q.id===p.id)):''}}</text>
              </g>
            </svg>
          </div>
          <div class="image-footer"><span><i></i>端子孔位 <i class="origin"></i>起始端子</span><span>{{flow.width}} × {{flow.height}} px</span></div>
        </div>
        <div class="layout-divider" role="separator" tabindex="0" aria-label="调整原图与操作卡片宽度" aria-orientation="vertical" :aria-valuenow="operationWidth" :aria-valuemin="280" :aria-valuemax="Math.max(280,(layout?.clientWidth || 1000)-380)" title="拖动调整布局；双击恢复默认" @pointerdown="beginResize" @pointermove="resizeLayout" @pointerup="resizing=false" @pointercancel="resizing=false" @lostpointercapture="resizing=false" @keydown="resizeKey" @dblclick="operationWidth=310"><span></span></div>
        <section class="operation-card">
          <div class="operation-heading"><span class="eyebrow">步骤 {{step}} / 6</span><span class="side-badge">{{(props.taskSide || side)==='right'?'右侧端子排':'左侧端子排'}}</span></div>
          <h2>{{titles[step-1]}}</h2><p class="step-description">{{stepHints[step-1]}}</p>
          <div class="operation-body">
            <template v-if="step===1"><div class="stat-card"><strong>{{flow.regions.length}}</strong><span>已选文字区域</span></div><a-button block :disabled="busy" @click="preview=true">调整文字区域</a-button></template>
            <template v-if="step===2"><label>本次识别方向<select v-model="side" :disabled="!!props.taskSide"><option value="">请选择方向</option><option value="left">左侧端子排</option><option value="right">右侧端子排</option></select></label><p class="field-note">请确认图片与顶部所选侧别一致。</p></template>
            <template v-if="step===3"><div class="stat-card"><strong>{{flow.points.length}}</strong><span>当前端子数量</span></div><p class="field-note">使用图片上方的工具栏校正骨架，再确认继续。</p><div v-if="selected" class="selection-card"><span class="selection-title">所选端子位置</span><div class="coordinates"><label>X 坐标<input v-model.number="pointX" type="number" min="0" :max="flow.width" /></label><label>Y 坐标<input v-model.number="pointY" type="number" min="0" :max="flow.height" /></label></div><a-button block :disabled="busy" @click="run(()=>updatePoints(flow!.points.map(p=>p.id===selectedPoint?{...p,x:pointX,y:pointY}:p)))">应用位置调整</a-button></div></template>
            <template v-if="step===4"><div class="status-message" :class="{ready:!!flow.start_point_id}">{{flow.start_point_id?'已设置起始端子，图片中以橙色标注':'尚未选择起始端子'}}</div><p class="field-note">起点之前的端子保留在骨架中，不参与本次编排。</p></template>
            <template v-if="step===5"><div class="stat-card"><strong>{{ordered.length}}</strong><span>按从上到下顺序编排</span></div><label>端子孔编号方式<select v-model="numberingMode"><option value="numeric">数字顺序 · 1、2、3</option><option value="alpha">字母顺序 · A、B、C</option></select></label><label v-if="numberingMode==='numeric'">起始编号<input v-model.number="start" type="number" min="0" /></label><template v-else><label>起始字母<input v-model="letterStart" maxlength="10" placeholder="例如 A、Z、AA" /></label><label>字母大小写<select v-model="letterCase"><option value="upper">大写 · A、B、C</option><option value="lower">小写 · a、b、c</option></select></label></template><label>端子孔编号前缀（可选）<input v-model="numberPrefix" maxlength="40" placeholder="例如：XT-，留空则不加前缀" /></label><p class="numbering-preview">编号预览：{{numberingPreview || '请输入有效的起始编号'}}</p><p class="field-note">编号前缀只添加到端子孔编号，不修改线号管识别文字。</p><label>线号管命名规律<select v-model="naming"><option value="" disabled>请选择线号管命名规律</option><option value="auto">Auto · 自动匹配全部规则</option><option value="existing">现有柜</option><option value="temp">临时柜</option><option value="new">新柜</option></select></label><p class="field-note">OCR 将按所选规则校验线号；Auto 同时匹配现有柜、临时柜和新柜规则。未能可靠判定的结果保留供人工核对。</p></template>
            <template v-if="step===6"><div class="status-message ready"><CheckOutlined aria-hidden="true" /> 识别配置已确认</div><dl class="recognition-summary"><dt>识别方向</dt><dd>{{side==='left'?'左侧':'右侧'}}端子排</dd><dt>文字区域</dt><dd>{{flow.regions.length}} 个</dd><dt>编排端子</dt><dd>{{ordered.length}} 个</dd><dt>端子孔编号</dt><dd>{{numberingPreview}}</dd></dl><IlluminationSelect :model-value="illumination" :disabled="busy || !!flow.job_id" @update:model-value="setIllumination" /><p class="field-note">原图保留原始光照；全局 HE 均衡整体亮度；CLAHE 增强局部对比度。</p><p class="field-note">识别后自动匹配端子点与文字，漏检孔位及匹配关系可在结果页继续校正。</p></template>
          </div>
          <div class="operation-actions"><a-button v-if="step<=5" type="primary" block size="large" :loading="busy" :disabled="!!flow.job_id" @click="confirm">{{confirmLabels[step-1]}} <ArrowRightOutlined aria-hidden="true" /></a-button><a-button v-else type="primary" block size="large" :loading="busy" :disabled="flow.confirmed<5 || !!flow.job_id" @click="submit"><ScanOutlined aria-hidden="true" /> 开始文字识别</a-button><span class="save-note">已确认配置会随流程保存</span></div>
        </section>
      </div>
    </template>
  </main>
</template>
<style scoped>
.workflow{padding:24px;flex:1;min-height:0;overflow-y:scroll;scrollbar-gutter:stable;background:#f1f4f2;overscroll-behavior:contain;color:#283d32}.workflow-steps{display:flex;align-items:center;background:#fff;border:1px solid #e0e8e3;border-radius:12px;padding:18px 20px;margin-bottom:20px;gap:8px}.workflow-steps button{position:relative;flex:1;display:flex;align-items:center;gap:10px;border:0;background:transparent;padding:6px;color:#9aa69f;font-size:12px;text-align:left;white-space:nowrap;cursor:pointer}.workflow-steps button:disabled{cursor:default}.step-number{display:grid;place-items:center;flex-shrink:0;width:28px;height:28px;border:1px solid #e1e7e3;border-radius:50%;font-size:12px;color:#a3afa7}.workflow-steps .active{color:#146c50;font-weight:600}.active .step-number{color:#fff;border-color:#168b6c;background:#168b6c;box-shadow:0 0 0 4px #edf7f1}.complete .step-number{color:#168b6c;background:#edf7f1;border-color:#d7eade}.complete{color:#5c7868!important}.layout{display:grid;grid-template-columns:minmax(360px,1fr) 12px minmax(280px,min(var(--operation-width,310px),55%));gap:6px;align-items:start}.workflow-file-bar{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:0 0 16px;color:#536c5d;font-size:12px}.workflow-file-bar small{color:#91a095;margin-left:16px;font-size:11px}.replacement-input{display:none}.layout-divider{align-self:stretch;min-height:280px;display:flex;align-items:center;justify-content:center;cursor:col-resize;touch-action:none;outline:none;border-radius:6px}.layout-divider span{width:3px;height:44px;background:#c6d6cc;border-radius:3px}.layout-divider:hover,.layout-divider:focus-visible,.resizing .layout-divider{background:#e1eee6}.layout-divider:hover span,.resizing .layout-divider span{background:#168b6c}.resizing{user-select:none;cursor:col-resize}.image-card,.operation-card{border:1px solid #dfe7e1;border-radius:12px;background:white;overflow:hidden;box-shadow:0 3px 14px #23392c04}.image-heading{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:18px;font-size:12px;font-weight:600}.image-heading>span:last-child{font-size:11px;font-weight:400;color:#8a9b90}.canvas-hint{display:flex;align-items:center;justify-content:space-between;gap:8px;background:#f6f8f6;padding:9px 16px;color:#7e8e83;font-size:11px;border-block:1px solid #e8ede9}.canvas-hint.danger{background:#fff5f2;color:#b74b43}.zoom-controls{display:flex;align-items:center;gap:5px;white-space:nowrap}.zoom-controls button{border:0;background:transparent;color:#627d6c;cursor:pointer;width:26px;height:24px;border-radius:4px}.zoom-controls button:hover{background:#e8eeea}.zoom-controls button:disabled{opacity:.35;cursor:default}.image-scroll{overflow:auto;max-height:calc(100vh - 310px);min-height:280px;background:#e9eeeb;scrollbar-gutter:stable}.image-scroll svg{height:auto;display:block;max-width:none;touch-action:pan-y;cursor:default}.image-scroll svg.adding{cursor:crosshair}.terminal-marker{cursor:pointer}.deleting .terminal-marker:hover .point-dot{fill:#ef4444;stroke:#ffffff;stroke-width:3}.deleting .terminal-marker:hover .point-halo{stroke:#b91c1c}.image-footer{display:flex;justify-content:space-between;padding:12px 16px;font-size:10px;color:#94a298}.image-footer span{display:flex;align-items:center;gap:8px}.image-footer i{width:7px;height:7px;border:1.5px solid #1677ff;background:#1677ff;border-radius:50%}.image-footer .origin{border-color:#fa8c16;background:#fa8c16;margin-left:10px}.operation-card{position:sticky;top:0;padding:22px}.operation-heading{display:flex;align-items:center;justify-content:space-between}.eyebrow{font-size:10px;letter-spacing:1px;color:#91a095}.side-badge{font-size:10px;background:#edf6f1;color:#56836b;border-radius:4px;padding:4px 7px}h2{margin:20px 0 10px;font-size:20px;font-weight:600;letter-spacing:.5px}.step-description{font-size:12px;line-height:1.8;color:#88988e;margin:0 0 24px}.operation-body{display:flex;flex-direction:column;gap:16px;min-height:130px}.operation-body label{display:flex;flex-direction:column;gap:8px;font-size:12px;color:#64776a}.operation-body input,.operation-body select{width:100%;min-width:0;padding:10px 12px;border:1px solid #dce5de;border-radius:7px;background:#fff;font:inherit;color:#334d3e;outline:none}.operation-body input:focus,.operation-body select:focus{border-color:#168b6c;box-shadow:0 0 0 2px #168b6c10}.operation-body select:disabled{background:#f6f8f6;color:#506a59}.stat-card{display:flex;align-items:baseline;gap:12px;border:1px solid #e4ece6;border-radius:8px;background:#f8fbf9;padding:15px 18px}.stat-card strong{font-size:28px;font-weight:500;color:#168b6c}.stat-card span{font-size:11px;color:#8c9e91}.numbering-preview{margin:0;padding:10px 12px;border-radius:6px;background:#f0f7f2;color:#27724d;font-size:12px;overflow-wrap:anywhere}.field-note{margin:0;font-size:11px;line-height:1.9;color:#91a095}.selection-card{border-top:1px solid #e7ede8;padding-top:16px}.selection-title{font-size:12px;color:#4f6c59}.coordinates{display:flex;gap:10px;margin:12px 0}.coordinates label{flex:1;min-width:0}.status-message{padding:14px;border-radius:8px;background:#f6f7f6;color:#8c988f;font-size:12px;line-height:1.7}.status-message.ready{color:#17815e;background:#edf7f0}.recognition-summary{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:8px 0;font-size:12px}.recognition-summary dt{color:#8b9a8f}.recognition-summary dd{margin:0;text-align:right;color:#395e47}.operation-actions{padding-top:24px;margin-top:24px;border-top:1px solid #e9eee9}.save-note{display:block;text-align:center;margin-top:12px;font-size:10px;color:#a1ada4}button:focus-visible{outline:2px solid #168b6c;outline-offset:3px}@media(max-width:1250px){.workflow{padding:16px}.layout{gap:4px}.workflow-steps{padding:14px 10px}.workflow-steps button{gap:6px;font-size:11px}.operation-card{padding:18px}}
</style>
