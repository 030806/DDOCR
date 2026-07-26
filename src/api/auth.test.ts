import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from './client'
import { getCurrentUser, login, requestPasswordReset, resetPassword, updateProfile } from './auth'

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

const apiUser = {
  id: 'user-1', name: '林工', email: 'lin@example.com', employee_no: 'QC-042',
  department: '质量部', phone_masked: '138****2607', role_names: ['质量检测工程师'],
  permissions: ['ocr:read'], avatar_url: null, last_login_at: '2026-07-21T00:00:00Z',
}

describe('auth API', () => {
  it('logs in with a phone number and stores the token', async () => {
    const setItem = vi.fn()
    vi.stubGlobal('window', { localStorage: { setItem } })
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: { data: { access_token: 'token-1', token_type: 'bearer', user: apiUser }, request_id: 'req-login' },
    })
    await login('13800132607', 'Terminal123')
    expect(post).toHaveBeenCalledWith('/auth/login', { phone: '13800132607', password: 'Terminal123' })
    expect(setItem).toHaveBeenCalledWith('ddocr.auth.token', 'token-1')
  })

  it('maps the current backend user to the frontend model', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { data: apiUser, request_id: 'req-1' } })
    await expect(getCurrentUser()).resolves.toMatchObject({
      name: '林工', employeeNo: 'QC-042', phoneMasked: '138****2607', roleNames: ['质量检测工程师'],
    })
  })

  it('updates editable profile fields', async () => {
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({ data: { data: apiUser, request_id: 'req-2' } })
    await updateProfile({ name: '林工', department: '质量部', phone: '13800132607' })
    expect(patch).toHaveBeenCalledWith('/users/me', { name: '林工', department: '质量部', phone: '13800132607' })
  })

  it('requests and confirms a password reset', async () => {
    const post = vi.spyOn(apiClient, 'post')
      .mockResolvedValueOnce({ data: { data: { message: 'ok', expires_in: 600, development_code: '123456' } } })
      .mockResolvedValueOnce({ status: 204 })
    await expect(requestPasswordReset('13800132607', 'QC-042')).resolves.toMatchObject({ development_code: '123456' })
    expect(post).toHaveBeenNthCalledWith(1, '/auth/forgot-password', {
      phone: '13800132607', employee_no: 'QC-042',
    })
    await resetPassword('13800132607', '123456', 'Updated456')
    expect(post).toHaveBeenNthCalledWith(2, '/auth/reset-password', {
      phone: '13800132607', code: '123456', new_password: 'Updated456',
    })
  })
})
