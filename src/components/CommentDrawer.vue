<script setup lang="ts">
import { ref, watch } from 'vue'
import type { OcrItem } from '../mock'

const props = defineProps<{ open: boolean; item?: OcrItem }>()
const emit = defineEmits<{ 'update:open': [open: boolean]; save: [text: string] }>()
const commentText = ref('')

watch(() => props.open, (open) => { if (open) commentText.value = '' })

function save() {
  if (!commentText.value.trim()) return
  emit('save', commentText.value.trim())
  commentText.value = ''
}
</script>

<template>
  <a-drawer :open="open" title="结果留言" placement="right" :width="400" @update:open="emit('update:open', $event)">
    <div class="comment-context"><small>识别内容</small><p>{{ item?.corrected || item?.text }}</p></div>
    <div class="comment-list">
      <div v-for="comment in item?.comments" :key="comment.id" class="comment-item">
        <span class="comment-avatar">{{ comment.author[0] }}</span>
        <div><b>{{ comment.author }} <small>{{ comment.time }}</small></b><p>{{ comment.content }}</p></div>
      </div>
      <a-empty v-if="!item?.comments.length" :image="undefined" description="还没有留言" />
    </div>
    <template #footer>
      <a-textarea v-model:value="commentText" :rows="3" placeholder="输入复核说明或协作留言…" :maxlength="300" />
      <button class="comment-submit" :disabled="!commentText.trim()" @click="save">添加留言</button>
    </template>
  </a-drawer>
</template>
