<script setup lang="ts">
import { mockUser } from '../mock/user'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [open: boolean] }>()
</script>

<template>
  <a-drawer :open="open" title="个人资料" placement="right" :width="400" @update:open="emit('update:open', $event)">
    <div class="profile-hero"><span>{{ mockUser.displayInitial }}</span><div><h3>{{ mockUser.name }}</h3><p>{{ mockUser.role }}</p></div></div>
    <dl class="profile-details">
      <div><dt>员工编号</dt><dd>{{ mockUser.employeeNo }}</dd></div>
      <div><dt>所属部门</dt><dd>{{ mockUser.department }}</dd></div>
      <div><dt>电子邮箱</dt><dd>{{ mockUser.email }}</dd></div>
      <div><dt>联系电话</dt><dd>{{ mockUser.phone }}</dd></div>
      <div><dt>最近登录</dt><dd>{{ mockUser.lastLoginAt }}</dd></div>
    </dl>
    <p class="profile-note">当前为 Mock 用户资料，暂未连接账号系统。</p>
  </a-drawer>
</template>
