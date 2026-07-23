<script setup lang="ts">
import { ref, watch } from 'vue'
import type { OcrItem } from '../types/ocr'

const props = defineProps<{ open: boolean; item?: OcrItem; currentUserId?: string; saving?: boolean }>()
const emit = defineEmits<{
  'update:open': [open: boolean]
  save: [text: string]
  updateComment: [commentId: string, content: string]
  deleteComment: [commentId: string]
}>()
const commentText = ref('')
const editingId = ref('')
const editingText = ref('')

watch(() => props.open, (open) => { if (open) commentText.value = '' })

function save() {
  if (!commentText.value.trim()) return
  emit('save', commentText.value.trim())
  commentText.value = ''
}

function startEdit(comment: OcrItem['comments'][number]) {
  editingId.value = comment.id
  editingText.value = comment.content
}

function saveEdit() {
  if (!editingId.value || !editingText.value.trim()) return
  emit('updateComment', editingId.value, editingText.value.trim())
  editingId.value = ''
}

function formatTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}
</script>

<template>
  <a-drawer :open="open" title="结果留言" placement="right" :width="400" @update:open="emit('update:open', $event)">
    <div class="comment-context"><small>识别内容</small><p>{{ item?.corrected || item?.text }}</p></div>
    <div class="comment-list">
      <div v-for="comment in item?.comments" :key="comment.id" class="comment-item">
        <span class="comment-avatar">{{ comment.author[0] }}</span>
        <div>
          <b>{{ comment.author }} <small>{{ formatTime(comment.updatedAt || comment.time) }}{{ comment.updatedAt ? ' · 已编辑' : '' }}</small></b>
          <template v-if="editingId === comment.id">
            <a-textarea v-model:value="editingText" :maxlength="300" :rows="2" />
            <a-space><a-button size="small" @click="editingId = ''">取消</a-button><a-button size="small" type="primary" :loading="saving" @click="saveEdit">保存</a-button></a-space>
          </template>
          <template v-else>
            <p>{{ comment.content }}</p>
            <a-space v-if="comment.authorId === currentUserId">
              <a-button type="link" size="small" @click="startEdit(comment)">编辑</a-button>
              <a-popconfirm title="删除这条留言？" @confirm="emit('deleteComment', comment.id)"><a-button type="link" danger size="small">删除</a-button></a-popconfirm>
            </a-space>
          </template>
        </div>
      </div>
      <a-empty v-if="!item?.comments.length" :image="undefined" description="还没有留言" />
    </div>
    <template #footer>
      <a-textarea v-model:value="commentText" :rows="3" placeholder="输入复核说明或协作留言…" :maxlength="300" />
      <button class="comment-submit" :disabled="!commentText.trim() || saving" @click="save">{{ saving ? '保存中…' : '添加留言' }}</button>
    </template>
  </a-drawer>
</template>
