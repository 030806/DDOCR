<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'

const router = useRouter()
const { login, register } = useAuth()
const mode = ref<'login' | 'register'>('login')
const submitting = ref(false)
const form = reactive({ name: '', email: '', employeeNo: '', department: '', phone: '', password: '', confirm: '' })
const title = computed(() => mode.value === 'login' ? '登录系统' : '创建账号')

async function submit() {
  if (!form.phone || !form.password) return message.warning('请填写联系电话和密码')
  if (mode.value === 'register' && (!form.name || !form.employeeNo)) return message.warning('请填写姓名和员工编号')
  if (mode.value === 'register' && form.password !== form.confirm) return message.warning('两次输入的密码不一致')
  if (form.password.length < 8 || !/[A-Za-z]/.test(form.password) || !/\d/.test(form.password)) return message.warning('密码至少 8 位，并同时包含字母和数字')
  submitting.value = true
  try {
    if (mode.value === 'login') await login(form.phone, form.password)
    else await register({ name: form.name, email: form.email, employeeNo: form.employeeNo, department: form.department, phone: form.phone, password: form.password })
    message.success(mode.value === 'login' ? '登录成功' : '注册成功')
    await router.replace('/workspace')
  } catch {
    message.error(mode.value === 'login' ? '登录失败，请检查联系电话和密码' : '注册失败，联系电话或员工编号可能已存在')
  } finally { submitting.value = false }
}
</script>

<template>
  <main class="auth-view">
    <section class="auth-card">
      <div class="auth-brand"><span class="brand-mark"><span></span><span></span><span></span></span><div><strong>矩识 OCR</strong><small>INDUSTRIAL VISION</small></div></div>
      <h1>{{ title }}</h1><p>工业端子排 OCR 管理系统</p>
      <a-form layout="vertical" @submit.prevent="submit">
        <template v-if="mode === 'register'">
          <a-form-item label="姓名"><a-input v-model:value="form.name" /></a-form-item>
          <a-form-item label="员工编号"><a-input v-model:value="form.employeeNo" /></a-form-item>
          <a-form-item label="所属部门"><a-input v-model:value="form.department" /></a-form-item>
          <a-form-item label="电子邮箱（选填）"><a-input v-model:value="form.email" type="email" /></a-form-item>
        </template>
        <a-form-item label="联系电话"><a-input v-model:value="form.phone" /></a-form-item>
        <a-form-item label="密码"><a-input-password v-model:value="form.password" /></a-form-item>
        <a-form-item v-if="mode === 'register'" label="确认密码"><a-input-password v-model:value="form.confirm" /></a-form-item>
        <a-button type="primary" html-type="submit" block size="large" :loading="submitting">{{ title }}</a-button>
      </a-form>
      <button class="auth-switch" @click="mode = mode === 'login' ? 'register' : 'login'">{{ mode === 'login' ? '没有账号？立即注册' : '已有账号？返回登录' }}</button>
    </section>
  </main>
</template>
