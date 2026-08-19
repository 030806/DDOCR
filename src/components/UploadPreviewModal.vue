<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { DeleteOutlined, RotateLeftOutlined, RotateRightOutlined, SaveOutlined } from '@ant-design/icons-vue'
import { isPreviewableImage, rotateImageFile } from '../imageUpload'

const props = defineProps<{ open: boolean; file?: File }>()
const emit = defineEmits<{ close: []; delete: []; save: [file: File] }>()
const rotation = ref(0)
const saving = ref(false)
const previewUrl = ref('')
const isImage = computed(() => Boolean(props.file && isPreviewableImage(props.file)))

function releasePreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

watch(() => props.file, file => {
  releasePreview()
  rotation.value = 0
  if (file) previewUrl.value = URL.createObjectURL(file)
}, { immediate: true })

onBeforeUnmount(releasePreview)

async function save() {
  if (!props.file) return
  saving.value = true
  try {
    emit('save', isImage.value ? await rotateImageFile(props.file, rotation.value) : props.file)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <a-modal :open="open" title="上传文件预览" width="min(900px, 92vw)" :footer="null" :mask-closable="false" @cancel="emit('close')">
    <div class="upload-preview-stage">
      <div v-if="isImage" class="upload-preview-image-wrap">
        <img :src="previewUrl" :alt="file?.name" :style="{ transform: `rotate(${rotation}deg)` }" />
      </div>
      <iframe v-else-if="previewUrl" :src="previewUrl" title="PDF 文件预览"></iframe>
    </div>
    <div class="upload-preview-info">
      <div><b>{{ file?.name }}</b><small>请检查文件内容，确认后保存为待识别文件</small></div>
      <div class="upload-preview-actions">
        <a-button v-if="isImage" @click="rotation -= 90"><RotateLeftOutlined />左转</a-button>
        <a-button v-if="isImage" @click="rotation += 90"><RotateRightOutlined />右转</a-button>
        <a-button danger @click="emit('delete')"><DeleteOutlined />删除</a-button>
        <a-button type="primary" :loading="saving" @click="save"><SaveOutlined />保存</a-button>
      </div>
    </div>
  </a-modal>
</template>
