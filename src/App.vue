<script setup lang="ts">
import AppHeader from './components/AppHeader.vue'
import SettingsDrawer from './components/SettingsDrawer.vue'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from './composables/useAuth'

const settingsOpen = ref(false)
const route = useRoute()
const router = useRouter()
const { restoreSession } = useAuth()

onMounted(async () => {
  if (route.name !== 'auth' && !await restoreSession()) await router.replace('/auth')
})
</script>

<template>
  <a-config-provider :theme="{ token: { colorPrimary: '#168b6c', borderRadius: 8, fontFamily: `'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif` } }">
    <div class="app-shell">
      <AppHeader v-if="route.name !== 'auth'" @open-settings="settingsOpen = true" />
      <RouterView />
      <SettingsDrawer v-if="route.name !== 'auth'" v-model:open="settingsOpen" />
    </div>
  </a-config-provider>
</template>
