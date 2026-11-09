<script setup lang="ts">
import IlluminationSelect from './IlluminationSelect.vue'
import type {IlluminationMode} from '../types/ocr'
defineProps<{fileName:string;illumination:IlluminationMode;busy:boolean}>()
defineEmits<{'update:illumination':[value:IlluminationMode];rerun:[]}>()
</script>
<template>
  <section class="terminal-result-controls" aria-label="端子排结果操作">
    <div class="terminal-result-file"><b>{{fileName}}</b><small>沿用已确认的文字区域、骨架、起始与末尾端子及编号规则</small></div>
    <IlluminationSelect :model-value="illumination" :disabled="busy" compact @update:model-value="$emit('update:illumination',$event)" />
    <a-button type="primary" :loading="busy" @click="$emit('rerun')">按已确认配置重新识别</a-button>
  </section>
</template>
<style scoped>
.terminal-result-controls{display:flex;align-items:center;gap:18px;padding:14px 20px;border-bottom:1px solid #dfe7e1;background:#fff;flex-shrink:0}.terminal-result-file{flex:1;min-width:0}.terminal-result-file b{display:block;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.terminal-result-file small{display:block;margin-top:5px;color:#85968b;font-size:11px}
</style>
