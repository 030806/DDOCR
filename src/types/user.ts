export type CurrentUser = {
  id: string
  name: string
  email: string
  employeeNo: string
  department: string
  phoneMasked: string
  roleNames: string[]
  permissions: string[]
  avatarUrl: string | null
  lastLoginAt: string | null
}

export type RegisterInput = {
  name: string
  email?: string
  employeeNo: string
  department: string
  phone: string
  password: string
}
