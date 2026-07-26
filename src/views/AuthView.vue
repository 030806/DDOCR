<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'
import { requestPasswordReset, resetPassword } from '../api/auth'

type Mode = 'login' | 'register' | 'forgot'

const router = useRouter()
const { login, register } = useAuth()
const mode = ref<Mode>('login')
const resetStep = ref<1 | 2>(1)
const submitting = ref(false)
const developmentCode = ref('')
const form = reactive({
  name: '', email: '', employeeNo: '', department: '', phone: '',
  password: '', confirm: '', code: '',
})
const title = computed(() => {
  if (mode.value === 'register') return '创建账号'
  if (mode.value === 'forgot') return resetStep.value === 1 ? '找回密码' : '设置新密码'
  return '登录系统'
})

function validPassword(value: string) {
  return value.length >= 8 && /[A-Za-z]/.test(value) && /\d/.test(value)
}

function switchMode(value: Mode) {
  mode.value = value
  resetStep.value = 1
  developmentCode.value = ''
  form.password = ''
  form.confirm = ''
  form.code = ''
}

async function submit() {
  if (mode.value === 'forgot') return submitReset()
  if (!form.phone || !form.password) return message.warning('请填写联系电话和密码')
  if (mode.value === 'register' && (!form.name || !form.employeeNo)) return message.warning('请填写姓名和员工编号')
  if (mode.value === 'register' && form.password !== form.confirm) return message.warning('两次输入的密码不一致')
  if (!validPassword(form.password)) return message.warning('密码至少 8 位，并同时包含字母和数字')
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

async function submitReset() {
  if (!form.phone || !form.employeeNo) return message.warning('请填写联系电话和员工编号')
  if (resetStep.value === 2) {
    if (!/^\d{6}$/.test(form.code)) return message.warning('请输入 6 位验证码')
    if (!validPassword(form.password)) return message.warning('密码至少 8 位，并同时包含字母和数字')
    if (form.password !== form.confirm) return message.warning('两次输入的密码不一致')
  }
  submitting.value = true
  try {
    if (resetStep.value === 1) {
      const result = await requestPasswordReset(form.phone, form.employeeNo)
      developmentCode.value = result.development_code || ''
      resetStep.value = 2
      message.success('重置验证码已生成')
    } else {
      await resetPassword(form.phone, form.code, form.password)
      message.success('密码已重置，请使用新密码登录')
      switchMode('login')
    }
  } catch {
    message.error(resetStep.value === 1 ? '暂时无法申请重置验证码' : '验证码无效或已过期')
  } finally { submitting.value = false }
}
</script>

<template>
  <main class="auth-view">
    <section class="auth-card">
      <div class="auth-brand"><span class="brand-mark"><span></span><span></span><span></span></span><div><strong>矩识 OCR</strong><small>INDUSTRIAL VISION</small></div></div>
      <h1>{{ title }}</h1><p>工业端子排 OCR 管理系统</p>
      <a-alert v-if="developmentCode" type="info" show-icon class="reset-code-alert" :message="`开发联调验证码：${developmentCode}`" />
      <a-form layout="vertical" @submit.prevent="submit">
        <template v-if="mode === 'register'">
          <a-form-item label="姓名"><a-input v-model:value="form.name" /></a-form-item>
          <a-form-item label="员工编号"><a-input v-model:value="form.employeeNo" /></a-form-item>
          <a-form-item label="所属部门"><a-input v-model:value="form.department" /></a-form-item>
          <a-form-item label="电子邮箱（选填）"><a-input v-model:value="form.email" type="email" /></a-form-item>
        </template>
        <template v-if="mode === 'forgot'">
          <a-form-item label="联系电话"><a-input v-model:value="form.phone" :disabled="resetStep === 2" /></a-form-item>
          <a-form-item label="员工编号"><a-input v-model:value="form.employeeNo" :disabled="resetStep === 2" /></a-form-item>
          <template v-if="resetStep === 2">
            <a-form-item label="验证码"><a-input v-model:value="form.code" maxlength="6" inputmode="numeric" /></a-form-item>
            <a-form-item label="新密码"><a-input-password v-model:value="form.password" /></a-form-item>
            <a-form-item label="确认新密码"><a-input-password v-model:value="form.confirm" /></a-form-item>
          </template>
        </template>
        <template v-else>
          <a-form-item label="联系电话"><a-input v-model:value="form.phone" /></a-form-item>
          <a-form-item label="密码"><a-input-password v-model:value="form.password" /></a-form-item>
          <a-form-item v-if="mode === 'register'" label="确认密码"><a-input-password v-model:value="form.confirm" /></a-form-item>
        </template>
        <a-button type="primary" html-type="submit" block size="large" :loading="submitting">{{ title }}</a-button>
      </a-form>
      <button v-if="mode === 'login'" class="auth-switch" @click="switchMode('forgot')">忘记密码？</button>
      <button class="auth-switch" @click="switchMode(mode === 'login' ? 'register' : 'login')">{{ mode === 'login' ? '没有账号？立即注册' : '返回登录' }}</button>
    </section>
  </main>
</template>
