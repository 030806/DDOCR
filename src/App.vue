<script setup lang="ts">
import AppHeader from './components/AppHeader.vue'
import SettingsDrawer from './components/SettingsDrawer.vue'
import { ref } from 'vue'

const settingsOpen = ref(false)
</script>

<template>
  <a-config-provider :theme="{ token: { colorPrimary: '#168b6c', borderRadius: 8, fontFamily: `'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif` } }">
    <div class="app-shell">
      <AppHeader @open-settings="settingsOpen = true" />
      <RouterView />
      <SettingsDrawer v-model:open="settingsOpen" />
    </div>
  </a-config-provider>
</template>
