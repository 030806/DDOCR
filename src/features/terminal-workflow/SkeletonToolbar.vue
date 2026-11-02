<script setup lang="ts">
import { AimOutlined, PlusOutlined, MinusOutlined, UndoOutlined, ReloadOutlined } from '@ant-design/icons-vue'
defineProps<{mode:string;busy:boolean;canUndo:boolean;count:number}>()
const emit=defineEmits<{mode:[value:string];undo:[];detect:[]}>()
</script>
<template>
  <div class="skeleton-toolbar" role="toolbar" aria-label="骨架编辑工具">
    <div class="tool-group"><button :aria-pressed="mode==='select'" :disabled="busy" @click="emit('mode','select')"><AimOutlined aria-hidden="true" /> 选择</button><button :aria-pressed="mode==='add'" :disabled="busy" @click="emit('mode','add')"><PlusOutlined aria-hidden="true" /> 添加端子</button><button class="delete-tool" :aria-pressed="mode==='delete'" :disabled="busy" @click="emit('mode','delete')"><MinusOutlined aria-hidden="true" /> 删除端子</button></div>
    <button :disabled="busy || !canUndo" @click="emit('undo')"><UndoOutlined aria-hidden="true" /> 撤销</button>
    <span class="point-count">{{count}} 个端子</span>
    <button class="detect-button" :disabled="busy" @click="emit('detect')"><ReloadOutlined aria-hidden="true" /> {{count?'重新检测':'生成骨架'}}</button>
  </div>
</template>
<style scoped>
.skeleton-toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:12px 16px;border-bottom:1px solid #e7ece9;background:#fff}.tool-group{display:flex;gap:4px;padding-right:10px;border-right:1px solid #e3eae5}button{display:inline-flex;align-items:center;gap:6px;padding:8px 10px;border:1px solid transparent;border-radius:6px;background:transparent;color:#53655a;font-size:12px;cursor:pointer;white-space:nowrap}button:hover:not(:disabled){background:#f2f6f3}button[aria-pressed=true]{background:#e8f4ed;color:#137858;border-color:#c3e2ce}.delete-tool[aria-pressed=true]{background:#fff0ee;color:#c83e38;border-color:#f1c5bf}button:disabled{opacity:.4;cursor:default}.point-count{margin-left:auto;font-size:11px;color:#95a399}.detect-button{border-color:#dfe7e1}
</style>
