export type Role = 'student' | 'teacher' | 'admin'

export type TeacherStatus = 'none' | 'pending' | 'approved' | 'rejected'

export interface User {
  id: number
  username: string
  role: Role
  student_id: string | null
  student_name: string | null
  student_no: string | null
  student_number: string | null
  teacher_status: TeacherStatus
  created_at: string
}

export interface PublicClass {
  id: number
  name: string
  alias: string
  course: {
    id: number
    name: string
    code: string
    semester: string
    teacher_id: number
    teacher_name: string | null
  }
  student?: {
    student_id: string | null
    student_no: string | null
    student_number: string | null
    student_name: string | null
    registration_status: 'imported' | 'registered' | null
  }
}

export interface AdminClass extends PublicClass {
  invite_code: string
  invite_enabled: boolean
  roster_count: number
}

export interface RosterEntry {
  id: number
  class_id: number
  student_name: string
  student_no: string | null
  student_number: string | null
  source_class: string | null
  student_id: string
  matched_user_id: number | null
  registration_status: 'imported' | 'registered'
  created_at: string
}

export interface RegisterPayload {
  username?: string
  password: string
  role: 'student' | 'teacher'
  student_id?: string
  student_name?: string
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData
  const response = await fetch(url, {
    credentials: 'include',
    headers: isFormData ? options.headers : { 'Content-Type': 'application/json', ...(options.headers ?? {}) },
    ...options
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.message ?? '请求失败')
  }
  return data as T
}

export const api = {
  me: () => request<{ user: User | null }>('/api/auth/me'),
  register: (payload: RegisterPayload) =>
    request<{ user: User }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  login: (username: string, password: string) =>
    request<{ user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    }),
  logout: () => request<{ message: string }>('/api/auth/logout', { method: 'POST' }),
  listPublicClasses: () => request<{ classes: PublicClass[] }>('/api/classes/public'),
  listMyClasses: () => request<{ classes: PublicClass[] }>('/api/classes/my'),
  listTeachers: (status = 'pending') => request<{ teachers: User[] }>(`/api/admin/teachers?status=${status}`),
  updateTeacherStatus: (teacherId: number, status: 'approved' | 'rejected') =>
    request<{ teacher: User }>(`/api/admin/teachers/${teacherId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status })
    }),
  listAdminClasses: () => request<{ classes: AdminClass[] }>('/api/admin/classes'),
  createClass: (payload: {
    class: { alias: string }
    course?: { name?: string; code?: string; semester?: string }
    roster?: Array<{ student_name: string; student_no: string; student_number?: string; source_class?: string }>
  }) =>
    request<{ class: AdminClass; roster_count: number }>('/api/admin/classes', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  updateClass: (
    classId: number,
    payload: { class?: { name?: string; invite_enabled?: boolean }; course?: { name?: string; code?: string; semester?: string } }
  ) =>
    request<{ class: AdminClass }>(`/api/admin/classes/${classId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    }),
  importRosterExcel: (formData: FormData) =>
    request<{ course_id: number; class_id: number; imported_count: number; updated_count: number }>(
      '/api/admin/classes/import-excel',
      {
        method: 'POST',
        headers: {},
        body: formData
      }
    ),
  listRoster: (classId: number) =>
    request<{ class: AdminClass; roster: RosterEntry[] }>(`/api/admin/classes/${classId}/roster`),
  createRosterEntry: (classId: number, payload: { student_name: string; student_no: string; student_number?: string; source_class?: string }) =>
    request<{ entry: RosterEntry }>(`/api/admin/classes/${classId}/roster`, {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  updateRosterEntry: (entryId: number, payload: { student_name: string; student_no: string; student_number?: string; source_class?: string }) =>
    request<{ entry: RosterEntry }>(`/api/admin/roster/${entryId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    }),
  deleteRosterEntry: (entryId: number) =>
    request<{ message: string }>(`/api/admin/roster/${entryId}`, {
      method: 'DELETE'
    })
}
