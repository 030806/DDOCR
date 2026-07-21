import { readonly, ref } from 'vue'
import * as authApi from '../api/auth'
import type { CurrentUser, RegisterInput } from '../types/user'

const user = ref<CurrentUser>()
const loading = ref(false)

export function useAuth() {
  async function restoreSession() {
    if (!window.localStorage.getItem(authApi.AUTH_TOKEN_KEY)) return false
    loading.value = true
    try { user.value = await authApi.getCurrentUser(); return true }
    catch { window.localStorage.removeItem(authApi.AUTH_TOKEN_KEY); user.value = undefined; return false }
    finally { loading.value = false }
  }

  async function login(phone: string, password: string) {
    user.value = await authApi.login(phone, password)
  }

  async function register(input: RegisterInput) {
    user.value = await authApi.register(input)
  }

  async function logout() {
    await authApi.logout()
    user.value = undefined
  }

  async function saveProfile(value: { name: string; department: string; phone?: string }) {
    user.value = await authApi.updateProfile(value)
  }

  return { user: readonly(user), loading: readonly(loading), restoreSession, login, register, logout, saveProfile }
}
