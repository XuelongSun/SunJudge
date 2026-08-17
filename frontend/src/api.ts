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
  pending_assignment_count?: number
  published_assignment_count?: number
}

export interface AdminClass extends PublicClass {
  invite_code: string
  invite_enabled: boolean
  roster_count: number
  assignment_count: number
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

export type AssignmentType = 'homework' | 'lab_report'
export type AssignmentStatus = 'draft' | 'published'
export type SubmissionStatus = 'submitted' | 'late'
export type TextFormat = 'text' | 'markdown'

export interface FileRules {
  allowed_extensions: string[]
  max_size_mb: number
  filename_template: string
}

export interface ProgramEvaluation {
  name: string
  input: string
  expected_output: string
  score_percent: number
  timeout_seconds?: number
  is_hidden?: boolean
}

export interface AiEvaluation {
  name: string
  input: string
  grading_criteria: string
  score_percent: number
}

export interface Submission {
  id: number
  assignment_id: number
  student_user_id: number
  student: User | null
  submitted_at: string
  original_filename: string
  file_size: number
  status: SubmissionStatus
  validation_result: {
    ok: boolean
    filename: string
    expected_filename: string
    extension: string
    size: number
    checks: Array<{ ok: boolean; message: string }>
  }
}

export interface Assignment {
  id: number
  course_id: number
  class_id: number
  title: string
  code: string
  type: AssignmentType
  description: string | null
  description_format: TextFormat
  deadline: string | null
  allow_late: boolean
  late_policy: string | null
  max_score: number
  file_rules: FileRules
  rubric: { text?: string; [key: string]: unknown }
  rubric_format: TextFormat
  program_evaluations: ProgramEvaluation[]
  ai_evaluations: AiEvaluation[]
  status: AssignmentStatus
  created_at: string
  updated_at: string
  published_at: string | null
  submission_count?: number
  latest_submission_count?: number
  submission?: Submission | null
}

export interface AssignmentSubmissionRow {
  roster: RosterEntry
  submission: Submission | null
  state: 'submitted' | 'missing'
}

export interface AssignmentPayload {
  title: string
  code: string
  type: AssignmentType
  description?: string
  description_format: TextFormat
  deadline?: string | null
  allow_late: boolean
  late_policy?: string
  max_score: number
  file_rules: FileRules
  rubric?: { text?: string }
  rubric_format: TextFormat
  program_evaluations: ProgramEvaluation[]
  ai_evaluations: AiEvaluation[]
  status: AssignmentStatus
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
    }),
  listManagedAssignments: (classId: number) =>
    request<{ class: AdminClass; assignments: Assignment[] }>(`/api/admin/classes/${classId}/assignments`),
  createAssignment: (classId: number, payload: AssignmentPayload) =>
    request<{ assignment: Assignment }>(`/api/admin/classes/${classId}/assignments`, {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  updateAssignment: (assignmentId: number, payload: AssignmentPayload) =>
    request<{ assignment: Assignment }>(`/api/admin/assignments/${assignmentId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    }),
  publishAssignment: (assignmentId: number) =>
    request<{ assignment: Assignment }>(`/api/admin/assignments/${assignmentId}/publish`, {
      method: 'POST'
    }),
  listAssignmentSubmissions: (assignmentId: number) =>
    request<{ assignment: Assignment; submissions: AssignmentSubmissionRow[] }>(`/api/admin/assignments/${assignmentId}/submissions`),
  listStudentAssignments: (classId: number) =>
    request<{ class: PublicClass; assignments: Assignment[] }>(`/api/classes/${classId}/assignments`),
  submitAssignment: (assignmentId: number, formData: FormData) =>
    request<{ submission: Submission }>(`/api/assignments/${assignmentId}/submissions`, {
      method: 'POST',
      headers: {},
      body: formData
    })
}
