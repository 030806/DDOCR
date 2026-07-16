<script setup lang="ts">
import { ref } from 'vue'
import { KeyOutlined, LogoutOutlined, UserOutlined } from '@ant-design/icons-vue'
import { Modal, message } from 'ant-design-vue'
import { mockUser } from '../mock/user'
import ProfileDrawer from './ProfileDrawer.vue'
import PasswordModal from './PasswordModal.vue'

const profileOpen = ref(false)
const passwordOpen = ref(false)

function handleMenu({ key }: { key: string | number }) {
  if (key === 'profile') profileOpen.value = true
  if (key === 'password') passwordOpen.value = true
  if (key === 'logout') {
    Modal.confirm({
      title: '退出登录？',
      content: '当前为前端 Mock 登录状态，退出不会清除任务和设置。',
      okText: '退出登录',
      cancelText: '取消',
      onOk: () => message.success('已退出登录（Mock）'),
    })
  }
}
</script>

<template>
  <a-dropdown :trigger="['click']" placement="bottomRight">
    <button class="avatar" aria-label="用户菜单">{{ mockUser.displayInitial }}</button>
    <template #overlay>
      <a-menu class="user-dropdown" @click="handleMenu">
        <a-menu-item key="identity" disabled><div class="user-identity"><b>{{ mockUser.name }}</b><small>{{ mockUser.role }}</small></div></a-menu-item>
        <a-menu-divider />
        <a-menu-item key="profile"><UserOutlined /> 个人资料</a-menu-item>
        <a-menu-item key="password"><KeyOutlined /> 修改密码</a-menu-item>
        <a-menu-divider />
        <a-menu-item key="logout" danger><LogoutOutlined /> 退出登录</a-menu-item>
      </a-menu>
    </template>
  </a-dropdown>
  <ProfileDrawer v-model:open="profileOpen" />
  <PasswordModal v-model:open="passwordOpen" />
</template>
