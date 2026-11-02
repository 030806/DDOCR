<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiClient } from '../api/client'
import TerminalWorkflowView from '../features/terminal-workflow/TerminalWorkflowView.vue'
const route=useRoute(), router=useRouter()
let disposed=false
onBeforeUnmount(()=>{disposed=true})
const loading=ref(true), failed=ref(false), child=ref<{prepareSideChange:()=>Promise<boolean>}>()
defineExpose({prepareSideChange:async()=>child.value ? child.value.prepareSideChange() : true})
async function load() {
  loading.value=true; failed.value=false
  const taskId=String(route.params.terminalId), side=String(route.params.side)
  try {
    if(route.query.new!=='1') {
      const flow=(await apiClient.get(`/terminal-tasks/${taskId}/sides/${side}/workflow`)).data.data
      if(disposed) return
      if(!flow) {
        const task=(await apiClient.get(`/terminal-tasks/${taskId}`)).data.data
        if(disposed) return
        if(task.sides[side]) { await router.replace(`/terminal-tasks/${taskId}/${side}/${task.sides[side].job_id}`); return }
      }
      if(flow?.job_id && flow.job_id!=='submitting') {
        await router.replace(`/terminal-tasks/${taskId}/${side}/${flow.job_id}`)
        return
      }
    }
  } catch { failed.value=true }
  finally { loading.value=false }
}
onMounted(load)
</script>
<template>
  <a-spin v-if="loading" />
  <a-alert v-else-if="failed" type="error" message="流程加载失败"><template #action><a-button @click="load">重试</a-button></template></a-alert>
  <TerminalWorkflowView v-else ref="child" :terminal-id="String(route.params.terminalId)" :task-side="route.params.side==='right'?'right':'left'" :new-attempt="route.query.new==='1'" />
</template>
