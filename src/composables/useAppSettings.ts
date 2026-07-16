import { readonly, ref } from 'vue'
import { DEFAULT_APP_SETTINGS, type AppSettings } from '../types/settings'
import { normalizeSettings, parseStoredSettings, SETTINGS_STORAGE_KEY } from '../settingsStorage'

const initialSettings = typeof window === 'undefined' ? { ...DEFAULT_APP_SETTINGS } : parseStoredSettings(window.localStorage.getItem(SETTINGS_STORAGE_KEY))
const settings = ref<AppSettings>(initialSettings)

function persist() {
  if (typeof window !== 'undefined') window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings.value))
}

export function useAppSettings() {
  function updateSettings(value: AppSettings) {
    settings.value = normalizeSettings(value)
    persist()
  }

  function resetSettings() {
    settings.value = { ...DEFAULT_APP_SETTINGS }
    persist()
  }

  return { settings: readonly(settings), updateSettings, resetSettings }
}
