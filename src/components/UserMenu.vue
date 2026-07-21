<script setup lang="ts">
import { ref } from 'vue'
import { KeyOutlined, LogoutOutlined, UserOutlined } from '@ant-design/icons-vue'
import { Modal, message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'
import ProfileDrawer from './ProfileDrawer.vue'
import PasswordModal from './PasswordModal.vue'

const profileOpen = ref(false)
const passwordOpen = ref(false)
const router = useRouter()
const { user, logout } = useAuth()

function handleMenu({ key }: { key: string | number }) {
  if (key === 'profile') profileOpen.value = true
  if (key === 'password') passwordOpen.value = true
  if (key === 'logout') {
    Modal.confirm({
      title: '退出登录？',
      content: '退出后需要重新登录，任务和设置数据不会被删除。',
      okText: '退出登录',
      cancelText: '取消',
      onOk: async () => {
        await logout()
        message.success('已退出登录')
        await router.replace('/auth')
      },
    })
  }
}
</script>

<template>
  <a-dropdown :trigger="['click']" placement="bottomRight">
    <button class="avatar" aria-label="用户菜单">{{ user?.name?.slice(0, 1) || '用' }}</button>
    <template #overlay>
      <a-menu class="user-dropdown" @click="handleMenu">
        <a-menu-item key="identity" disabled><div class="user-identity"><b>{{ user?.name || '当前用户' }}</b><small>{{ user?.roleNames?.join('、') || '已登录' }}</small></div></a-menu-item>
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
