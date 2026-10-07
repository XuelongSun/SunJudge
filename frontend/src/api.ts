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
  completed_assignment_count?: number
  published_grade_count?: number
  average_score?: number | null
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
export type SubmissionStatus = 'uploaded' | 'submitted' | 'late'
export type TextFormat = 'markdown'
export type GradingStatus = 'pending' | 'auto_graded' | 'reviewed' | 'published'
export type JudgeStatus = 'accepted' | 'wrong_answer' | 'runtime_error' | 'time_limit_exceeded' | 'skipped' | 'error'
export type StudentSubmissionState = 'unread' | 'read' | 'uploaded' | 'submitted'
export type TeacherGradingState = 'needs_grading' | 'needs_review' | 'reviewed' | 'published'

export interface FileRules {
  allowed_extensions: string[]
  max_size_mb: number
  filename_template: string
}

export interface SubmissionRequirement extends FileRules {
  key: string
  label: string
  required: boolean
}

export interface ProgramTestCase {
  name: string
  args: string
  expected_output: string
  score_percent: number
  timeout_seconds?: number
  is_hidden?: boolean
}

export interface ProgramEvaluation {
  name: string
  input_file_key: string
  score_percent?: number
  cases: ProgramTestCase[]
}

export interface AiEvaluation {
  name: string
  input_file_key: string
  input: string
  grading_criteria?: string
  criteria_items: Array<{
    content: string
    weight: number
  }>
  score_percent: number
}

export interface Submission {
  id: number
  assignment_id: number
  student_user_id: number
  student: User | null
  submitted_at: string
  original_filename: string
  submission_item_key: string
  submission_item_label: string | null
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
  grading_result: GradingResult | null
  latest_judge_run: JudgeRun | null
}

export interface JudgeRun {
  id: number
  submission_id: number
  status: JudgeStatus
  score: number
  details: {
    message?: string
    cases?: Array<{
      name: string
      status: JudgeStatus
      score: number
      score_percent: number
      timeout_seconds: number
      is_hidden: boolean
      args?: string | null
      expected_output?: string | null
      stdout?: string | null
      stderr?: string | null
      diff?: {
        line: number | null
        expected: string
        actual: string
      } | null
    }>
    [key: string]: unknown
  }
  created_at: string
}

export interface GradingResult {
  id: number
  submission_id?: number
  assignment_id?: number
  student_user_id?: number
  auto_score: number | null
  llm_score: number | null
  final_score: number | null
  feedback: string | null
  teacher_comment: string | null
  reviewed_by: number | null
  status: GradingStatus
  llm_details: {
    status?: string
    message?: string
    modules?: unknown[]
    manual_file_keys?: string[]
    file_reviews?: FileReview[]
    feedback_report_markdown?: string
    [key: string]: unknown
  }
  created_at: string
  updated_at: string
}

export interface TeacherLLMConfig {
  id: number
  teacher_id: number
  provider: string
  base_url: string
  model: string
  enabled: boolean
  has_api_key: boolean
  created_at: string
  updated_at: string
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
  submission_requirements: SubmissionRequirement[]
  rubric: { text?: string; [key: string]: unknown }
  rubric_format: TextFormat
  program_evaluations: ProgramEvaluation[]
  ai_evaluations: AiEvaluation[]
  status: AssignmentStatus
  created_at: string
  updated_at: string
  published_at: string | null
  read_at?: string | null
  expected_submission_count?: number
  submission_count?: number
  feedback_count?: number
  latest_submission_count?: number
  submission?: Submission | null
  submissions?: Submission[]
  assignment_grade?: GradingResult | null
}

export interface AssignmentGradeAnalysis {
  expected_count: number
  submitted_count: number
  missing_count: number
  submitted_rate: number | null
  reviewed_or_published_count: number
  published_count: number
  average_score: number | null
  average_submit_days_after_publish: number | null
  average_submit_days_before_deadline: number | null
  max_score: number
}
export interface AssignmentSubmissionRow {
  roster: RosterEntry
  submission: Submission | null
  submissions: Submission[]
  assignment_grade: GradingResult | null
  state: 'submitted' | 'missing'
  student_state?: StudentSubmissionState
  teacher_state?: TeacherGradingState
  final_score?: number | null
  read_at?: string | null
}

export type FileReviewStatus = 'pending' | 'confirmed'

export interface FileReview {
  submission_id?: number | null
  submission_item_key: string
  submission_item_label: string
  filename: string
  review_kind: 'manual' | 'program' | 'ai'
  review_status?: FileReviewStatus
  score: number
  weight_percent?: number
  max_score?: number
  comment: string
}

