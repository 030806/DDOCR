import axios from 'axios'

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 10_000,
  headers: { Accept: 'application/json' },
})

apiClient.interceptors.request.use((config) => {
  const token = typeof window === 'undefined' ? null : window.localStorage.getItem('ddocr.auth.token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
