<script setup lang="ts">
import { ref } from 'vue'
import { CloudUploadOutlined, PictureOutlined, ArrowRightOutlined } from '@ant-design/icons-vue'
const props=defineProps<{busy?:boolean;side?:string}>()
const emit=defineEmits<{select:[file:File]}>()
const input=ref<HTMLInputElement>(), dragging=ref(false)
function choose(files:FileList|null) { if(!props.busy && files?.[0]) emit('select',files[0]); if(input.value) input.value.value='' }
function drop(event:DragEvent) { dragging.value=false; choose(event.dataTransfer?.files || null) }
</script>
<template>
  <section class="upload-card">
    <div class="upload-context"><span class="eyebrow">准备开始</span><span class="side-pill">{{side==='right'?'右侧端子排':side==='left'?'左侧端子排':'端子排识别'}}</span></div>
    <div class="dropzone" :class="{dragging,busy}" @dragover.prevent="dragging=!busy" @dragleave.prevent="dragging=false" @drop.prevent="drop">
      <div class="upload-icon"><CloudUploadOutlined aria-hidden="true" /></div>
      <h2>{{busy?'正在准备图片…':`上传${side==='right'?'右侧':side==='left'?'左侧':''}端子排图片`}}</h2>
      <p>选择包含完整端子排的清晰图片，随后框选文字区域。</p>
      <input ref="input" class="file-input" type="file" accept="image/*" aria-label="选择端子排图片" :disabled="busy" @change="choose(($event.target as HTMLInputElement).files)" />
      <button class="upload-button" :disabled="busy" @click="input?.click()"><PictureOutlined aria-hidden="true" /> 选择图片 <ArrowRightOutlined aria-hidden="true" /></button>
      <span class="drop-hint">或将图片拖放到此处</span>
      <small>支持图片文件 · 单个文件不超过 200 MB</small>
    </div>
    <div class="upload-guide"><span><b>01</b> 框选文字区域</span><span><b>02</b> 确认骨架与编排</span><span><b>03</b> 识别并校正结果</span></div>
  </section>
</template>
<style scoped>
.upload-card{width:min(880px,100%);margin:24px auto;background:#fff;border:1px solid #e0e8e3;border-radius:16px;padding:24px;box-shadow:0 6px 24px #243e3106}.upload-context{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.eyebrow{font-size:12px;font-weight:600;color:#7b8c83;letter-spacing:2px}.side-pill{font-size:12px;background:#edf6f1;color:#168b6c;padding:5px 12px;border-radius:20px}.dropzone{padding:44px 24px;display:flex;flex-direction:column;align-items:center;border:1.5px dashed #ccdbd2;border-radius:12px;background:#fafcfb;transition:background .15s,border-color .15s}.dropzone.dragging{border-color:#168b6c;background:#edf8f1}.upload-icon{display:grid;place-items:center;width:64px;height:64px;background:#eaf4ee;color:#168b6c;border-radius:18px;font-size:32px;margin-bottom:20px}h2{margin:0 0 10px;font-size:22px;letter-spacing:.3px;font-weight:600;color:#253d32}p{color:#7b8982;font-size:13px;margin:0 0 26px}.file-input{display:none}.upload-button{display:flex;align-items:center;gap:10px;background:#168b6c;color:#fff;border:0;border-radius:8px;padding:12px 24px;font-size:14px;cursor:pointer;box-shadow:0 4px 10px #168b6c20}.upload-button:disabled{opacity:.55;cursor:wait}.upload-button:hover:not(:disabled){background:#10765b}.drop-hint{margin-top:15px;color:#829088;font-size:12px}small{margin-top:26px;font-size:11px;color:#9aa59f}.upload-guide{display:flex;justify-content:space-around;gap:18px;padding:24px 0 4px;font-size:12px;color:#6b7c72}.upload-guide b{color:#a8b7ae;font-size:11px;margin-right:8px}
</style>
