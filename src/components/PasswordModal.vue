<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [open: boolean] }>()
const form = reactive({ currentPassword: '', newPassword: '', confirmPassword: '' })
const error = ref('')

watch(() => props.open, (open) => {
  if (open) { Object.assign(form, { currentPassword: '', newPassword: '', confirmPassword: '' }); error.value = '' }
})

function submit() {
  if (!form.currentPassword || !form.newPassword || !form.confirmPassword) error.value = '请完整填写密码信息'
  else if (form.newPassword.length < 8 || !/[A-Za-z]/.test(form.newPassword) || !/\d/.test(form.newPassword)) error.value = '新密码至少 8 位，并同时包含字母和数字'
  else if (form.newPassword !== form.confirmPassword) error.value = '两次输入的新密码不一致'
  else {
    error.value = ''
    emit('update:open', false)
    message.success('密码修改成功（Mock）')
  }
}
</script>

<template>
  <a-modal :open="open" title="修改密码" ok-text="确认修改" cancel-text="取消" @update:open="emit('update:open', $event)" @ok="submit">
    <a-form layout="vertical" class="password-form">
      <a-form-item label="当前密码"><a-input-password v-model:value="form.currentPassword" placeholder="输入当前密码" /></a-form-item>
      <a-form-item label="新密码"><a-input-password v-model:value="form.newPassword" placeholder="至少 8 位，包含字母和数字" /></a-form-item>
      <a-form-item label="确认新密码"><a-input-password v-model:value="form.confirmPassword" placeholder="再次输入新密码" /></a-form-item>
      <a-alert v-if="error" :message="error" type="error" show-icon />
    </a-form>
  </a-modal>
</template>
