import type { CurrentUser, RegisterInput } from '../types/user'
import { apiClient } from './client'

export const AUTH_TOKEN_KEY = 'ddocr.auth.token'

type ApiEnvelope<T> = { data: T; request_id: string }
type ApiUser = {
  id: string; name: string; email: string; employee_no: string
  department: string; phone_masked: string; role_names: string[]
  permissions: string[]; avatar_url: string | null; last_login_at: string | null
}
type ApiSession = { access_token: string; token_type: string; user: ApiUser }

function mapUser(user: ApiUser): CurrentUser {
  return {
    id: user.id, name: user.name, email: user.email,
    employeeNo: user.employee_no, department: user.department,
    phoneMasked: user.phone_masked, roleNames: user.role_names,
    permissions: user.permissions, avatarUrl: user.avatar_url,
    lastLoginAt: user.last_login_at,
  }
}

function storeSession(session: ApiSession) {
  window.localStorage.setItem(AUTH_TOKEN_KEY, session.access_token)
  return mapUser(session.user)
}

export async function login(phone: string, password: string) {
  const response = await apiClient.post<ApiEnvelope<ApiSession>>('/auth/login', { phone, password })
  return storeSession(response.data.data)
}

export async function register(input: RegisterInput) {
  const response = await apiClient.post<ApiEnvelope<ApiSession>>('/auth/register', {
    name: input.name, email: input.email || null, employee_no: input.employeeNo,
    department: input.department, phone: input.phone, password: input.password,
  })
  return storeSession(response.data.data)
}

export async function requestPasswordReset(phone: string, employeeNo: string) {
  const response = await apiClient.post<ApiEnvelope<{
    message: string
    expires_in: number
    development_code?: string
  }>>('/auth/forgot-password', { phone, employee_no: employeeNo })
  return response.data.data
}

export async function resetPassword(phone: string, code: string, newPassword: string) {
  await apiClient.post('/auth/reset-password', {
    phone,
    code,
    new_password: newPassword,
  })
}

export async function getCurrentUser() {
  const response = await apiClient.get<ApiEnvelope<ApiUser>>('/users/me')
  return mapUser(response.data.data)
}

export async function updateProfile(value: { name: string; department: string; phone?: string }) {
  const response = await apiClient.patch<ApiEnvelope<ApiUser>>('/users/me', value)
  return mapUser(response.data.data)
}

export async function changePassword(currentPassword: string, newPassword: string) {
  await apiClient.post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

export async function logout() {
  try { await apiClient.post('/auth/logout') } finally { window.localStorage.removeItem(AUTH_TOKEN_KEY) }
}
