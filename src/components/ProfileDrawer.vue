<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useAuth } from '../composables/useAuth'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [open: boolean] }>()
const { user, saveProfile } = useAuth()
const editing = ref(false)
const saving = ref(false)
const form = reactive({ name: '', department: '', phone: '' })

watch(() => props.open, (open) => {
  if (!open || !user.value) return
  editing.value = false
  Object.assign(form, { name: user.value.name, department: user.value.department, phone: '' })
})

async function save() {
  saving.value = true
  try {
    await saveProfile({ name: form.name, department: form.department, ...(form.phone ? { phone: form.phone } : {}) })
    editing.value = false
    message.success('个人资料已更新')
  } catch { message.error('个人资料更新失败') }
  finally { saving.value = false }
}
</script>

<template>
  <a-drawer :open="open" title="个人资料" placement="right" :width="400" @update:open="emit('update:open', $event)">
    <div class="profile-hero"><span>{{ user?.name?.slice(0, 1) || '用' }}</span><div><h3>{{ user?.name }}</h3><p>{{ user?.roleNames.join('、') }}</p></div></div>
    <a-form v-if="editing" layout="vertical">
      <a-form-item label="姓名"><a-input v-model:value="form.name" /></a-form-item>
      <a-form-item label="所属部门"><a-input v-model:value="form.department" /></a-form-item>
      <a-form-item label="联系电话"><a-input v-model:value="form.phone" placeholder="如需修改，请填写新号码" /></a-form-item>
      <a-space><a-button @click="editing = false">取消</a-button><a-button type="primary" :loading="saving" @click="save">保存资料</a-button></a-space>
    </a-form>
    <dl v-else class="profile-details">
      <div><dt>员工编号</dt><dd>{{ user?.employeeNo }}</dd></div>
      <div><dt>所属部门</dt><dd>{{ user?.department || '—' }}</dd></div>
      <div><dt>电子邮箱</dt><dd>{{ user?.email }}</dd></div>
      <div><dt>联系电话</dt><dd>{{ user?.phoneMasked || '—' }}</dd></div>
      <div><dt>最近登录</dt><dd>{{ user?.lastLoginAt ? new Date(user.lastLoginAt).toLocaleString('zh-CN') : '—' }}</dd></div>
    </dl>
    <a-button v-if="!editing" block @click="editing = true">编辑个人资料</a-button>
  </a-drawer>
</template>