export interface SubmissionPreview {
  submission: Submission
  previewable: boolean
  content: string | null
  message?: string
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
  submission_requirements: SubmissionRequirement[]
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
  updateAssignment: (assignmentId: number, payload: AssignmentPayload & { reset_grading?: boolean }) =>
    request<{ assignment: Assignment; reset_grading?: boolean; rerun_count?: number }>(`/api/admin/assignments/${assignmentId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    }),
  publishAssignment: (assignmentId: number) =>
    request<{ assignment: Assignment }>(`/api/admin/assignments/${assignmentId}/publish`, {
      method: 'POST'
    }),
  deleteAssignment: (assignmentId: number) =>
    request<{ message: string; class_id: number }>(`/api/admin/assignments/${assignmentId}`, {
      method: 'DELETE'
    }),
  listAssignmentSubmissions: (assignmentId: number) =>
    request<{ assignment: Assignment; analysis: AssignmentGradeAnalysis; submissions: AssignmentSubmissionRow[] }>(`/api/admin/assignments/${assignmentId}/submissions`),
  listAssignmentGrades: (assignmentId: number) =>
    request<{ assignment: Assignment; class: AdminClass; analysis: AssignmentGradeAnalysis; rows: Array<Record<string, unknown>> }>(`/api/admin/assignments/${assignmentId}/grades`),
  assignmentGradesCsvUrl: (assignmentId: number) => `/api/admin/assignments/${assignmentId}/grades.csv`,
  exportScoreManagerCommands: (assignmentId: number, params: { field: string; command_type: 'regular' | 'lab'; group_same_score: boolean }) => {
    const query = new URLSearchParams({
      field: params.field,
      command_type: params.command_type,
      group_same_score: params.group_same_score ? 'true' : 'false'
    })
    return request<{ assignment: Assignment; export: { field: string; command_type: 'regular' | 'lab'; group_same_score: boolean; commands: string; lines: string[]; exported_count: number; skipped: Array<Record<string, string>> } }>(`/api/admin/assignments/${assignmentId}/scoremanager-commands?${query.toString()}`)
  },
  rerunSubmissionGrading: (submissionId: number) =>
    request<{ submission: Submission; assignment_grade: GradingResult }>(`/api/admin/submissions/${submissionId}/rerun-grading`, {
      method: 'POST'
    }),
  returnSubmissionForResubmit: (submissionId: number) =>
    request<{ message: string; assignment: Assignment }>(`/api/admin/submissions/${submissionId}/return`, {
      method: 'POST'
    }),
  reviewSubmissionGrade: (
    submissionId: number,
    payload: { final_score: number; feedback?: string; teacher_comment?: string; reason?: string; status?: GradingStatus; file_reviews?: FileReview[] }
  ) =>
    request<{ submission: Submission; assignment_grade: GradingResult; grading_result: GradingResult }>(`/api/admin/submissions/${submissionId}/grade`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    }),
  getLLMConfig: () => request<{ config: TeacherLLMConfig | null }>('/api/admin/llm-config'),
  submissionDownloadUrl: (submissionId: number) => `/api/admin/submissions/${submissionId}/download`,
  previewSubmission: (submissionId: number) => request<SubmissionPreview>(`/api/admin/submissions/${submissionId}/preview`),
  saveLLMConfig: (payload: { provider?: string; base_url: string; model: string; api_key?: string; enabled: boolean }) =>
    request<{ config: TeacherLLMConfig }>('/api/admin/llm-config', {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),
  listStudentAssignments: (classId: number) =>
    request<{ class: PublicClass; assignments: Assignment[] }>(`/api/classes/${classId}/assignments`),
  markAssignmentRead: (assignmentId: number) =>
    request<{ read: { id: number; assignment_id: number; student_user_id: number; read_at: string }; assignment: Assignment }>(
      `/api/assignments/${assignmentId}/read`,
      { method: 'POST' }
    ),
  submitAssignment: (assignmentId: number, formData: FormData) =>
    request<{ submission: Submission; assignment_grade: GradingResult | null }>(`/api/assignments/${assignmentId}/submissions`, {
      method: 'POST',
      headers: {},
      body: formData
    }),
  confirmAssignmentSubmission: (assignmentId: number) =>
    request<{ assignment: Assignment; assignment_grade: GradingResult | null; queue_status: 'queued' | 'inline' }>(`/api/assignments/${assignmentId}/confirm-submission`, {
      method: 'POST'
    })
}