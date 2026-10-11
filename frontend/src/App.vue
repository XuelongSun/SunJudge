<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { homeworkMarkdown, feedbackMarkdown, reportDate, deadlineFromInput } from './reportTemplates'
import { aiResultRows } from './gradingPresentation'
import { progressPercent, filenamePreview, insertAtSelection } from './presentation'
import ProgressCard from './components/ProgressCard.vue'
import { renderContent } from './markdown'
import MarkdownEditor from './components/MarkdownEditor.vue'
import ImageLibrary from './components/ImageLibrary.vue'
import type { MarkdownDocument } from './api'
import 'highlight.js/styles/github.css'
import 'katex/dist/katex.min.css'
import {
  Check,
  CirclePlus,
  Close,
  CopyDocument,
  Delete,
  DocumentAdd,
  Download,
  Edit,
  Files,
  Moon,
  Refresh,
  Sunny,
  SwitchButton,
  Upload,
  View
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type InputInstance } from 'element-plus'
import {
  api,
  type AdminClass,
  type Assignment,
  type AssignmentPayload,
  type AssignmentGradeAnalysis,
  type AssignmentSubmissionRow,
  type AssignmentType,
  type AiEvaluation,
  type FileReview,
  type GradingResult,
  type GradingStatus,
  type ProgramEvaluation,
  type ProgramTestCase,
  type PublicClass,
  type Role,
  type RosterEntry,
  type Submission,
  type SubmissionPreview,
  type SubmissionRequirement,
  type TeacherLLMConfig,
  type TeacherStatus,
  type TextFormat,
  type User
} from './api'

type AiReportCriterion = {
  content?: string
  weight?: number
}

type AiReportModule = {
  input_file_key?: string
  name?: string
  score_percent?: number
  criteria_weight_total?: number
  input?: string
  status?: string
  message?: string
  criteria_items?: AiReportCriterion[]
  score?: number
  max_score?: number
  summary?: string
  criteria_results?: Array<AiReportCriterion & { criterion_id?: number; score?: number; max_score?: number; reason?: string; comment?: string }>
}

const currentUser = ref<User | null>(null)
const teachers = ref<User[]>([])
const adminClasses = ref<AdminClass[]>([])
const studentClasses = ref<PublicClass[]>([])
const selectedClassId = ref<number | undefined>()
const selectedStudentClassId = ref<number | undefined>()
const roster = ref<RosterEntry[]>([])
const selectedRoster = ref<RosterEntry[]>([])
const batchRosterDialogVisible = ref(false)
const batchSourceClass = ref('')
const batchRosterLoading = ref(false)
const filenamePreviewStudent = ref<RosterEntry | null>(null)
const filenameTemplateInput = ref<InputInstance>()
const filenameSelection = reactive({ start: 0, end: 0 })
const managedAssignments = ref<Assignment[]>([])
const studentAssignments = ref<Assignment[]>([])
const submissionRows = ref<AssignmentSubmissionRow[]>([])
const testSubmissionRows = ref<AssignmentSubmissionRow[]>([])
const gradeAnalysis = ref<AssignmentGradeAnalysis | null>(null)
const selectedAssignmentId = ref<number | undefined>()
const selectedStudentAssignmentId = ref<number | undefined>()
const selectedFile = ref<File | null>(null)
const selectedSubmissionFile = ref<File | null>(null)
const loading = ref(false)
const teacherLoading = ref(false)
const classLoading = ref(false)
const rosterLoading = ref(false)
const assignmentLoading = ref(false)
const submissionLoading = ref(false)
const authMode = ref<'login' | 'register'>('login')
const registerRole = ref<'student' | 'teacher'>('student')
const theme = ref<'light' | 'dark'>('light')

const classDialogVisible = ref(false)
const importDialogVisible = ref(false)
const rosterInput = ref<HTMLInputElement>()
const submissionFileInput = ref<HTMLInputElement>()
const parsedStudentCount = ref(0)
const imageLibraryVisible = ref(false)
const copyDialogVisible = ref(false)
const copyingAssignment = ref<Assignment | null>(null)
const copyClassId = ref<number>()
const copyCode = ref('')
const copyLoading = ref(false)

function deadlinePayload() { return deadlineFromInput(assignmentForm.deadline) }
function openCopyAssignment(assignment: Assignment) {
  copyingAssignment.value = assignment
  copyClassId.value = undefined
  copyCode.value = assignment.code
  copyDialogVisible.value = true
}
async function copyAssignmentSettings() {
  if (!copyingAssignment.value || !copyClassId.value) return
  copyLoading.value = true
  try {
    await api.copyAssignment(copyingAssignment.value.id, copyClassId.value, copyCode.value)
    copyDialogVisible.value = false
    ElMessage.success('已迁移为目标班级的草稿，请检查截止时间和设置后发布')
    await loadTeacherDashboard()
  } catch (error) { ElMessage.error((error as Error).message) }
  finally { copyLoading.value = false }
}
const rosterDrawerVisible = ref(false)
const assignmentsDrawerVisible = ref(false)
const assignmentDialogVisible = ref(false)
const assignmentPreviewDrawerVisible = ref(false)
const submissionRequirementDialogVisible = ref(false)
const programEvaluationDialogVisible = ref(false)
const aiEvaluationDialogVisible = ref(false)
const submissionsDrawerVisible = ref(false)
const submissionDialogVisible = ref(false)
const markdownDialogVisible = ref(false)
const studentMarkdownDocument = ref<MarkdownDocument | null>(null)
const studentMarkdownContent = ref('')
const teacherMarkdownDocument = ref<MarkdownDocument | null>(null)
const teacherMarkdownEditor = ref<{ flush: () => Promise<void> }>()
const studentMarkdownEditor = ref<{ flush: () => Promise<void> }>()
let teacherEditorSession = 0

const gradeReviewDialogVisible = ref(false)
const submissionPreviewDialogVisible = ref(false)
const feedbackPreviewDialogVisible = ref(false)
const studentFeedbackDialogVisible = ref(false)
const scoreManagerDialogVisible = ref(false)
const llmConfigDialogVisible = ref(false)
const studentDialogVisible = ref(false)
const classMetaDialogVisible = ref(false)
const editingRosterId = ref<number | null>(null)
const editingClassId = ref<number | null>(null)
const editingAssignmentId = ref<number | null>(null)
const editingAssignmentOriginalStatus = ref<Assignment['status'] | null>(null)
const editingRequirementIndex = ref<number | null>(null)
const editingProgramEvaluationIndex = ref<number | null>(null)
const editingAiEvaluationIndex = ref<number | null>(null)
const submittingAssignment = ref<Assignment | null>(null)
const submittingRequirement = ref<SubmissionRequirement | null>(null)
const reviewingSubmission = ref<Submission | null>(null)
const reviewingSubmissionRow = ref<AssignmentSubmissionRow | null>(null)
const reviewFileForms = ref<FileReview[]>([])
const previewingSubmission = ref<Submission | null>(null)
const submissionPreview = ref<SubmissionPreview | null>(null)
const llmConfig = ref<TeacherLLMConfig | null>(null)
const scoreManagerCommands = ref('')

const loginForm = reactive({
  username: '',
  password: ''
})

const registerForm = reactive({
  username: '',
  password: '',
  student_id: '',
  student_name: ''
})

const importForm = reactive({
  class_id: undefined as number | undefined
})

const classForm = reactive({
  class_alias: '',
  course_name: '',
  course_code: '',
  semester: ''
})

const classMetaForm = reactive({
  class_name: '',
  course_name: '',
  course_code: '',
  semester: ''
})

const rosterForm = reactive({
  student_name: '',
  student_no: '',
  student_number: '',
  source_class: ''
})

const assignmentForm = reactive({
  title: '',
  code: '',
  type: 'homework' as AssignmentType,
  description: '',
  description_format: 'markdown' as TextFormat,
  deadline: '',
  allow_late: false,
  late_policy: '',
  max_score: 100,
  allowed_extensions: ['.py', '.md', '.zip', '.jpg', '.png'] as string[],
  max_size_mb: 5,
  filename_template: '{student_id}_{assignment_code}{extension}',
  submission_requirements: [
    {
      key: 'main',
      label: '提交文件',
      allowed_extensions: ['.py', '.md', '.zip', '.jpg', '.png'],
      max_size_mb: 5,
      filename_template: '{student_id}_{assignment_code}{extension}',
      required: true,
      weight_percent: 100
    }
  ] as SubmissionRequirement[],
  rubric: '',
  rubric_format: 'markdown' as TextFormat,
  program_evaluations: [] as ProgramEvaluation[],
  ai_evaluations: [] as AiEvaluation[]
})

const submissionRequirementForm = reactive<SubmissionRequirement>({
  key: '',
  label: '',
  allowed_extensions: ['.md'],
  max_size_mb: 5,
  filename_template: '{student_id}_{assignment_code}{extension}',
  required: true,
  weight_percent: 0
})

const programEvaluationForm = reactive<ProgramEvaluation>({
  name: '',
  input_file_key: 'main',
  cases: []
})

const aiEvaluationForm = reactive<AiEvaluation>({
  name: '',
  input_file_key: 'main',
  input: '',
  criteria_items: [],
  score_percent: 10
})

const gradeReviewForm = reactive({
  final_score: 0,
  feedback: '',
  teacher_comment: '',
  reason: '',
  status: 'reviewed' as GradingStatus
})

const scoreManagerForm = reactive({
  field: 'homework',
  command_type: 'regular' as 'regular' | 'lab',
  group_same_score: true
})
const llmConfigForm = reactive({
  provider: 'deepseek',
  base_url: '',
  model: '',
  api_key: '',
  enabled: true
})

const isAdmin = computed(() => currentUser.value?.role === 'admin')
const isTeacher = computed(() => currentUser.value?.role === 'teacher')
const pendingTeachers = computed(() => teachers.value.filter((teacher) => teacher.teacher_status === 'pending'))
const currentClass = computed(() => adminClasses.value.find((item) => item.id === selectedClassId.value))
const currentStudentClass = computed(() => studentClasses.value.find((item) => item.id === selectedStudentClassId.value))
const selectedAssignment = computed(() => managedAssignments.value.find((item) => item.id === selectedAssignmentId.value))
const selectedStudentAssignment = computed(() => studentAssignments.value.find((item) => item.id === selectedStudentAssignmentId.value))
const reviewTotalScore = computed(() => Number(Math.min(selectedAssignment.value?.max_score ?? 100, reviewFileForms.value.reduce((total, item) => total + (reviewWeightPercent(item) > 0 ? Number(item.score || 0) : 0), 0)).toFixed(2)))
const reviewWeightTotal = computed(() => Number(reviewFileForms.value.reduce((total, item) => total + reviewWeightPercent(item), 0).toFixed(2)))
const reviewWeightValid = computed(() => Math.abs(reviewWeightTotal.value - 100) < 0.01)
const previewAssignment = computed(() => {
  if (selectedAssignment.value) {
    return selectedAssignment.value
  }
  return {
    id: 0,
    course_id: currentClass.value?.course.id ?? 0,
    class_id: selectedClassId.value ?? 0,
    title: assignmentForm.title || '未命名作业',
    code: assignmentForm.code || 'draft',
    type: assignmentForm.type,
    description: assignmentForm.description,
    description_format: assignmentForm.description_format,
    deadline: deadlinePayload(),
    allow_late: assignmentForm.allow_late,
    late_policy: assignmentForm.late_policy || null,
    max_score: Number(assignmentForm.max_score),
    file_rules: {
      allowed_extensions: assignmentForm.allowed_extensions,
      max_size_mb: Number(assignmentForm.max_size_mb),
      filename_template: assignmentForm.filename_template
    },
    submission_requirements: assignmentForm.submission_requirements,
    rubric: { text: '' },
    rubric_format: 'markdown',
    program_evaluations: assignmentForm.program_evaluations.map((item) => normalizeProgramEvaluationForForm(item)),
    ai_evaluations: assignmentForm.ai_evaluations.map((item) => normalizeAiEvaluationForForm(item)),
    status: 'draft',
    created_at: '',
    updated_at: '',
    published_at: null,
    submission: null
  } as Assignment
})
const selectedClassRosterCount = computed(() => currentClass.value?.roster_count ?? roster.value.length)
const submissionFilenameExamples = computed(() => {
  const example = filenamePreviewStudent.value
  const alias = currentClass.value?.alias ?? 'OS202601'
  return submissionRequirementForm.allowed_extensions.map(extension => filenamePreview(submissionRequirementForm.filename_template, {
    course_alias: alias, student_id: example?.student_id ?? `${alias}-06`, student_no: example?.student_no ?? '06',
    name: example?.student_name ?? '示例学生', assignment_code: assignmentForm.code || 'hw1', extension
  }))
})
const accountDisplayName = computed(() => {
  if (!currentUser.value) {
    return ''
  }
  return currentUser.value.role === 'student' ? currentUser.value.student_name ?? '' : currentUser.value.username
})
const expectedSubmissionName = computed(() => {
  if (!submittingAssignment.value || !submittingRequirement.value || !currentStudentClass.value) {
    return ''
  }
  const fileExt = selectedSubmissionFile.value ? `.${selectedSubmissionFile.value.name.split('.').pop()}` : '{extension}'
  const student = currentStudentClass.value.student
  return submittingRequirement.value.filename_template
    .replace('{student_id}', student?.student_id ?? '')
    .replace('{student_no}', student?.student_no ?? '')
    .replace('{assignment_code}', submittingAssignment.value.code)
    .replace('{course_alias}', currentStudentClass.value.alias)
    .replace('{name}', student?.student_name ?? currentUser.value?.student_name ?? '')
    .replace('{extension}', fileExt)
})

const roleLabelMap: Record<Role, string> = {
  admin: '管理员',
  teacher: '教师',
  student: '学生'
}

const teacherStatusLabelMap: Record<TeacherStatus, string> = {
  none: '未申请',
  pending: '待审批',
  approved: '已通过',
  rejected: '已拒绝'
}

const currentRoleLabel = computed(() => roleLabelMap[currentUser.value?.role ?? 'student'])

const assignmentTypeOptions = [
  { label: '作业', value: 'homework' },
  { label: '实验报告', value: 'lab_report' }
]

const extensionOptions = [
  { label: '.md', value: '.md' },
  { label: '.py', value: '.py' },
  { label: '.zip', value: '.zip' },
  { label: '.jpg', value: '.jpg' },
  { label: '.png', value: '.png' }
]

function teacherStatusLabel(status: TeacherStatus) {
  return teacherStatusLabelMap[status]
}

function teacherStatusTagType(status: TeacherStatus) {
  if (status === 'approved') {
    return 'success'
  }
  if (status === 'rejected') {
    return 'danger'
  }
  if (status === 'pending') {
    return 'warning'
  }
  return 'info'
}

function registrationStatusLabel(status: RosterEntry['registration_status']) {
  return status === 'registered' ? '已注册' : '未注册'
}

function classesForTeacher(teacherId: number) {
  return adminClasses.value.filter((item) => item.course.teacher_id === teacherId)
}

function assignmentTypeLabel(type: AssignmentType) {
  return assignmentTypeOptions.find((item) => item.value === type)?.label ?? type
}

function assignmentStatusLabel(status: Assignment['status']) {
  return status === 'published' ? '已发布' : '草稿'
}

function assignmentStatusType(status: Assignment['status']) {
  return status === 'published' ? 'success' : 'info'
}

function assignmentSubmissionSummary(assignment: Assignment) {
  const expected = assignment.expected_submission_count ?? currentClass.value?.roster_count ?? 0
  const submitted = assignment.submission_count ?? 0
  return `${submitted}/${expected}`
}

function assignmentFeedbackSummary(assignment: Assignment) {
  const submitted = assignment.submission_count ?? 0
  const feedback = assignment.feedback_count ?? 0
  return `${feedback}/${submitted || 0}`
}

function isConfirmedSubmission(submission: Submission) {
  return submission.status === 'submitted' || submission.status === 'late'
}

function uploadedRequiredKeys(assignment: Assignment) {
  const keys = new Set((assignment.submissions ?? []).map((submission) => submission.submission_item_key))
  Object.entries(assignment.markdown_drafts ?? {}).forEach(([key, draft]) => { if (draft.has_content) keys.add(key) })
  return keys
}

function confirmedRequiredKeys(assignment: Assignment) {
  return new Set((assignment.submissions ?? []).filter(isConfirmedSubmission).map((submission) => submission.submission_item_key))
}

function hasAllRequiredUploads(assignment: Assignment) {
  const required = assignment.submission_requirements.filter((item) => item.required)
  const uploadedKeys = uploadedRequiredKeys(assignment)
  return required.length > 0 && required.every((item) => uploadedKeys.has(item.key))
}

function hasAllRequiredConfirmedSubmissions(assignment: Assignment) {
  if (Object.values(assignment.markdown_drafts ?? {}).some(draft => draft.pending_changes)) return false
  const required = assignment.submission_requirements.filter((item) => item.required)
  const confirmedKeys = confirmedRequiredKeys(assignment)
  return required.length > 0 && required.every((item) => confirmedKeys.has(item.key))
}

function submissionStatusLabel(assignment: Assignment) {
  if (hasAllRequiredConfirmedSubmissions(assignment)) {
    return (assignment.submissions ?? []).some((submission) => submission.status === 'late') ? '已迟交' : '已提交'
  }
  if (hasAllRequiredUploads(assignment)) {
    return '待确认'
  }
  return '未提交'
}

function submissionStatusType(assignment: Assignment) {
  if (hasAllRequiredConfirmedSubmissions(assignment)) {
    return (assignment.submissions ?? []).some((submission) => submission.status === 'late') ? 'warning' : 'success'
  }
  if (hasAllRequiredUploads(assignment)) {
    return 'warning'
  }
  return 'info'
}
function requirementLabel(assignment: Assignment, key: string) {
  return assignment.submission_requirements.find((item) => item.key === key)?.label ?? key
}

function requirementLabelForForm(key: string) {
  return assignmentForm.submission_requirements.find((item) => item.key === key)?.label ?? key
}

function aiCriteriaWeightTotal(evaluation: AiEvaluation) {
  return normalizeAiEvaluationForForm(evaluation).criteria_items.reduce((total, item) => total + Number(item.weight || 0), 0)
}

function submissionForRequirement(assignment: Assignment, key: string) {
  return assignment.submissions?.find((submission) => submission.submission_item_key === key) ?? null
}

function requirementStatusLabel(assignment: Assignment, key: string) {
  const draft = assignment.markdown_drafts?.[key]
  if (draft?.pending_changes) return draft.has_content ? '草稿待提交' : '草稿为空'
  const submission = submissionForRequirement(assignment, key)
  if (!submission) {
    return '未上传'
  }
  return isConfirmedSubmission(submission) ? '已确认' : '已上传'
}

function requirementStatusType(assignment: Assignment, key: string) {
  if (assignment.markdown_drafts?.[key]?.pending_changes) return 'warning'
  const submission = submissionForRequirement(assignment, key)
  if (!submission) {
    return 'info'
  }
  return isConfirmedSubmission(submission) ? 'success' : 'warning'
}

function submissionActionLabel(assignment: Assignment, key: string) {
  if (assignment.assignment_grade?.status === 'published') {
    return '已反馈'
  }
  if (assignment.submission_requirements.find(item => item.key === key)?.allowed_extensions.includes('.md')) return '在线编辑'
  return submissionForRequirement(assignment, key) ? '重新上传' : '上传文件'
}

function canSubmitRequirement(assignment: Assignment) {
  return !assignment.is_expired && assignment.assignment_grade?.status !== 'published'
}

function canConfirmAssignmentSubmission(assignment: Assignment) {
  return canSubmitRequirement(assignment) && hasAllRequiredUploads(assignment) && !hasAllRequiredConfirmedSubmissions(assignment)
}
function studentReadStateLabel(state?: string) {
  const labels: Record<string, string> = {
    unread: '未阅读',
    read: '未提交',
    uploaded: '待确认',
    submitted: '已提交'
  }
  return labels[state || ''] ?? '未提交'
}

function studentReadStateType(state?: string) {
  if (state === 'submitted') {
    return 'success'
  }
  if (state === 'uploaded') {
    return 'warning'
  }
  if (state === 'unread') {
    return 'info'
  }
  return 'warning'
}

function teacherGradingStateLabel(state?: string) {
  const labels: Record<string, string> = {
    needs_grading: '待批改',
    needs_review: '待复核',
    reviewed: '已复核',
    published: '已反馈'
  }
  return labels[state || ''] ?? '待批改'
}

function teacherGradingStateType(state?: string) {
  if (state === 'reviewed') return 'warning'
  if (state === 'published') {
    return 'success'
  }
  if (state === 'needs_review') {
    return 'warning'
  }
  return 'info'
}

function studentGradeStatusLabel(assignment: Assignment) {
  if (assignment.is_expired) return '已过期'
  if (assignment.assignment_grade?.status === 'published') {
    return '已批改'
  }
  if (assignment.assignment_grade?.status === 'reviewed' || assignment.assignment_grade?.status === 'auto_graded') {
    return '批改中'
  }
  return '未批改'
}

function studentGradeStatusType(assignment: Assignment) {
  if (assignment.is_expired) return 'danger'
  if (assignment.assignment_grade?.status === 'published') {
    return 'success'
  }
  if (assignment.assignment_grade?.status === 'reviewed' || assignment.assignment_grade?.status === 'auto_graded') {
    return 'warning'
  }
  return 'info'
}

function gradingStatusLabel(status?: GradingStatus) {
  const labels: Record<GradingStatus, string> = {
    pending: '待批改',
    auto_graded: '自动批改',
    reviewed: '已复核',
    published: '已发布'
  }
  return status ? labels[status] : '待批改'
}

function gradingStatusType(status?: GradingStatus) {
  if (status === 'published' || status === 'reviewed') {
    return 'success'
  }
  if (status === 'auto_graded') {
    return 'warning'
  }
  return 'info'
}

function judgeStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    accepted: '通过',
    wrong_answer: '答案错误',
    runtime_error: '运行错误',
    time_limit_exceeded: '超时',
    skipped: '跳过',
    error: '错误'
  }
  return status ? labels[status] ?? status : '-'
}

function judgeStatusType(status?: string) {
  if (status === 'accepted') {
    return 'success'
  }
  if (status === 'wrong_answer' || status === 'runtime_error' || status === 'time_limit_exceeded' || status === 'error') {
    return 'danger'
  }
  if (status === 'skipped') {
    return 'warning'
  }
  return 'info'
}
function formatDate(value: string | null) {
  return reportDate(value)
}

function isDialogCancel(error: unknown) {
  return error === 'cancel' || error === 'close' || (error instanceof Error && (error.message === 'cancel' || error.message === 'close'))
}

function formatSize(value: number) {
  if (value < 1024) {
    return `${value} B`
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`
  }
  return `${(value / 1024 / 1024).toFixed(2)} MB`
}

function formatOptionalNumber(value?: number | null, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '-'
  }
  return Number(value).toFixed(digits).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1')
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined) {
    return '-'
  }
  return `${Math.round(Number(value) * 100)}%`
}

function formatDays(value?: number | null) {
  if (value === null || value === undefined) {
    return '-'
  }
  return `${formatOptionalNumber(value)} 天`
}

function studentClassAverageScore(courseClass: PublicClass) {
  return courseClass.average_score === null || courseClass.average_score === undefined ? '-' : formatOptionalNumber(courseClass.average_score)
}

function exportAssignmentGradesCsv() {
  if (!selectedAssignmentId.value) {
    return
  }
  window.open(api.assignmentGradesCsvUrl(selectedAssignmentId.value), '_blank')
}

async function openScoreManagerDialog() {
  if (!selectedAssignment.value || !selectedAssignmentId.value) {
    return
  }
  scoreManagerForm.field = selectedAssignment.value.type === 'lab_report' ? selectedAssignment.value.code : 'homework'
  scoreManagerForm.command_type = selectedAssignment.value.type === 'lab_report' ? 'lab' : 'regular'
  scoreManagerForm.group_same_score = scoreManagerForm.command_type === 'regular'
  scoreManagerCommands.value = ''
  scoreManagerDialogVisible.value = true
  await generateScoreManagerCommands()
}

async function generateScoreManagerCommands() {
  if (!selectedAssignmentId.value) {
    return
  }
  submissionLoading.value = true
  try {
    const result = await api.exportScoreManagerCommands(selectedAssignmentId.value, { ...scoreManagerForm })
    scoreManagerCommands.value = result.export.commands
    if (!result.export.exported_count) {
      ElMessage.warning('暂无已复核或已发布的最终成绩可导出')
    }
  } catch (error) {
    scoreManagerCommands.value = ''
    ElMessage.error((error as Error).message)
  } finally {
    submissionLoading.value = false
  }
}

async function copyScoreManagerCommands() {
  if (!scoreManagerCommands.value) {
    ElMessage.warning('暂无可复制命令')
    return
  }
  await navigator.clipboard.writeText(scoreManagerCommands.value)
  ElMessage.success('命令已复制')
}
function currentReviewSubmissions() {
  return reviewingSubmissionRow.value?.submissions ?? (reviewingSubmission.value ? [reviewingSubmission.value] : [])
}

function judgeCases(submission?: Submission | null) {
  const cases = submission?.latest_judge_run?.details.cases
  return Array.isArray(cases) ? cases : []
}

function aiReportModules(grading?: GradingResult | null) {
  const modules = grading?.llm_details.modules
  return Array.isArray(modules) ? (modules as AiReportModule[]) : []
}

function openSubmissionDownload(submission: Submission) {
  window.open(api.submissionDownloadUrl(submission.id), '_blank', 'noopener')
}

function programEvaluationKeys(assignment?: Assignment | null) {
  return new Set((assignment?.program_evaluations ?? []).map((item) => item.input_file_key))
}

function aiEvaluationKeys(assignment?: Assignment | null) {
  return new Set((assignment?.ai_evaluations ?? []).map((item) => item.input_file_key))
}

function manualSubmissionKeys(assignment?: Assignment | null) {
  if (!assignment) {
    return new Set<string>()
  }
  const evaluated = new Set([
    ...programEvaluationKeys(assignment),
    ...aiEvaluationKeys(assignment)
  ])
  return new Set(assignment.submission_requirements.filter((item) => item.required && !evaluated.has(item.key)).map((item) => item.key))
}

function reviewKindForSubmission(submission: Submission) {
  const assignment = selectedAssignment.value
  if (programEvaluationKeys(assignment).has(submission.submission_item_key)) {
    return 'program' as const
  }
  if (aiEvaluationKeys(assignment).has(submission.submission_item_key)) {
    return 'ai' as const
  }
  return 'manual' as const
}
function reviewKindLabel(kind: FileReview['review_kind']) {
  const labels: Record<FileReview['review_kind'], string> = {
    manual: '教师手动批改',
    program: '程序评测后复核',
    ai: 'AI 建议后复核'
  }
  return labels[kind]
}

function reviewItemStateLabel(item: FileReview) {
  if (item.review_status === 'confirmed') {
    return item.review_kind === 'manual' ? '已批改' : '已复核'
  }
  if (item.review_kind === 'manual') {
    return '手动待批改'
  }
  if (item.review_kind === 'program') {
    return '程序评测后待复核'
  }
  return 'AI 建议后待复核'
}
function reviewKindType(kind: FileReview['review_kind']) {
  if (kind === 'manual') {
    return 'danger'
  }
  if (kind === 'program') {
    return 'warning'
  }
  return 'primary'
}

function reviewStatusLabel(item: FileReview) {
  if (item.review_status === 'confirmed') {
    return item.review_kind === 'manual' ? '已确认批改' : '已确认复核'
  }
  return item.review_kind === 'manual' ? '待确认批改' : '待确认复核'
}

function reviewStatusType(item: FileReview) {
  return item.review_status === 'confirmed' ? 'success' : 'info'
}

function reviewConfirmActionLabel(item: FileReview) {
  return item.review_kind === 'manual' ? '确认批改' : '确认复核'
}

function confirmReviewItem(item: FileReview) {
  item.review_status = 'confirmed'
}

function confirmAllReviewItems() {
  reviewFileForms.value.forEach((item) => {
    item.review_status = 'confirmed'
  })
}
function submissionForReviewItem(item: FileReview) {
  return currentReviewSubmissions().find((submission) => submission.id === item.submission_id) ?? null
}

function openSubmissionPreviewForReviewItem(item: FileReview) {
  const submission = submissionForReviewItem(item)
  if (submission) {
    openSubmissionPreview(submission)
  }
}

function openSubmissionDownloadForReviewItem(item: FileReview) {
  const submission = submissionForReviewItem(item)
  if (submission) {
    openSubmissionDownload(submission)
  }
}

async function rerunCurrentReviewGrading() {
  if (!reviewingSubmissionRow.value || !selectedAssignmentId.value) {
    return
  }
  await rerunSubmissionGrading(reviewingSubmissionRow.value)
  const refreshed = [...submissionRows.value, ...testSubmissionRows.value].find((row) => row.roster.id === reviewingSubmissionRow.value?.roster.id)
  if (refreshed?.submission) {
    openGradeReviewDialog(refreshed)
  }
}

function judgeRunForReviewItem(item: FileReview) {
  return submissionForReviewItem(item)?.latest_judge_run ?? null
}

function judgeCasesForReviewItem(item: FileReview) {
  return judgeCases(submissionForReviewItem(item))
}

function judgeRunMessageForReviewItem(item: FileReview) {
  return String(judgeRunForReviewItem(item)?.details.message ?? '')
}

function programModulesForReviewItem(item: FileReview) {
  return (selectedAssignment.value?.program_evaluations ?? []).filter((module) => module.input_file_key === item.submission_item_key)
}

function programModuleNamesForReviewItem(item: FileReview) {
  const names = programModulesForReviewItem(item).map((module) => module.name).filter(Boolean)
  return names.length ? names.join('，') : '程序评测模块'
}
function aiModulesForReviewItem(item: FileReview) {
  const grading = reviewingSubmissionRow.value?.assignment_grade ?? reviewingSubmission.value?.grading_result
  return aiReportModules(grading).filter((module) => module.input_file_key === item.submission_item_key)
}

function configuredEvaluationWeightForKey(key: string) {
  const assignment = selectedAssignment.value
  if (!assignment) {
    return 0
  }
  const programWeight = assignment.program_evaluations
    .filter((item) => item.input_file_key === key)
    .reduce((total, item) => total + programEvaluationScore(item), 0)
  const aiWeight = assignment.ai_evaluations
    .filter((item) => item.input_file_key === key)
    .reduce((total, item) => total + Number(item.score_percent || 0), 0)
  return programWeight + aiWeight
}

function manualWeightPercentForKey(key: string) {
  const assignment = selectedAssignment.value
  if (!assignment || !manualSubmissionKeys(assignment).has(key)) {
    return 0
  }
  const evaluatedWeight = assignment.submission_requirements.reduce((total, item) => total + configuredEvaluationWeightForKey(item.key), 0)
  const manualKeys = Array.from(manualSubmissionKeys(assignment))
  const remaining = Math.max(0, 100 - evaluatedWeight)
  return manualKeys.length ? remaining / manualKeys.length : 0
}

function reviewWeightPercent(item: FileReview) {
  const requirement = selectedAssignment.value?.submission_requirements.find(value => value.key === item.submission_item_key)
  if (!requirement?.required) return 0
  return Number((requirement.weight_percent ?? (configuredEvaluationWeightForKey(item.submission_item_key) || manualWeightPercentForKey(item.submission_item_key))).toFixed(2))
}

function maxScoreForReviewItem(item: FileReview) {
  return Number((((selectedAssignment.value?.max_score ?? 100) * reviewWeightPercent(item)) / 100).toFixed(2))
}

function reviewScoringHint(item: FileReview) {
  return `满分 ${maxScoreForReviewItem(item)}，权重 ${reviewWeightPercent(item)}%`
}

function reviewFilePayloads() {
  return reviewFileForms.value.map((item) => ({
    ...item,
    weight_percent: reviewWeightPercent(item),
    max_score: maxScoreForReviewItem(item)
  }))
}

function existingFileReviews(grading?: GradingResult | null) {
  const reviews = grading?.llm_details.file_reviews
  return Array.isArray(reviews) ? reviews : []
}

function buildReviewFileForms(row: AssignmentSubmissionRow) {
  const existing = existingFileReviews(row.assignment_grade ?? row.submission?.grading_result)
  reviewFileForms.value = row.submissions.map((submission) => {
    const saved = existing.find((item) => item.submission_id === submission.id || item.submission_item_key === submission.submission_item_key)
    const reviewKind = reviewKindForSubmission(submission)
    return {
      submission_id: submission.id,
      submission_item_key: submission.submission_item_key,
      submission_item_label: submission.submission_item_label ?? submission.submission_item_key,
      filename: submission.original_filename,
      review_kind: reviewKind,
      review_status: saved?.review_status ?? ((row.assignment_grade?.status === 'reviewed' || row.assignment_grade?.status === 'published') ? 'confirmed' : 'pending'),
      score: selectedAssignment.value?.submission_requirements.find(item => item.key === submission.submission_item_key)?.required === false ? 0 : Number(saved?.score ?? (reviewKind === 'program' ? submission.latest_judge_run?.score ?? 0 : 0)),
      comment: saved?.comment ?? defaultReviewComment(submission, reviewKind)
    }
  })
}

function defaultReviewComment(submission: Submission, kind: FileReview['review_kind']) {
  if (kind === 'manual') {
    return ''
  }
  if (kind === 'program') {
    if (!submission.latest_judge_run) {
      return '程序评测尚未生成结果，请重测或稍后刷新'
    }
    return `程序评测：${judgeStatusLabel(submission.latest_judge_run.status)}，得分 ${submission.latest_judge_run.score ?? 0}`
  }
  return 'AI 评测建议等待教师复核'
}
function assignmentMarkdown(assignment: Assignment) {
  const courseClass = [...adminClasses.value, ...studentClasses.value].find(item => item.id === assignment.class_id)
  return homeworkMarkdown({
    title: assignment.title, course: courseClass?.course.name ?? '-',
    teacher: courseClass?.course.teacher_name ?? currentUser.value?.username ?? '-',
    publishedAt: assignment.published_at ? reportDate(assignment.published_at) : '未发布',
    deadline: reportDate(assignment.deadline), maxScore: assignment.max_score,
    description: assignment.description
  })
}

function assignmentFormMarkdown() {
  return assignmentMarkdown({
    ...previewAssignment.value, title: assignmentForm.title || '作业标题',
    description: assignmentForm.description, deadline: deadlinePayload(),
    max_score: Number(assignmentForm.max_score)
  })
}

function generatedFeedbackReport() {
  const assignment = selectedAssignment.value
  const row = reviewingSubmissionRow.value
  const courseClass = currentClass.value
  return feedbackMarkdown({
    name: row?.roster.student_name ?? reviewingSubmission.value?.student?.student_name ?? '学生',
    studentNumber: row?.roster.student_number ?? '-', code: assignment?.code ?? '-',
    submittedAt: reportDate(reviewingSubmission.value?.submitted_at ?? null),
    deadline: reportDate(assignment?.deadline ?? null), score: reviewTotalScore.value,
    course: courseClass?.course.name ?? '-', teacher: courseClass?.course.teacher_name ?? '-',
    publishedAt: reportDate(new Date().toISOString()), comment: gradeReviewForm.teacher_comment || '',
    files: reviewFileForms.value.map(item => ({
      label: item.submission_item_label || '文件', filename: item.filename || '-',
      weight: reviewWeightPercent(item), score: Number(item.score || 0),
      maxScore: maxScoreForReviewItem(item), comment: item.comment || '-'
    }))
  })
}
function submissionPreviewMarkdown() {
  if (!previewingSubmission.value || !submissionPreview.value?.content) {
    return ''
  }
  if (previewingSubmission.value.original_filename.toLowerCase().endsWith('.md')) {
    return submissionPreview.value.content
  }
  const language = previewLanguage(previewingSubmission.value.original_filename)
  return `\`\`\`${language}\n${submissionPreview.value.content}\n\`\`\``
}

function previewLanguage(filename: string) {
  const lower = filename.toLowerCase()
  if (lower.endsWith('.py')) {
    return 'python'
  }
  if (lower.endsWith('.c')) {
    return 'c'
  }
  if (lower.endsWith('.cpp') || lower.endsWith('.cc')) {
    return 'cpp'
  }
  return ''
}

async function selectStudentClass(courseClass: PublicClass) {
  if (selectedStudentClassId.value === courseClass.id) {
    selectedStudentClassId.value = undefined
    studentAssignments.value = []
    selectedStudentAssignmentId.value = undefined
    return
  }
  selectedStudentClassId.value = courseClass.id
  selectedStudentAssignmentId.value = undefined
  await loadStudentAssignments(courseClass.id)
}

function applyTheme(value: 'light' | 'dark') {
  theme.value = value
  document.documentElement.dataset.theme = value
  localStorage.setItem('sunjudge-theme', value)
}

function toggleTheme() {
  applyTheme(theme.value === 'light' ? 'dark' : 'light')
}

async function refreshMe() {
  const { user } = await api.me()
  currentUser.value = user
  if (user?.role === 'admin') {
    await loadAdminDashboard()
  }
  if (user?.role === 'teacher') {
    await loadTeacherDashboard()
  }
  if (user?.role === 'student') {
    await loadStudentDashboard()
  }
}

async function submitLogin() {
  if (loading.value) return
  loading.value = true
  try {
    const { user } = await api.login(loginForm.username, loginForm.password)
    currentUser.value = user
    ElMessage.success('登录成功')
    if (user.role === 'admin') {
      await loadAdminDashboard()
    }
    if (user.role === 'teacher') {
      await loadTeacherDashboard()
    }
    if (user.role === 'student') {
      await loadStudentDashboard()
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function submitRegister() {
  if (loading.value) return
  loading.value = true
  try {
    await api.register({
      username: registerRole.value === 'teacher' ? registerForm.username : undefined,
      password: registerForm.password,
      role: registerRole.value,
      student_id: registerForm.student_id,
      student_name: registerForm.student_name
    })
    ElMessage.success(registerRole.value === 'teacher' ? '教师申请已提交，等待管理员审批' : '学生账号已注册')
    authMode.value = 'login'
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function logout() {
  await api.logout()
  currentUser.value = null
  teachers.value = []
  adminClasses.value = []
  studentClasses.value = []
  roster.value = []
  managedAssignments.value = []
  studentAssignments.value = []
  submissionRows.value = []
  testSubmissionRows.value = []
  gradeAnalysis.value = null
  selectedClassId.value = undefined
  selectedStudentClassId.value = undefined
  selectedStudentAssignmentId.value = undefined
  rosterDrawerVisible.value = false
  assignmentsDrawerVisible.value = false
  submissionsDrawerVisible.value = false
  ElMessage.success('已退出登录')
}

async function loadAdminDashboard() {
  await Promise.all([loadTeachers(), loadClasses()])
}

async function loadTeacherDashboard() {
  await loadClasses()
}

async function loadStudentDashboard() {
  classLoading.value = true
  try {
    const { classes } = await api.listMyClasses()
    studentClasses.value = classes
    if (selectedStudentClassId.value && !classes.some((item) => item.id === selectedStudentClassId.value)) {
      selectedStudentClassId.value = undefined
      studentAssignments.value = []
      selectedStudentAssignmentId.value = undefined
    } else if (selectedStudentClassId.value) {
      await loadStudentAssignments(selectedStudentClassId.value)
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    classLoading.value = false
  }
}

async function loadTeachers() {
  teacherLoading.value = true
  try {
    const { teachers: result } = await api.listTeachers('all')
    teachers.value = result
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    teacherLoading.value = false
  }
}

async function reviewTeacher(teacher: User, status: 'approved' | 'rejected') {
  try {
    await api.updateTeacherStatus(teacher.id, status)
    ElMessage.success(status === 'approved' ? '已通过教师申请' : '已拒绝教师申请')
    await loadTeachers()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function loadClasses() {
  classLoading.value = true
  try {
    const { classes } = await api.listAdminClasses()
    adminClasses.value = classes
    if (selectedClassId.value && !classes.some((item) => item.id === selectedClassId.value)) {
      selectedClassId.value = undefined
      roster.value = []
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    classLoading.value = false
  }
}

function openClassDialog() {
  classForm.class_alias = ''
  classForm.course_name = ''
  classForm.course_code = ''
  classForm.semester = ''
  classDialogVisible.value = true
}

async function createTeachingClass() {
  try {
    const result = await api.createClass({
      class: {
        alias: classForm.class_alias
      },
      course: {
        name: classForm.course_name,
        code: classForm.course_code,
        semester: classForm.semester
      },
      roster: []
    })
    ElMessage.success('教学班已创建')
    selectedClassId.value = result.class.id
    importForm.class_id = result.class.id
    classDialogVisible.value = false
    await loadTeacherDashboard()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function openClassMetaDialog(courseClass: AdminClass) {
  editingClassId.value = courseClass.id
  classMetaForm.class_name = courseClass.name
  classMetaForm.course_name = courseClass.course.name
  classMetaForm.course_code = courseClass.course.code
  classMetaForm.semester = courseClass.course.semester
  classMetaDialogVisible.value = true
}

async function updateClassMeta() {
  if (!editingClassId.value) {
    return
  }
  try {
    await api.updateClass(editingClassId.value, {
      class: {
        name: classMetaForm.class_name
      },
      course: {
        name: classMetaForm.course_name,
        code: classMetaForm.course_code,
        semester: classMetaForm.semester
      }
    })
    ElMessage.success('课程信息已更新')
    classMetaDialogVisible.value = false
    await loadTeacherDashboard()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
  input.value = ''
  if (!selectedFile.value || !importForm.class_id) return
  const formData = new FormData()
  formData.append('file', selectedFile.value)
  formData.append('class_id', String(importForm.class_id))
  formData.append('preview', 'true')
  rosterLoading.value = true
  try {
    parsedStudentCount.value = (await api.previewRosterExcel(formData)).student_count
    importDialogVisible.value = true
  } catch (error) { ElMessage.error((error as Error).message) }
  finally { rosterLoading.value = false }
}

function handleSubmissionFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectedSubmissionFile.value = input.files?.[0] ?? null
  input.value = ''
}

function openImportDialog(courseClass: AdminClass) {
  if (rosterLoading.value) return
  selectedClassId.value = courseClass.id
  importForm.class_id = courseClass.id
  selectedFile.value = null
  rosterInput.value?.click()
}

async function importRoster(mode: 'append' | 'replace') {
  if (!selectedFile.value) {
    ElMessage.error('请先选择 Excel 文件')
    return
  }
  if (!importForm.class_id) {
    ElMessage.error('请先选择目标教学班')
    return
  }
  const formData = new FormData()
  formData.append('file', selectedFile.value)
  formData.append('class_id', String(importForm.class_id))
  formData.append('mode', mode)
  rosterLoading.value = true
  try {
    const result = await api.importRosterExcel(formData)
    ElMessage.success(`导入完成：新增 ${result.imported_count} 人，更新 ${result.updated_count} 人，移除 ${result.removed_count} 人，保留已注册 ${result.preserved_registered_count} 人`)
    importDialogVisible.value = false
    await loadTeacherDashboard()
    if (rosterDrawerVisible.value && selectedClassId.value) {
      await loadRoster(selectedClassId.value)
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    rosterLoading.value = false
  }
}

async function openRosterDrawer(courseClass: AdminClass) {
  selectedClassId.value = courseClass.id
  importForm.class_id = courseClass.id
  rosterDrawerVisible.value = true
  await loadRoster(courseClass.id)
}

async function loadRoster(classId: number) {
  rosterLoading.value = true
  selectedRoster.value = []
  try {
    selectedClassId.value = classId
    importForm.class_id = classId
    const result = await api.listRoster(classId)
    roster.value = result.roster
    selectedRoster.value = []
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    rosterLoading.value = false
  }
}

async function batchRoster(action: 'update_class' | 'delete') {
  const classId = selectedClassId.value
  if (!classId || !selectedRoster.value.length || batchRosterLoading.value) return
  const entryIds = selectedRoster.value.map(entry => entry.id)
  try {
    if (action === 'delete') {
      await ElMessageBox.confirm(`删除所选 ${entryIds.length} 名学生的名单项？`, '批量删除', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    }
    batchRosterLoading.value = true
    const result = await api.batchRosterEntries(classId, { entry_ids: entryIds, action, source_class: batchSourceClass.value })
    batchRosterDialogVisible.value = false
    ElMessage.success(`已${action === 'delete' ? '删除' : '更新'} ${result.affected_count} 名学生`)
    await loadRoster(classId)
    await loadTeacherDashboard()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error((error as Error).message)
  } finally {
    batchRosterLoading.value = false
  }
}

function resetRosterForm() {
  rosterForm.student_name = ''
  rosterForm.student_no = ''
  rosterForm.student_number = ''
  rosterForm.source_class = ''
  editingRosterId.value = null
}

function openStudentDialog(entry?: RosterEntry) {
  resetRosterForm()
  if (entry) {
    rosterForm.student_name = entry.student_name
    rosterForm.student_no = entry.student_no ?? entry.student_id.split('-').slice(1).join('-')
    rosterForm.student_number = entry.student_number ?? ''
    rosterForm.source_class = entry.source_class ?? ''
    editingRosterId.value = entry.id
  }
  studentDialogVisible.value = true
}

async function saveRosterEntry() {
  if (!selectedClassId.value) {
    ElMessage.error('请先选择班级')
    return
  }
  try {
    if (editingRosterId.value) {
      await api.updateRosterEntry(editingRosterId.value, { ...rosterForm })
      ElMessage.success('学生信息已更新')
    } else {
      await api.createRosterEntry(selectedClassId.value, { ...rosterForm })
      ElMessage.success('学生已新增')
    }
    studentDialogVisible.value = false
    resetRosterForm()
    await loadRoster(selectedClassId.value)
    await loadTeacherDashboard()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function deleteRosterEntry(entry: RosterEntry) {
  try {
    await api.deleteRosterEntry(entry.id)
    ElMessage.success('名单项已删除')
    if (selectedClassId.value) {
      await loadRoster(selectedClassId.value)
      await loadTeacherDashboard()
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function openAssignmentsDrawer(courseClass: AdminClass) {
  selectedClassId.value = courseClass.id
  assignmentsDrawerVisible.value = true
  await loadManagedAssignments(courseClass.id)
}

async function loadManagedAssignments(classId: number) {
  assignmentLoading.value = true
  try {
    const result = await api.listManagedAssignments(classId)
    managedAssignments.value = result.assignments
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    assignmentLoading.value = false
  }
}

function applyTypeDefaults(type: AssignmentType) {
  assignmentForm.type = type
}

function resetAssignmentForm(type: AssignmentType = 'homework') {
  editingAssignmentId.value = null
  editingAssignmentOriginalStatus.value = null
  assignmentForm.title = ''
  assignmentForm.code = ''
  assignmentForm.type = type
  assignmentForm.description = ''
  assignmentForm.description_format = 'markdown'
  assignmentForm.deadline = ''
  assignmentForm.allow_late = false
  assignmentForm.late_policy = ''
  assignmentForm.max_score = 100
  assignmentForm.allowed_extensions = ['.py', '.md', '.zip', '.jpg', '.png']
  assignmentForm.max_size_mb = 5
  assignmentForm.filename_template = '{student_id}_{assignment_code}{extension}'
  assignmentForm.submission_requirements = [
    {
      key: 'main',
      label: '提交文件',
      allowed_extensions: ['.py', '.md', '.zip', '.jpg', '.png'],
      max_size_mb: 5,
      filename_template: '{student_id}_{assignment_code}{extension}',
      required: true,
      weight_percent: 100
    }
  ]
  assignmentForm.rubric = ''
  assignmentForm.rubric_format = 'markdown'
  assignmentForm.program_evaluations = []
  assignmentForm.ai_evaluations = []
}

async function openAssignmentDialog(courseClass: AdminClass, assignment?: Assignment) {
  selectedClassId.value = courseClass.id
  if (!assignment) {
    resetAssignmentForm()
  } else {
    editingAssignmentId.value = assignment.id
    editingAssignmentOriginalStatus.value = assignment.status
    assignmentForm.title = assignment.title
    assignmentForm.code = assignment.code
    assignmentForm.type = assignment.type
    assignmentForm.description = assignment.description ?? ''
    assignmentForm.description_format = 'markdown'
    assignmentForm.deadline = assignment.deadline ? reportDate(assignment.deadline).replace(' ', 'T') : ''
    assignmentForm.allow_late = assignment.allow_late
    assignmentForm.late_policy = assignment.late_policy ?? ''
    assignmentForm.max_score = assignment.max_score
    assignmentForm.allowed_extensions = assignment.file_rules.allowed_extensions
    assignmentForm.max_size_mb = assignment.file_rules.max_size_mb
    assignmentForm.filename_template = assignment.file_rules.filename_template
    assignmentForm.submission_requirements = (assignment.submission_requirements.length
      ? assignment.submission_requirements
      : [{ key: 'main', label: '提交文件', ...assignment.file_rules, required: true }]
    ).map((item) => ({ ...item, allowed_extensions: [...item.allowed_extensions] }))
    assignmentForm.rubric = String(assignment.rubric.text ?? '')
    assignmentForm.rubric_format = 'markdown'
    assignmentForm.program_evaluations = assignment.program_evaluations.map((item) => normalizeProgramEvaluationForForm(item))
    assignmentForm.ai_evaluations = assignment.ai_evaluations.map((item) => normalizeAiEvaluationForForm(item))
  }
  teacherMarkdownDocument.value = null
  const session = ++teacherEditorSession
  assignmentDialogVisible.value = true
  try {
    const result = await api.openMarkdownDocument({ class_id: courseClass.id, assignment_id: assignment?.id, kind: 'description' })
    if (session !== teacherEditorSession || !assignmentDialogVisible.value) return
    teacherMarkdownDocument.value = result.document
    assignmentForm.description = result.document.content
  } catch (error) { ElMessage.error((error as Error).message) }
}

async function closeTeacherMarkdownEditor(done: () => void) {
  try { await teacherMarkdownEditor.value?.flush(); teacherEditorSession++; done() }
  catch (error) { await confirmCloseUnsavedEditor(error, done) }
}

function openAssignmentPreview(assignment?: Assignment) {
  selectedAssignmentId.value = assignment?.id
  assignmentPreviewDrawerVisible.value = true
}

function assignmentPayload(status: Assignment['status']): AssignmentPayload {
  return {
    markdown_document_id: teacherMarkdownDocument.value?.id,
    title: assignmentForm.title,
    code: assignmentForm.code,
    type: assignmentForm.type,
    description: assignmentForm.description,
    description_format: 'markdown',
    deadline: deadlinePayload(),
    allow_late: assignmentForm.allow_late,
    late_policy: assignmentForm.late_policy,
    max_score: Number(assignmentForm.max_score),
    file_rules: {
      allowed_extensions: assignmentForm.submission_requirements[0]?.allowed_extensions ?? assignmentForm.allowed_extensions,
      max_size_mb: Number(assignmentForm.submission_requirements[0]?.max_size_mb ?? assignmentForm.max_size_mb),
      filename_template: assignmentForm.submission_requirements[0]?.filename_template ?? assignmentForm.filename_template
    },
    submission_requirements: assignmentForm.submission_requirements.map((item) => ({
      ...item,
      max_size_mb: Number(item.max_size_mb)
    })),
    rubric: { text: '' },
    rubric_format: 'markdown',
    program_evaluations: assignmentForm.program_evaluations,
    ai_evaluations: assignmentForm.ai_evaluations,
    status
  }
}

function normalizeProgramEvaluationForForm(item: ProgramEvaluation): ProgramEvaluation {
  const legacy = item as ProgramEvaluation & Partial<ProgramTestCase> & { argv?: string; arguments?: string }
  const cases = item.cases?.length
    ? item.cases
    : [
        {
          name: 'case 1',
          args: legacy.args ?? legacy.argv ?? legacy.arguments ?? '',
          expected_output: legacy.expected_output ?? '',
          score_percent: legacy.score_percent ?? 10,
          timeout_seconds: legacy.timeout_seconds ?? 2,
          is_hidden: legacy.is_hidden ?? false
        }
      ]
  return {
    name: item.name,
    input_file_key: item.input_file_key,
    cases: cases.map((testCase) => ({ ...testCase, args: testCase.args ?? '' }))
  }
}

function programEvaluationScore(evaluation: ProgramEvaluation) {
  return evaluation.cases.reduce((total, testCase) => total + Number(testCase.score_percent || 0), 0)
}

function resetSubmissionRequirementForm() {
  editingRequirementIndex.value = null
  submissionRequirementForm.key = ''
  submissionRequirementForm.label = ''
  submissionRequirementForm.allowed_extensions = ['.md']
  submissionRequirementForm.max_size_mb = 5
  submissionRequirementForm.filename_template = '{student_id}_{assignment_code}{extension}'
  submissionRequirementForm.required = true
  submissionRequirementForm.weight_percent = Math.max(0, 100 - assignmentForm.submission_requirements.reduce((sum, item) => sum + Number(item.weight_percent ?? 0), 0))
}

function rememberFilenameSelection() {
  const input = filenameTemplateInput.value?.input
  if (input) {
    filenameSelection.start = input.selectionStart ?? input.value.length
    filenameSelection.end = input.selectionEnd ?? filenameSelection.start
  }
}

async function insertFilenameField(field: string) {
  rememberFilenameSelection()
  const inserted = insertAtSelection(submissionRequirementForm.filename_template, `{${field}}`, filenameSelection.start, filenameSelection.end)
  submissionRequirementForm.filename_template = inserted.value
  filenameSelection.start = filenameSelection.end = inserted.cursor
  await nextTick()
  const input = filenameTemplateInput.value?.input
  input?.focus()
  input?.setSelectionRange(inserted.cursor, inserted.cursor)
}

async function openSubmissionRequirementDialog(index?: number) {
  resetSubmissionRequirementForm()
  if (index !== undefined) {
    const requirement = assignmentForm.submission_requirements[index]
    editingRequirementIndex.value = index
    Object.assign(submissionRequirementForm, { ...requirement, allowed_extensions: [...requirement.allowed_extensions] })
  } else {
    const next = assignmentForm.submission_requirements.length + 1
    submissionRequirementForm.key = next === 1 ? 'main' : `file${next}`
    submissionRequirementForm.label = next === 1 ? '提交文件' : `提交文件 ${next}`
    submissionRequirementForm.filename_template = next === 1 ? '{student_id}_{assignment_code}{extension}' : `{student_id}_{assignment_code}_file${next}{extension}`
  }
  submissionRequirementDialogVisible.value = true
  filenameSelection.start = filenameSelection.end = submissionRequirementForm.filename_template.length
  filenamePreviewStudent.value = null
  const classId = selectedClassId.value
  if (classId) {
    try {
      const result = await api.listRoster(classId)
      if (selectedClassId.value === classId) filenamePreviewStudent.value = result.roster[0] ?? null
    } catch { /* A synthetic example remains available if the roster cannot be read. */ }
  }
}

function saveSubmissionRequirement() {
  const maxSizeMb = Number(submissionRequirementForm.max_size_mb)
  if (!Number.isFinite(maxSizeMb) || maxSizeMb <= 0 || maxSizeMb > 64) {
    ElMessage.warning('大小上限必须大于 0 且不超过 64 MB')
    return
  }
  const weightPercent = Number(submissionRequirementForm.weight_percent)
  if (submissionRequirementForm.required && (!Number.isFinite(weightPercent) || weightPercent < 0 || weightPercent > 100)) {
    ElMessage.warning('权重必须为 0 到 100 之间的数字')
    return
  }
  const saved = { ...submissionRequirementForm, allowed_extensions: [...submissionRequirementForm.allowed_extensions] }
  if (!saved.required) saved.weight_percent = 0
  if (editingRequirementIndex.value === null) {
    assignmentForm.submission_requirements.push(saved)
  } else {
    const oldKey = assignmentForm.submission_requirements[editingRequirementIndex.value].key
    assignmentForm.submission_requirements.splice(editingRequirementIndex.value, 1, saved)
    assignmentForm.program_evaluations.forEach((item) => {
      if (item.input_file_key === oldKey) {
        item.input_file_key = saved.key
      }
    })
    assignmentForm.ai_evaluations.forEach((item) => {
      if (item.input_file_key === oldKey) {
        item.input_file_key = saved.key
      }
    })
  }
  submissionRequirementDialogVisible.value = false
}

function removeSubmissionRequirement(index: number) {
  if (assignmentForm.submission_requirements.length <= 1) {
    ElMessage.warning('至少保留一个需提交文件')
    return
  }
  const [removed] = assignmentForm.submission_requirements.splice(index, 1)
  const fallback = assignmentForm.submission_requirements[0]?.key ?? 'main'
  assignmentForm.program_evaluations.forEach((item) => {
    if (item.input_file_key === removed.key) {
      item.input_file_key = fallback
    }
  })
  assignmentForm.ai_evaluations.forEach((item) => {
    if (item.input_file_key === removed.key) {
      item.input_file_key = fallback
    }
  })
}

function resetProgramEvaluationForm() {
  editingProgramEvaluationIndex.value = null
  programEvaluationForm.name = ''
  programEvaluationForm.input_file_key = assignmentForm.submission_requirements[0]?.key ?? 'main'
  programEvaluationForm.cases = []
}

function openProgramEvaluationDialog(index?: number) {
  resetProgramEvaluationForm()
  if (index !== undefined) {
    editingProgramEvaluationIndex.value = index
    const evaluation = normalizeProgramEvaluationForForm(assignmentForm.program_evaluations[index])
    programEvaluationForm.name = evaluation.name
    programEvaluationForm.input_file_key = evaluation.input_file_key
    programEvaluationForm.cases = evaluation.cases.map((testCase) => ({ ...testCase }))
  } else {
    programEvaluationForm.name = `程序评测 ${assignmentForm.program_evaluations.length + 1}`
    addProgramTestCase()
  }
  programEvaluationDialogVisible.value = true
}

function saveProgramEvaluation() {
  const saved: ProgramEvaluation = {
    name: programEvaluationForm.name,
    input_file_key: programEvaluationForm.input_file_key,
    cases: programEvaluationForm.cases.map((testCase) => ({ ...testCase }))
  }
  if (!saved.cases.length) {
    ElMessage.warning('至少添加一个测试用例')
    return
  }
  if (editingProgramEvaluationIndex.value === null) {
    assignmentForm.program_evaluations.push(saved)
  } else {
    assignmentForm.program_evaluations.splice(editingProgramEvaluationIndex.value, 1, saved)
  }
  programEvaluationDialogVisible.value = false
}

function addProgramTestCase() {
  const index = programEvaluationForm.cases.length + 1
  programEvaluationForm.cases.push({
    name: `case ${index}`,
    args: '',
    expected_output: '',
    score_percent: 10,
    timeout_seconds: 2,
    is_hidden: false
  })
}

function removeProgramTestCase(index: number) {
  programEvaluationForm.cases.splice(index, 1)
}

function removeProgramEvaluation(index: number) {
  assignmentForm.program_evaluations.splice(index, 1)
}

function resetAiEvaluationForm() {
  editingAiEvaluationIndex.value = null
  aiEvaluationForm.name = ''
  aiEvaluationForm.input_file_key = assignmentForm.submission_requirements[0]?.key ?? 'main'
  aiEvaluationForm.input = ''
  aiEvaluationForm.criteria_items = []
  aiEvaluationForm.score_percent = 10
}

function openAiEvaluationDialog(index?: number) {
  resetAiEvaluationForm()
  if (index !== undefined) {
    editingAiEvaluationIndex.value = index
    const evaluation = normalizeAiEvaluationForForm(assignmentForm.ai_evaluations[index])
    aiEvaluationForm.name = evaluation.name
    aiEvaluationForm.input_file_key = evaluation.input_file_key
    aiEvaluationForm.input = evaluation.input
    aiEvaluationForm.score_percent = evaluation.score_percent
    aiEvaluationForm.criteria_items = evaluation.criteria_items.map((item) => ({ ...item }))
  } else {
    aiEvaluationForm.name = `AI 评测 ${assignmentForm.ai_evaluations.length + 1}`
    addAiCriterionItem()
  }
  aiEvaluationDialogVisible.value = true
}

function saveAiEvaluation() {
  if (!aiEvaluationForm.criteria_items.length) {
    ElMessage.warning('至少添加一个评分项目')
    return
  }
  const saved: AiEvaluation = {
    name: aiEvaluationForm.name,
    input_file_key: aiEvaluationForm.input_file_key,
    input: aiEvaluationForm.input,
    score_percent: Number(aiEvaluationForm.score_percent),
    criteria_items: aiEvaluationForm.criteria_items.map((item) => ({ content: item.content, weight: Number(item.weight) }))
  }
  if (editingAiEvaluationIndex.value === null) {
    assignmentForm.ai_evaluations.push(saved)
  } else {
    assignmentForm.ai_evaluations.splice(editingAiEvaluationIndex.value, 1, saved)
  }
  aiEvaluationDialogVisible.value = false
}

function normalizeAiEvaluationForForm(item: AiEvaluation): AiEvaluation {
  const legacy = item as AiEvaluation & { grading_criteria?: string }
  const criteriaItems = item.criteria_items?.length
    ? item.criteria_items
    : [
        {
          content: legacy.grading_criteria ?? '',
          weight: 100
        }
      ]
  return {
    name: item.name,
    input_file_key: item.input_file_key,
    input: item.input,
    score_percent: item.score_percent,
    criteria_items: criteriaItems.map((criterion) => ({ content: criterion.content, weight: Number(criterion.weight) }))
  }
}

function addAiCriterionItem() {
  aiEvaluationForm.criteria_items.push({
    content: '',
    weight: 10
  })
}

function removeAiCriterionItem(index: number) {
  aiEvaluationForm.criteria_items.splice(index, 1)
}

function removeAiEvaluation(index: number) {
  assignmentForm.ai_evaluations.splice(index, 1)
}

async function saveAssignment(status: Assignment['status']) {
  if (!selectedClassId.value) {
    return
  }
  try {
    if (!teacherMarkdownDocument.value) { ElMessage.error('请等待 Markdown 编辑器加载完成'); return }
    await teacherMarkdownEditor.value?.flush()
    const payload = assignmentPayload(status)
    let resetGrading = false
    if (editingAssignmentId.value && editingAssignmentOriginalStatus.value === 'published') {
      await ElMessageBox.confirm(
        '已发布作业修改后，重新发布会清空该作业下所有已反馈、已保存和自动批改结果，并重新执行程序/AI评测。教师需要重新复核。',
        '确认修改已发布作业',
        { confirmButtonText: '确认重置并保存', cancelButtonText: '取消', type: 'warning' }
      )
      resetGrading = true
    }
    if (editingAssignmentId.value) {
      await api.updateAssignment(editingAssignmentId.value, { ...payload, reset_grading: resetGrading })
    } else {
      await api.createAssignment(selectedClassId.value, payload)
    }
    ElMessage.success(resetGrading ? '作业已更新，批改结果已重置并重新评测' : status === 'published' ? '作业已发布' : '草稿已保存')
    assignmentDialogVisible.value = false
    await loadManagedAssignments(selectedClassId.value)
    await loadTeacherDashboard()
    if (selectedAssignmentId.value) {
      await loadSubmissions(selectedAssignmentId.value)
    }
  } catch (error) {
    if (!isDialogCancel(error)) {
      ElMessage.error((error as Error).message)
    }
  }
}

async function publishAssignment(row: Assignment) {
  try {
    await api.publishAssignment(row.id)
    ElMessage.success('作业已发布，学生现在可见')
    if (selectedClassId.value) {
      await loadManagedAssignments(selectedClassId.value)
    }
    await loadTeacherDashboard()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function deleteAssignment(row: Assignment) {
  try {
    await ElMessageBox.confirm(`确定删除作业「${row.title}」吗？该操作会同时删除相关提交记录和批改结果。`, '删除作业', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await api.deleteAssignment(row.id)
    ElMessage.success('作业已删除')
    if (selectedAssignmentId.value === row.id) {
      selectedAssignmentId.value = undefined
      submissionsDrawerVisible.value = false
    }
    if (assignmentPreviewDrawerVisible.value && previewAssignment.value.id === row.id) {
      assignmentPreviewDrawerVisible.value = false
    }
    if (selectedClassId.value) {
      await loadManagedAssignments(selectedClassId.value)
    }
    await loadTeacherDashboard()
  } catch (error) {
    if (!isDialogCancel(error)) {
      ElMessage.error((error as Error).message)
    }
  }
}

async function openSubmissionsDrawer(row: Assignment) {
  selectedAssignmentId.value = row.id
  submissionRows.value = []
  testSubmissionRows.value = []
  gradeAnalysis.value = null
  scoreManagerForm.field = row.type === 'lab_report' ? row.code : 'homework'
  scoreManagerForm.command_type = row.type === 'lab_report' ? 'lab' : 'regular'
  scoreManagerForm.group_same_score = scoreManagerForm.command_type === 'regular'
  submissionsDrawerVisible.value = true
  await loadSubmissions(row.id)
}

async function loadSubmissions(assignmentId: number) {
  submissionLoading.value = true
  try {
    const result = await api.listAssignmentSubmissions(assignmentId)
    gradeAnalysis.value = result.analysis
    submissionRows.value = result.submissions
    testSubmissionRows.value = result.test_submissions ?? []
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submissionLoading.value = false
  }
}

async function rerunSubmissionGrading(row: AssignmentSubmissionRow) {
  if (!row.submission || !selectedAssignmentId.value) {
    return
  }
  submissionLoading.value = true
  try {
    await api.rerunSubmissionGrading(row.submission.id)
    ElMessage.success('已重新执行自动批改')
    await loadSubmissions(selectedAssignmentId.value)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submissionLoading.value = false
  }
}

async function returnCurrentSubmissionForResubmit() {
  if (!reviewingSubmission.value || !selectedAssignmentId.value) {
    return
  }
  try {
    await ElMessageBox.confirm('退回后将清空该学生本次作业的提交文件、自动评测和教师批改结果，学生需要重新提交。', '退回重交', {
      confirmButtonText: '退回',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await api.returnSubmissionForResubmit(reviewingSubmission.value.id)
    ElMessage.success('已退回学生重新提交')
    gradeReviewDialogVisible.value = false
    reviewingSubmission.value = null
    reviewingSubmissionRow.value = null
    reviewFileForms.value = []
    await loadSubmissions(selectedAssignmentId.value)
    if (selectedClassId.value) {
      await loadManagedAssignments(selectedClassId.value)
    }
  } catch (error) {
    if (!isDialogCancel(error)) {
      ElMessage.error((error as Error).message)
    }
  }
}

function openGradeReviewDialog(row: AssignmentSubmissionRow) {
  if (!row.submission) {
    return
  }
  reviewingSubmission.value = row.submission
  reviewingSubmissionRow.value = row
  const grading = row.assignment_grade ?? row.submission.grading_result
  gradeReviewForm.final_score = grading?.final_score ?? grading?.auto_score ?? 0
  gradeReviewForm.feedback = grading?.feedback ?? ''
  gradeReviewForm.teacher_comment = grading?.teacher_comment ?? ''
  gradeReviewForm.status = grading?.status === 'published' ? 'published' : 'reviewed'
  buildReviewFileForms(row)
  gradeReviewForm.final_score = grading?.final_score ?? reviewTotalScore.value
  gradeReviewDialogVisible.value = true
}

function openStudentFeedbackDialog() {
  if (selectedStudentAssignment.value?.assignment_grade?.status === 'published') {
    studentFeedbackDialogVisible.value = true
  }
}
function openFeedbackPreview() {
  gradeReviewForm.final_score = reviewTotalScore.value
  gradeReviewForm.feedback = generatedFeedbackReport()
  feedbackPreviewDialogVisible.value = true
}

async function saveGradeReview(status: GradingStatus = gradeReviewForm.status) {
  if (!reviewingSubmission.value || !selectedAssignmentId.value) {
    return
  }
  if (!reviewWeightValid.value) {
    ElMessage.error(`文件评分权重合计应为 100%，当前为 ${reviewWeightTotal.value}%`)
    return
  }
  try {
    confirmAllReviewItems()
    gradeReviewForm.final_score = reviewTotalScore.value
    gradeReviewForm.feedback = generatedFeedbackReport()
    await api.reviewSubmissionGrade(reviewingSubmission.value.id, {
      final_score: Number(gradeReviewForm.final_score),
      teacher_comment: gradeReviewForm.teacher_comment,
      status,
      file_reviews: reviewFilePayloads()
    })
    ElMessage.success(status === 'published' ? '反馈已发布给学生' : '批改已保存')
    gradeReviewDialogVisible.value = false
    reviewingSubmissionRow.value = null
    reviewFileForms.value = []
    await loadSubmissions(selectedAssignmentId.value)
    if (selectedClassId.value) {
      await loadManagedAssignments(selectedClassId.value)
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function openSubmissionPreview(submission: Submission) {
  previewingSubmission.value = submission
  submissionPreview.value = null
  submissionPreviewDialogVisible.value = true
  try {
    submissionPreview.value = await api.previewSubmission(submission.id)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function openLLMConfigDialog() {
  try {
    const { config } = await api.getLLMConfig()
    llmConfig.value = config
    llmConfigForm.provider = config?.provider ?? 'deepseek'
    llmConfigForm.base_url = config?.base_url ?? ''
    llmConfigForm.model = config?.model ?? ''
    llmConfigForm.api_key = ''
    llmConfigForm.enabled = config?.enabled ?? true
    llmConfigDialogVisible.value = true
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function saveLLMConfig() {
  try {
    const { config } = await api.saveLLMConfig({
      provider: llmConfigForm.provider,
      base_url: llmConfigForm.base_url,
      model: llmConfigForm.model,
      api_key: llmConfigForm.api_key || undefined,
      enabled: llmConfigForm.enabled
    })
    llmConfig.value = config
    llmConfigDialogVisible.value = false
    ElMessage.success('LLM 配置已保存')
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function loadStudentAssignments(classId: number) {
  assignmentLoading.value = true
  try {
    const result = await api.listStudentAssignments(classId)
    studentAssignments.value = result.assignments
    if (selectedStudentAssignmentId.value && !result.assignments.some((item) => item.id === selectedStudentAssignmentId.value)) {
      selectedStudentAssignmentId.value = undefined
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    assignmentLoading.value = false
  }
}

async function openSubmissionDialog(assignment: Assignment, requirement: SubmissionRequirement, uploadFile = false) {
  submittingAssignment.value = assignment
  submittingRequirement.value = requirement
  selectedSubmissionFile.value = null
  if (requirement.allowed_extensions.includes('.md') && !uploadFile) {
    try {
      const result = await api.openMarkdownDocument({ class_id: assignment.class_id, assignment_id: assignment.id, kind: 'submission', item_key: requirement.key })
      studentMarkdownDocument.value = result.document
      studentMarkdownContent.value = result.document.content
      markdownDialogVisible.value = true
    } catch (error) { ElMessage.error((error as Error).message) }
    return
  }
  submissionDialogVisible.value = true
}

async function confirmCloseUnsavedEditor(error: unknown, done: () => void) {
  try {
    await ElMessageBox.confirm(`${(error as Error).message} 当前内容尚未保存，请先取消关闭并下载 .md 保留内容。仍要关闭吗？`, '草稿未保存', {
      confirmButtonText: '仍然关闭', cancelButtonText: '继续编辑', type: 'warning'
    })
    done()
  } catch { /* Keep the editor open so the content can be downloaded. */ }
}

async function closeStudentMarkdownEditor(done: () => void) {
  try {
    await studentMarkdownEditor.value?.flush()
    if (selectedStudentClassId.value) await loadStudentAssignments(selectedStudentClassId.value)
    done()
  } catch (error) { await confirmCloseUnsavedEditor(error, done) }
}

async function uploadAlternativeFormat() {
  await closeStudentMarkdownEditor(() => {
    markdownDialogVisible.value = false
    submissionDialogVisible.value = true
  })
}

async function selectStudentAssignment(row: Assignment) {
  selectedStudentAssignmentId.value = row.id
  if (!row.read_at) {
    try {
      const result = await api.markAssignmentRead(row.id)
      const index = studentAssignments.value.findIndex((item) => item.id === row.id)
      if (index >= 0) {
        studentAssignments.value.splice(index, 1, result.assignment)
      }
    } catch (error) {
      ElMessage.error((error as Error).message)
    }
  }
}

function studentClassRowClassName({ row }: { row: PublicClass }) {
  return row.id === selectedStudentClassId.value ? 'is-selected-row clickable-row' : 'clickable-row'
}

function studentAssignmentRowClassName({ row }: { row: Assignment }) {
  return row.id === selectedStudentAssignmentId.value ? 'is-selected-row clickable-row' : 'clickable-row'
}

function submissionRowClassName({ row }: { row: AssignmentSubmissionRow }) {
  return row.submission ? 'clickable-row' : ''
}

async function confirmAssignmentSubmission(assignment: Assignment) {
  if (!selectedStudentClassId.value) {
    return
  }
  if (!canConfirmAssignmentSubmission(assignment)) {
    ElMessage.warning('请先上传所有必交文件')
    return
  }
  submissionLoading.value = true
  try {
    const result = await api.confirmAssignmentSubmission(assignment.id)
    ElMessage.success(result.queue_status === 'queued' ? '提交已确认，自动评测已进入队列' : '提交已确认，自动评测已完成')
    await loadStudentAssignments(selectedStudentClassId.value)
    selectedStudentAssignmentId.value = assignment.id
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submissionLoading.value = false
  }
}
async function submitAssignmentFile() {
  if (!submittingAssignment.value || !submittingRequirement.value || !selectedSubmissionFile.value || !selectedStudentClassId.value) {
    ElMessage.error('请先选择要提交的文件')
    return
  }
  const formData = new FormData()
  formData.append('file', selectedSubmissionFile.value)
  formData.append('item_key', submittingRequirement.value.key)
  submissionLoading.value = true
  try {
    await api.submitAssignment(submittingAssignment.value.id, formData)
    ElMessage.success('文件上传成功，请确认提交作业')
    submissionDialogVisible.value = false
    await loadStudentAssignments(selectedStudentClassId.value)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submissionLoading.value = false
  }
}

onMounted(() => {
  const savedTheme = localStorage.getItem('sunjudge-theme')
  applyTheme(savedTheme === 'dark' ? 'dark' : 'light')
  refreshMe()
})
</script>

<template>
  <main class="shell">
    <section class="masthead">
      <div class="brand-mark">SunJudge</div>
      <div class="top-actions">
        <div v-if="currentUser" class="account-chip">
          <el-tag :class="['role-tag', `role-tag--${currentUser.role}`]" effect="plain">
            {{ currentRoleLabel }}
          </el-tag>
          <div class="account-copy">
            <strong>{{ accountDisplayName }}</strong>
          </div>
        </div>
        <el-button v-if="isTeacher" :icon="Files" @click="openLLMConfigDialog">LLM 配置</el-button>
        <el-button :icon="theme === 'light' ? Moon : Sunny" circle title="切换主题" @click="toggleTheme" />
        <el-button v-if="currentUser" :icon="SwitchButton" @click="logout">退出</el-button>
      </div>
    </section>

    <section v-if="!currentUser" class="auth-panel">
      <el-tabs v-model="authMode" stretch>
        <el-tab-pane label="登录" name="login">
          <el-form class="form" label-position="top" @submit.prevent="submitLogin">
            <el-form-item label="登录名">
              <el-input v-model="loginForm.username" autocomplete="username" placeholder="教师昵称 / 学生真实姓名或编号" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="loginForm.password" type="password" autocomplete="current-password" show-password />
            </el-form-item>
            <el-button class="primary-action" type="primary" native-type="submit" :loading="loading">登录</el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="注册 / 申请" name="register">
          <el-form class="form" label-position="top" @submit.prevent="submitRegister">
            <el-form-item label="账号类型">
              <el-segmented
                v-model="registerRole"
                :options="[
                  { label: '学生', value: 'student' },
                  { label: '教师', value: 'teacher' }
                ]"
              />
            </el-form-item>
            <el-form-item v-if="registerRole === 'teacher'" label="昵称">
              <el-input v-model="registerForm.username" autocomplete="username" />
            </el-form-item>
            <template v-if="registerRole === 'student'">
              <el-form-item label="真实姓名">
                <el-input v-model="registerForm.student_name" />
              </el-form-item>
              <el-form-item label="邀请码">
                <el-input v-model="registerForm.student_id" placeholder="OS202601-06" />
              </el-form-item>
            </template>
            <el-form-item label="密码">
              <el-input v-model="registerForm.password" type="password" autocomplete="new-password" show-password />
            </el-form-item>
            <el-button class="primary-action" type="primary" native-type="submit" :icon="CirclePlus" :loading="loading">
              {{ registerRole === 'teacher' ? '提交教师申请' : '注册学生账号' }}
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </section>

    <section v-else-if="isAdmin" class="workspace">
      <section class="dashboard-card">
        <div class="card-header">
          <div>
            <h2>教师账号</h2>
            <p>{{ teachers.length }} 位教师，{{ pendingTeachers.length }} 个待审批申请，{{ adminClasses.length }} 个教学班</p>
          </div>
          <el-button :icon="Refresh" circle title="刷新" :loading="teacherLoading || classLoading" @click="loadAdminDashboard" />
        </div>
        <el-table :data="teachers" v-loading="teacherLoading || classLoading" row-key="id" empty-text="暂无教师账号">
          <el-table-column type="expand" width="48">
            <template #default="{ row }">
              <div class="nested-table">
                <el-table :data="classesForTeacher(row.id)" empty-text="该教师暂无教学班">
                  <el-table-column prop="course.semester" label="学期" min-width="130" />
                  <el-table-column prop="course.name" label="课程" min-width="180" />
                  <el-table-column prop="alias" label="别名" min-width="130" />
                  <el-table-column prop="roster_count" label="学生" width="90" />
                  <el-table-column prop="assignment_count" label="作业" width="90" />
                </el-table>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="username" label="教师" min-width="140" />
          <el-table-column prop="created_at" label="申请时间" min-width="180" />
          <el-table-column label="班级" width="90">
            <template #default="{ row }">
              {{ classesForTeacher(row.id).length }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="teacherStatusTagType(row.teacher_status)" effect="plain">
                {{ teacherStatusLabel(row.teacher_status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button
                :icon="Check"
                type="success"
                circle
                title="通过"
                :disabled="row.teacher_status !== 'pending'"
                @click="reviewTeacher(row, 'approved')"
              />
              <el-button
                :icon="Close"
                type="danger"
                circle
                title="拒绝"
                :disabled="row.teacher_status !== 'pending'"
                @click="reviewTeacher(row, 'rejected')"
              />
            </template>
          </el-table-column>
        </el-table>
      </section>
    </section>

    <section v-else-if="isTeacher" class="workspace">
      <section class="toolbar-band compact-toolbar">
        <div class="toolbar-actions">
          <el-button type="primary" :icon="CirclePlus" @click="openClassDialog">添加班级</el-button>
          <el-button :icon="Files" @click="imageLibraryVisible = true">图片库管理</el-button>
          <el-tag effect="plain">{{ adminClasses.length }} 个班级</el-tag>
          <el-button :icon="Refresh" :loading="classLoading" @click="loadTeacherDashboard">刷新</el-button>
        </div>
      </section>

      <section class="dashboard-card">
        <el-table :data="adminClasses" v-loading="classLoading" row-key="id" empty-text="暂无教学班" row-class-name="clickable-row" @row-click="openAssignmentsDrawer">
          <el-table-column prop="course.semester" label="学期" min-width="130" />
          <el-table-column prop="course.name" label="课程" min-width="180" />
          <el-table-column prop="alias" label="别名" min-width="130" />
          <el-table-column prop="roster_count" label="学生" width="90" />
          <el-table-column prop="assignment_count" label="作业" width="90" />
          <el-table-column label="操作" width="190" fixed="right" class-name="operation-column">
            <template #default="{ row }">
              <div class="row-actions" @click.stop>
                <el-button :icon="View" circle title="学生列表" @click="openRosterDrawer(row)" />
                <el-button :icon="Files" circle title="作业列表" @click="openAssignmentsDrawer(row)" />
                <el-button :icon="DocumentAdd" type="primary" circle title="发布作业" @click="openAssignmentDialog(row)" />
                <el-button :icon="Edit" circle title="编辑课程" @click="openClassMetaDialog(row)" />
              </div>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </section>

    <section v-else class="workspace">
      <section :class="currentStudentClass ? 'student-layout' : 'student-layout single-panel'">
        <section class="dashboard-card">
          <div class="card-header">
            <div>
              <h2>我的班级</h2>
              <p>{{ studentClasses.length }} 个已绑定班级</p>
            </div>
            <div class="toolbar-actions">
              <el-button :icon="Files" @click="imageLibraryVisible = true">图片库管理</el-button>
              <el-button :icon="Refresh" circle title="刷新" :loading="classLoading" @click="loadStudentDashboard" />
            </div>
          </div>
          <el-table
            :data="studentClasses"
            v-loading="classLoading"
            row-key="id"
            empty-text="暂无班级"
            :row-class-name="studentClassRowClassName"
            @row-click="selectStudentClass"
          >
            <el-table-column v-if="!currentStudentClass" prop="course.semester" label="学期" min-width="130" />
            <el-table-column prop="course.name" label="课程" min-width="170" />
            <el-table-column v-if="!currentStudentClass" prop="course.teacher_name" label="教师" min-width="120" />
            <el-table-column prop="alias" label="别名" width="120" />
            <el-table-column v-if="!currentStudentClass" label="已发布" width="90">
              <template #default="{ row }">{{ row.published_assignment_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column v-if="!currentStudentClass" label="已完成" width="90">
              <template #default="{ row }">{{ row.completed_assignment_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column v-if="!currentStudentClass" label="已反馈" width="90">
              <template #default="{ row }">{{ row.published_grade_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column v-if="!currentStudentClass" label="均分" width="90">
              <template #default="{ row }">{{ studentClassAverageScore(row) }}</template>
            </el-table-column>
            <el-table-column v-if="!currentStudentClass" prop="student.student_id" label="编号" min-width="150" />
            <el-table-column label="待提交" width="100">
              <template #default="{ row }">
                <el-tag :type="row.pending_assignment_count ? 'warning' : 'success'" effect="plain">
                  {{ row.pending_assignment_count ?? 0 }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </section>

        <div v-if="currentStudentClass" class="student-assignment-cards">
        <section class="workflow-card student-assignment-overview">
          <div class="card-header">
            <div>
              <h2>{{ currentStudentClass.alias }}</h2>
              <p>{{ currentStudentClass.course.name }}</p>
            </div>
          </div>
          <div class="student-state-grid">
            <div>
              <span>真实姓名</span>
              <strong>{{ currentStudentClass.student?.student_name ?? currentUser.student_name }}</strong>
            </div>
            <div>
              <span>学号</span>
              <strong>{{ currentStudentClass.student?.student_number ?? currentUser.student_number }}</strong>
            </div>
            <div>
              <span>编号</span>
              <strong>{{ currentStudentClass.student?.student_id ?? currentUser.student_id }}</strong>
            </div>
          </div>
          <div class="student-summary-grid">
            <ProgressCard label="待提交" :value="String(currentStudentClass.pending_assignment_count ?? 0)" number-only :accent="(currentStudentClass.pending_assignment_count ?? 0) > 0" />
            <ProgressCard label="完成" :value="`${currentStudentClass.completed_assignment_count ?? 0} / ${currentStudentClass.published_assignment_count ?? 0}`" :completed="currentStudentClass.completed_assignment_count ?? 0" :expired="currentStudentClass.expired_assignment_count ?? 0" :total="currentStudentClass.published_assignment_count ?? 0" :note="`已完成 / 已发布 · 已过期 ${currentStudentClass.expired_assignment_count ?? 0}`" />
            <ProgressCard label="分数" :value="`${studentClassAverageScore(currentStudentClass)} / ${formatOptionalNumber(currentStudentClass.average_max_score)}`" :percentage="progressPercent(currentStudentClass.score_rate, 1)" note="平均分 / 满分 · 含逾期零分" />
            <ProgressCard label="批改进度" :value="`${currentStudentClass.published_grade_count ?? 0} / ${currentStudentClass.completed_assignment_count ?? 0}`" :percentage="progressPercent(currentStudentClass.published_grade_count, currentStudentClass.completed_assignment_count)" note="已批改 / 已提交" />
          </div>
          <el-table
            :data="studentAssignments"
            v-loading="assignmentLoading"
            row-key="id"
            empty-text="暂无已发布作业"
            :row-class-name="studentAssignmentRowClassName"
            @row-click="selectStudentAssignment"
          >
            <el-table-column prop="title" label="作业" min-width="170" />
            <el-table-column label="截止时间" min-width="160">
              <template #default="{ row }">{{ formatDate(row.deadline) }}</template>
            </el-table-column>
            <el-table-column label="提交状态" width="120">
              <template #default="{ row }">
                <el-tag :type="submissionStatusType(row)" effect="plain">{{ submissionStatusLabel(row) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="批改状态" width="120">
              <template #default="{ row }">
                <el-tag :type="studentGradeStatusType(row)" effect="plain">{{ studentGradeStatusLabel(row) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="成绩" width="100">
              <template #default="{ row }">{{ row.display_score != null ? `${row.display_score}/${row.max_score}` : '-' }}</template>
            </el-table-column>
          </el-table>
        </section>
          <template v-if="selectedStudentAssignment">
            <section class="workflow-card student-assignment-description" aria-label="作业说明">
              <div class="assignment-rendered" v-html="renderContent(assignmentMarkdown(selectedStudentAssignment), 'markdown')" />
            </section>
            <section class="workflow-card assignment-submission-panel" aria-labelledby="assignment-submission-title">
              <div class="card-header">
                <div>
                  <h2 id="assignment-submission-title"><el-icon><Upload /></el-icon> 提交作业</h2>
                </div>
                <div v-if="selectedStudentAssignment.assignment_grade?.status === 'published'" class="toolbar-actions">
                  <el-tag type="success" effect="plain">
                    {{ selectedStudentAssignment.assignment_grade.final_score ?? 0 }} / {{ selectedStudentAssignment.max_score }} 分
                  </el-tag>
                  <el-button type="success" :icon="View" @click="openStudentFeedbackDialog">查看批改反馈</el-button>
                </div>
              </div>
              <el-table :data="selectedStudentAssignment.submission_requirements" row-key="key" empty-text="暂无提交项">
                <el-table-column label="提交项" min-width="210">
                  <template #default="{ row }">
                    <strong>{{ row.label }}</strong>
                    <el-tag :type="row.required ? 'danger' : 'info'" :effect="row.required ? 'dark' : 'plain'" class="requirement-badge">{{ row.required ? '必交' : '选交 · 不计分' }}</el-tag>
                    <div class="requirement-extensions">文件后缀：{{ row.allowed_extensions.join(' / ') }}</div>
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="120">
                  <template #default="{ row }">
                    <el-tag :type="requirementStatusType(selectedStudentAssignment, row.key)" effect="plain">
                      {{ requirementStatusLabel(selectedStudentAssignment, row.key) }}
                    </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" min-width="230">
                <template #default="{ row }">
                  <el-button type="primary" :icon="Upload" :disabled="!canSubmitRequirement(selectedStudentAssignment)" @click="openSubmissionDialog(selectedStudentAssignment, row)">
                    {{ row.allowed_extensions.includes('.md') ? '在线编辑' : submissionActionLabel(selectedStudentAssignment, row.key) }}
                  </el-button>
                  <el-button v-if="row.allowed_extensions.includes('.md')" :icon="Upload" :disabled="!canSubmitRequirement(selectedStudentAssignment)" @click="openSubmissionDialog(selectedStudentAssignment, row, true)">上传文件</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div class="assignment-confirm-bar">
              <div>
                <strong>准备完成后，确认提交整份作业</strong>
                <span>保存或上传不代表提交；确认后进入批改和评测。</span>
              </div>
              <el-button type="primary" :icon="Check" :disabled="!canConfirmAssignmentSubmission(selectedStudentAssignment)" :loading="submissionLoading" @click="confirmAssignmentSubmission(selectedStudentAssignment)">
                确认提交作业
              </el-button>
            </div>

          </section>
          </template>
        </div>
      </section>
    </section>

    <el-dialog v-model="studentFeedbackDialogVisible" title="批改反馈" width="min(920px, 94vw)">
      <section v-if="selectedStudentAssignment?.assignment_grade?.status === 'published'" class="published-feedback-panel">
        <div class="card-header">
          <div>
            <h2>{{ selectedStudentAssignment.title }}</h2>
            <p>{{ selectedStudentAssignment.assignment_grade.final_score ?? 0 }} / {{ selectedStudentAssignment.max_score }} 分</p>
          </div>
          <el-tag type="success" effect="plain">已反馈</el-tag>
        </div>
        <div class="assignment-rendered" v-html="renderContent(selectedStudentAssignment.assignment_grade.feedback ?? '', 'markdown')" />
      </section>
      <el-empty v-else description="暂无已发布反馈" />
      <template #footer>
        <el-button @click="studentFeedbackDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="classDialogVisible" title="添加教学班" width="min(620px, 94vw)" class="structured-form-dialog">
      <el-form id="class-create-form" label-position="top" @submit.prevent="createTeachingClass">
        <section class="workflow-card">
          <h2>教学班</h2>
        <el-form-item label="班级别名">
          <el-input v-model="classForm.class_alias" placeholder="OS202601" />
        </el-form-item>
        <el-form-item label="邀请码">
          <el-input :model-value="classForm.class_alias || '填写别名后生成'" disabled />
        </el-form-item>
        </section>
        <section class="workflow-card">
          <h2>课程信息</h2>
        <el-form-item label="课程名称">
          <el-input v-model="classForm.course_name" placeholder="可先留空，导入 Excel 后自动更新" />
        </el-form-item>
        <el-form-item label="课程号">
          <el-input v-model="classForm.course_code" placeholder="可先留空" />
        </el-form-item>
        <el-form-item label="学期">
          <el-input v-model="classForm.semester" placeholder="2025-2026-2" />
        </el-form-item>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="classDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="CirclePlus" native-type="submit" form="class-create-form">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="classMetaDialogVisible" title="编辑课程信息" width="min(620px, 94vw)" class="structured-form-dialog">
      <el-form id="class-meta-form" label-position="top" @submit.prevent="updateClassMeta">
        <section class="workflow-card">
          <h2>教学班</h2>
        <el-form-item label="教学班名称">
          <el-input v-model="classMetaForm.class_name" />
        </el-form-item>
        </section>
        <section class="workflow-card">
          <h2>课程信息</h2>
        <el-form-item label="课程名称">
          <el-input v-model="classMetaForm.course_name" />
        </el-form-item>
        <el-form-item label="课程号">
          <el-input v-model="classMetaForm.course_code" />
        </el-form-item>
        <el-form-item label="学期">
          <el-input v-model="classMetaForm.semester" placeholder="2025-2026-2" />
        </el-form-item>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="classMetaDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="Check" native-type="submit" form="class-meta-form">保存</el-button>
      </template>
    </el-dialog>

    <input ref="rosterInput" type="file" accept=".xlsx,.xlsm" hidden @change="handleFileChange" />
    <el-dialog v-model="importDialogVisible" title="确认导入学生名单" width="min(500px, 94vw)" :close-on-click-modal="!rosterLoading" :show-close="!rosterLoading">
      <p>已解析 {{ parsedStudentCount }} 名学生，导入至 {{ currentClass?.alias }}，需要追加还是覆盖？</p>
      <p class="muted-line">追加：只新增编号，保留已有名单。覆盖：更新未注册名单并移除文件中没有的未注册学生。已绑定账号的学生始终保留；姓名或学号冲突时取消导入。</p>
      <template #footer>
        <el-button :disabled="rosterLoading" @click="importDialogVisible = false">取消</el-button>
        <el-button :loading="rosterLoading" @click="importRoster('replace')">覆盖</el-button>
        <el-button type="primary" :loading="rosterLoading" @click="importRoster('append')">追加</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="rosterDrawerVisible" size="72%" :title="currentClass ? `${currentClass.name} 学生列表` : '学生列表'">
      <div class="drawer-toolbar">
        <div>
          <strong>{{ currentClass?.alias }}</strong>
          <span>{{ selectedClassRosterCount }} 名学生</span>
        </div>
        <div class="toolbar-actions">
          <el-button :icon="Refresh" :loading="rosterLoading" @click="selectedClassId && loadRoster(selectedClassId)">刷新</el-button>
          <el-button :icon="Upload" @click="currentClass && openImportDialog(currentClass)">导入名单</el-button>
          <el-button type="primary" :icon="CirclePlus" @click="openStudentDialog()">新增学生</el-button>
        </div>
      </div>
      <div class="roster-batch-toolbar">
        <span>已选 {{ selectedRoster.length }} 人</span>
        <el-button :disabled="!selectedRoster.length || batchRosterLoading" @click="batchSourceClass = ''; batchRosterDialogVisible = true">批量修改班级</el-button>
        <el-button type="danger" plain :disabled="!selectedRoster.length" :loading="batchRosterLoading" @click="batchRoster('delete')">批量删除</el-button>
        <small>已注册名单受保护</small>
      </div>
      <el-table :data="roster" v-loading="rosterLoading" row-key="id" empty-text="暂无学生名单" @selection-change="(entries: RosterEntry[]) => selectedRoster = entries">
        <el-table-column type="selection" width="48" :selectable="(entry: RosterEntry) => !entry.matched_user_id" />
        <el-table-column prop="student_no" label="No." width="80" />
        <el-table-column prop="student_name" label="真实姓名" min-width="120" />
        <el-table-column prop="student_number" label="学号" min-width="150" />
        <el-table-column prop="source_class" label="学生信息班级" min-width="150" />
        <el-table-column prop="student_id" label="注册编号" min-width="170" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.registration_status === 'registered' ? 'success' : 'info'" effect="plain">
              {{ registrationStatusLabel(row.registration_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button :icon="Edit" circle title="编辑" :disabled="Boolean(row.matched_user_id)" @click="openStudentDialog(row)" />
            <el-button
              :icon="Delete"
              type="danger"
              circle
              title="删除"
              :disabled="Boolean(row.matched_user_id)"
              @click="deleteRosterEntry(row)"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <el-dialog v-model="batchRosterDialogVisible" title="批量修改学生信息班级" width="min(460px, 94vw)" :close-on-click-modal="!batchRosterLoading">
      <el-form id="roster-batch-form" label-position="top" @submit.prevent="batchRoster('update_class')">
        <el-form-item :label="`所选 ${selectedRoster.length} 名学生的新班级`">
          <el-input v-model="batchSourceClass" maxlength="120" placeholder="例如：计算机261" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="batchRosterLoading" @click="batchRosterDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!batchSourceClass.trim() || !selectedRoster.length" :loading="batchRosterLoading" native-type="submit" form="roster-batch-form">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="assignmentsDrawerVisible" size="78%" :title="currentClass ? `${currentClass.alias} 作业管理` : '作业管理'">
      <div class="drawer-toolbar">
        <div>
          <strong>{{ currentClass?.course.name }}</strong>
          <span>{{ managedAssignments.length }} 个作业</span>
        </div>
        <div class="toolbar-actions">
          <el-button :icon="Refresh" :loading="assignmentLoading" @click="selectedClassId && loadManagedAssignments(selectedClassId)">刷新</el-button>
          <el-button type="primary" :icon="DocumentAdd" @click="currentClass && openAssignmentDialog(currentClass)">新建作业</el-button>
        </div>
      </div>
      <el-table :data="managedAssignments" v-loading="assignmentLoading" row-key="id" empty-text="暂无作业" row-class-name="clickable-row" @row-click="openSubmissionsDrawer">
        <el-table-column prop="title" label="作业" min-width="180" />
        <el-table-column prop="code" label="代码" width="100" />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">{{ assignmentTypeLabel(row.type) }}</template>
        </el-table-column>
        <el-table-column label="截止时间" min-width="160">
          <template #default="{ row }">{{ formatDate(row.deadline) }}</template>
        </el-table-column>
        <el-table-column label="状态" min-width="230">
          <template #default="{ row }">
            <div class="status-triplet">
              <el-tag :type="assignmentStatusType(row.status)" effect="plain">{{ assignmentStatusLabel(row.status) }}</el-tag>
              <el-tag type="warning" effect="plain">{{ assignmentSubmissionSummary(row) }}</el-tag>
              <el-tag type="success" effect="plain">{{ assignmentFeedbackSummary(row) }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right" class-name="operation-column">
          <template #default="{ row }">
            <div class="row-actions" @click.stop>
              <el-button :icon="Files" circle title="提交状态" @click="openSubmissionsDrawer(row)" />
              <el-button :icon="View" circle title="预览" @click="openAssignmentPreview(row)" />
              <el-button :icon="Edit" circle title="编辑" @click="currentClass && openAssignmentDialog(currentClass, row)" />
              <el-button :icon="CopyDocument" circle title="迁移到其他班级" @click="openCopyAssignment(row)" />
              <el-button v-if="row.status === 'draft'" type="primary" :icon="Check" circle title="发布" @click="publishAssignment(row)" />
              <el-button type="danger" :icon="Delete" circle title="删除" @click="deleteAssignment(row)" />
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <el-drawer v-model="assignmentPreviewDrawerVisible" size="72%" :title="`${previewAssignment.title} 预览`">
      <section class="assignment-detail-panel preview-panel">
        <div class="card-header">
          <div class="toolbar-actions">
            <el-button
              v-if="previewAssignment.id && previewAssignment.status === 'draft'"
              type="primary"
              :icon="Check"
              @click="publishAssignment(previewAssignment)"
            >
              发布
            </el-button>
            <el-button v-if="previewAssignment.id" type="danger" :icon="Delete" @click="deleteAssignment(previewAssignment)">删除</el-button>
            <el-tag :type="assignmentStatusType(previewAssignment.status)" effect="plain">{{ assignmentStatusLabel(previewAssignment.status) }}</el-tag>
          </div>
        </div>
            <div class="assignment-rendered" v-html="renderContent(assignmentMarkdown(previewAssignment), 'markdown')" />
        <h2>需提交文件</h2>
        <el-table :data="previewAssignment.submission_requirements" row-key="key" empty-text="暂无提交项">
          <el-table-column prop="label" label="提交项" min-width="140" />
          <el-table-column prop="key" label="Key" width="110" />
          <el-table-column label="允许类型" min-width="150">
            <template #default="{ row }">{{ row.allowed_extensions.join(', ') }}</template>
          </el-table-column>
          <el-table-column label="大小" width="90">
            <template #default="{ row }">{{ row.max_size_mb }} MB</template>
          </el-table-column>
          <el-table-column prop="filename_template" label="命名模板" min-width="220" show-overflow-tooltip />
        </el-table>
        <section v-if="previewAssignment.program_evaluations.length" class="evaluation-preview">
          <div class="card-header">
            <div>
              <h2>程序评测</h2>
              <p>{{ previewAssignment.program_evaluations.length }} 个模块</p>
            </div>
          </div>
          <el-table :data="previewAssignment.program_evaluations" row-key="name" empty-text="未添加程序评测，发布后将由教师手动批改或使用其它评测方式">
            <el-table-column prop="name" label="名称" min-width="140" />
            <el-table-column label="输入文件" min-width="120">
              <template #default="{ row }">{{ requirementLabel(previewAssignment, row.input_file_key) }}</template>
            </el-table-column>
            <el-table-column label="测试用例" width="100">
              <template #default="{ row }">{{ row.cases.length }}</template>
            </el-table-column>
            <el-table-column label="占比 %" width="100">
              <template #default="{ row }">{{ programEvaluationScore(row) }}</template>
            </el-table-column>
          </el-table>
        </section>
        <section v-if="previewAssignment.ai_evaluations.length" class="evaluation-preview">
          <div class="card-header">
            <div>
              <h2>AI 评测</h2>
              <p>{{ previewAssignment.ai_evaluations.length }} 个模块</p>
            </div>
          </div>
          <el-table :data="previewAssignment.ai_evaluations" row-key="name" empty-text="未添加 AI 评测，发布后将由教师手动批改或使用其它评测方式">
            <el-table-column prop="name" label="名称" min-width="140" />
            <el-table-column label="输入文件" min-width="120">
              <template #default="{ row }">{{ requirementLabel(previewAssignment, row.input_file_key) }}</template>
            </el-table-column>
            <el-table-column prop="score_percent" label="占比 %" width="100" />
            <el-table-column prop="input" label="指定输入" min-width="200" show-overflow-tooltip />
            <el-table-column label="评分项目" width="100">
              <template #default="{ row }">{{ normalizeAiEvaluationForForm(row).criteria_items.length }}</template>
            </el-table-column>
            <el-table-column label="权重合计" width="100">
              <template #default="{ row }">{{ aiCriteriaWeightTotal(row) }}</template>
            </el-table-column>
          </el-table>
        </section>
      </section>
    </el-drawer>

    <el-drawer v-model="submissionsDrawerVisible" size="70%" :title="selectedAssignment ? `${selectedAssignment.title} 提交状态` : '提交状态'">
      <div class="drawer-toolbar">
        <div>
          <strong>{{ selectedAssignment?.code }}</strong>
          <span>按名单显示提交情况</span>
        </div>
        <div class="toolbar-actions">
          <el-button :icon="Refresh" :loading="submissionLoading" @click="selectedAssignmentId && loadSubmissions(selectedAssignmentId)">刷新</el-button>
          <el-button :icon="Download" @click="exportAssignmentGradesCsv">CSV</el-button>
          <el-button type="primary" :icon="Files" @click="openScoreManagerDialog">ScoreManagerCLI</el-button>
        </div>
      </div>
      <div v-if="gradeAnalysis" class="analysis-grid">
        <ProgressCard label="完成" :value="`${gradeAnalysis.submitted_count} / ( ${gradeAnalysis.pending_submission_count} + ${gradeAnalysis.expired_count} )`" :completed="gradeAnalysis.submitted_count" :expired="gradeAnalysis.expired_count" :total="gradeAnalysis.expected_count" note="已提交 / ( 待提交 + 已过期 )" />
        <ProgressCard label="分数" :value="`${formatOptionalNumber(gradeAnalysis.average_score)} / ${gradeAnalysis.max_score}`" :percentage="progressPercent(gradeAnalysis.average_score, gradeAnalysis.max_score)" note="平均分 / 总分（不含过期未提交）" />
        <ProgressCard label="速度" :value="`${formatOptionalNumber(gradeAnalysis.average_submit_days_after_publish)} / ${formatOptionalNumber(gradeAnalysis.publish_to_deadline_days)} 天`" :percentage="progressPercent(gradeAnalysis.average_submit_days_after_publish, gradeAnalysis.publish_to_deadline_days)" note="平均提交用时 / 发布至截止" />
        <ProgressCard label="批改进度" :value="`${gradeAnalysis.published_count} / ${gradeAnalysis.submitted_count}`" :percentage="progressPercent(gradeAnalysis.published_count, gradeAnalysis.submitted_count)" :note="`已反馈 / 已提交 · 待批改 ${gradeAnalysis.pending_grading_count} · 待发布 ${gradeAnalysis.reviewed_count}`" />
      </div>
      <section v-for="group in [
        { key: 'students', rows: submissionRows, title: '班级学生' },
        { key: 'test', rows: testSubmissionRows, title: '00 测试学生' }
      ].filter(group => group.key === 'students' || group.rows.length)" :key="group.key" class="submission-group">
      <div class="card-header">
        <h3>{{ group.title }}</h3>
        <el-tag v-if="group.key === 'test'" type="info" effect="plain">不计入班级统计和成绩导出</el-tag>
      </div>
      <el-table
        :data="group.rows"
        v-loading="submissionLoading"
        row-key="roster.id"
        empty-text="暂无名单"
        :row-class-name="submissionRowClassName"
        @row-click="openGradeReviewDialog"
      >
        <el-table-column prop="roster.student_no" label="序号" width="80" />
        <el-table-column prop="roster.student_name" label="姓名" min-width="120" />
        <el-table-column label="提交日期" min-width="120">
          <template #default="{ row }">{{ row.is_expired ? '已过期' : row.student_state === 'submitted' && row.submission ? formatDate(row.submission.submitted_at) : '-' }}</template>
        </el-table-column>
        <el-table-column label="总分" width="90" align="center">
          <template #default="{ row }">{{ row.final_score ?? '' }}</template>
        </el-table-column>
        <el-table-column label="状态" min-width="220">
          <template #default="{ row }">
            <div class="status-pair">
              <el-tag :type="studentReadStateType(row.student_state)" effect="plain">学生端：{{ studentReadStateLabel(row.student_state) }}</el-tag>
              <el-tag v-if="row.student_state === 'submitted'" :type="teacherGradingStateType(row.teacher_state)" effect="plain">教师端：{{ teacherGradingStateLabel(row.teacher_state) }}</el-tag>
            </div>
          </template>
        </el-table-column>
      </el-table>
      </section>
    </el-drawer>

        <el-dialog v-model="scoreManagerDialogVisible" title="ScoreManagerCLI 导出" width="min(760px, 94vw)" class="structured-form-dialog">
      <el-form label-position="top" @submit.prevent>
        <section class="workflow-card">
          <h2>导出设置</h2>
        <div class="form-grid wide">
          <el-form-item label="目标字段">
            <el-input v-model="scoreManagerForm.field" placeholder="homework / exp1" @change="generateScoreManagerCommands" />
          </el-form-item>
          <el-form-item label="命令类型">
            <el-select v-model="scoreManagerForm.command_type" @change="generateScoreManagerCommands">
              <el-option label="普通成绩 rd/brd" value="regular" />
              <el-option label="实验成绩 lab rd" value="lab" />
            </el-select>
          </el-form-item>
        </div>
        <el-checkbox v-if="scoreManagerForm.command_type === 'regular'" v-model="scoreManagerForm.group_same_score" @change="generateScoreManagerCommands">
          同分合并为 brd
        </el-checkbox>
        </section>
        <section class="workflow-card">
          <h2>命令预览</h2>
        <el-form-item label="命令文本">
          <el-input v-model="scoreManagerCommands" type="textarea" :rows="12" readonly placeholder="暂无可导出的已复核或已发布成绩" />
        </el-form-item>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="scoreManagerDialogVisible = false">关闭</el-button>
        <el-button :icon="Refresh" :loading="submissionLoading" @click="generateScoreManagerCommands">刷新命令</el-button>
        <el-button type="primary" :icon="Check" @click="copyScoreManagerCommands">复制</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="gradeReviewDialogVisible" title="作业批改" width="min(1120px, 96vw)" class="grade-review-dialog">
      <el-form label-position="top" @submit.prevent>
        <section v-if="reviewingSubmission" class="grade-review-sticky-header">
          <div>
            <span>序号</span>
            <strong>{{ reviewingSubmissionRow?.roster.student_no ?? '-' }}</strong>
          </div>
          <div>
            <span>学生姓名</span>
            <strong>{{ reviewingSubmissionRow?.roster.student_name ?? reviewingSubmission.student?.student_name ?? '-' }}</strong>
          </div>
          <div>
            <span>总分</span>
            <strong>{{ reviewTotalScore }} / {{ selectedAssignment?.max_score ?? 100 }}</strong>
          </div>
          <div>
            <span>作业状态</span>
            <el-tag :type="teacherGradingStateType(reviewingSubmissionRow?.teacher_state)" effect="plain">
              {{ teacherGradingStateLabel(reviewingSubmissionRow?.teacher_state) }}
            </el-tag>
          </div>
        </section>

        <section class="workflow-card review-files-section" aria-labelledby="review-files-title">
          <div class="card-header">
            <div>
              <h2 id="review-files-title">逐文件批改</h2>
              <p>权重合计 {{ reviewWeightTotal }}%，总分自动按文件评分汇总</p>
            </div>
            <el-tag :type="reviewWeightValid ? 'success' : 'danger'" effect="plain">
              {{ reviewWeightValid ? '权重有效' : '权重需为 100%' }}
            </el-tag>
          </div>

          <div v-for="item in reviewFileForms" :key="`${item.submission_id}-${item.submission_item_key}`" class="file-review-item review-work-card">
            <div class="card-header">
              <div>
                <h3>{{ item.submission_item_label }}</h3>
                <p>{{ item.filename }} · {{ reviewScoringHint(item) }}</p>
              </div>
              <div class="toolbar-actions">
                <el-tag :type="item.review_status === 'confirmed' ? 'success' : reviewKindType(item.review_kind)" effect="plain">{{ reviewItemStateLabel(item) }}</el-tag>
                <el-button :icon="View" @click="openSubmissionPreviewForReviewItem(item)">在线预览</el-button>
                <el-button :icon="Download" @click="openSubmissionDownloadForReviewItem(item)">下载</el-button>
                <el-button v-if="item.review_kind !== 'manual'" :icon="Refresh" :loading="submissionLoading" @click="rerunCurrentReviewGrading">重测</el-button>
                <el-button :type="item.review_status === 'confirmed' ? 'success' : 'primary'" :icon="Check" @click="confirmReviewItem(item)">
                  {{ item.review_status === 'confirmed' ? '已确认' : reviewConfirmActionLabel(item) }}
                </el-button>
              </div>
            </div>

            <section class="review-result-section">
              <div class="review-section-title">评测结果</div>
              <template v-if="item.review_kind === 'program'">
                <div class="judge-run-summary">
                  <div>
                    <span>评测模块</span>
                    <strong>{{ programModuleNamesForReviewItem(item) }}</strong>
                  </div>
                  <div>
                    <span>运行状态</span>
                    <el-tag :type="judgeStatusType(judgeRunForReviewItem(item)?.status)" effect="plain">
                      {{ judgeRunForReviewItem(item) ? judgeStatusLabel(judgeRunForReviewItem(item)?.status) : '暂无结果' }}
                    </el-tag>
                  </div>
                  <div>
                    <span>自动得分</span>
                    <strong>{{ judgeRunForReviewItem(item)?.score ?? 0 }}</strong>
                  </div>
                </div>
                <el-alert
                  v-if="judgeRunMessageForReviewItem(item)"
                  :title="judgeRunMessageForReviewItem(item)"
                  type="warning"
                  :closable="false"
                  show-icon
                />
                <el-table v-if="judgeCasesForReviewItem(item).length" :data="judgeCasesForReviewItem(item)" row-key="name" size="small">
                  <el-table-column prop="name" label="用例" min-width="150" />
                  <el-table-column label="状态" width="110">
                    <template #default="{ row }">{{ judgeStatusLabel(row.status) }}</template>
                  </el-table-column>
                  <el-table-column prop="score" label="得分" width="80" />
                  <el-table-column prop="score_percent" label="权重 %" width="90" />
                  <el-table-column label="差异" min-width="220" show-overflow-tooltip>
                    <template #default="{ row }">
                      <span v-if="row.diff">第 {{ row.diff.line ?? '-' }} 行：期望 {{ row.diff.expected || '空' }}，实际 {{ row.diff.actual || '空' }}</span>
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <el-table-column type="expand" width="46">
                    <template #default="{ row }">
                      <div class="judge-case-detail">
                        <div>
                          <span>运行参数</span>
                          <pre>{{ row.args || '' }}</pre>
                        </div>
                        <div>
                          <span>期望输出</span>
                          <pre>{{ row.expected_output || '' }}</pre>
                        </div>
                        <div>
                          <span>学生输出</span>
                          <pre>{{ row.stdout || '' }}</pre>
                        </div>
                        <div>
                          <span>错误输出</span>
                          <pre>{{ row.stderr || '' }}</pre>
                        </div>
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
                <p v-else class="muted-line">该文件已配置程序评测，但当前还没有用例结果。请点击“重测”，或检查 Docker/测试用例配置后刷新。</p>
              </template>
              <div v-else-if="item.review_kind === 'ai'" class="ai-report-list">
                <div v-for="module in aiModulesForReviewItem(item)" :key="`${module.input_file_key}-${module.name}`" class="ai-report-item">
                  <el-table v-if="module.criteria_results?.length" :data="aiResultRows(module, selectedAssignment?.max_score ?? 100)" size="small">
                    <el-table-column prop="content" label="评分项" min-width="180" />
                    <el-table-column label="得分/总分（权重）" min-width="155">
                      <template #default="{ row }">{{ row.score ?? '-' }}/{{ row.max_score ?? '-' }}（{{ row.weight_percent }}%）</template>
                    </el-table-column>
                    <el-table-column label="评分理由" min-width="260">
                      <template #default="{ row }">{{ row.reason ?? row.comment ?? '-' }}</template>
                    </el-table-column>
                  </el-table>
                  <div v-if="module.status === 'completed'" class="ai-result-total">
                    <strong>{{ module.score ?? 0 }} / {{ module.max_score ?? '-' }} 分</strong>
                  </div>
                  <div class="assignment-rendered" v-html="renderContent(module.summary ?? module.message ?? '暂无模型反馈', 'markdown')" />
                </div>
                <p v-if="!aiModulesForReviewItem(item).length" class="muted-line">暂无 AI 评测结果，教师可先人工复核。</p>
              </div>
              <p v-else class="muted-line">该文件未配置程序或 AI 评测，需要教师手动批改。</p>
            </section>

            <div class="form-grid wide">
              <el-form-item :label="`文件评分（${reviewScoringHint(item)}）`">
                <el-input-number v-model="item.score" :min="0" :max="maxScoreForReviewItem(item)" controls-position="right" />
              </el-form-item>
              <el-form-item label="备注">
                <el-input v-model="item.comment" type="textarea" :rows="2" placeholder="这里只写简单备注，详细评价请放在教师总评中" />
              </el-form-item>
            </div>
          </div>
        </section>

        <section class="workflow-card review-overall-panel" aria-labelledby="review-overall-title">
          <div class="card-header">
            <h2 id="review-overall-title">教师总评</h2>
            <el-tag effect="plain">Markdown</el-tag>
          </div>
          <div class="markdown-edit-grid">
            <el-form-item>
              <el-input v-model="gradeReviewForm.teacher_comment" aria-label="教师总评 Markdown" type="textarea" :rows="14" placeholder="填写总评，支持 Markdown、公式和表情" />
            </el-form-item>
            <section class="markdown-live-preview" aria-label="教师总评预览">
              <div class="assignment-rendered" v-html="renderContent(gradeReviewForm.teacher_comment, 'markdown')" />
            </section>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="gradeReviewDialogVisible = false">取消</el-button>
        <el-button type="warning" :icon="Refresh" @click="returnCurrentSubmissionForResubmit">退回重交</el-button>
        <el-button :icon="View" @click="openFeedbackPreview">预览反馈</el-button>
        <el-button :icon="Check" @click="saveGradeReview('reviewed')">保存</el-button>
        <el-button type="primary" :icon="DocumentAdd" @click="saveGradeReview('published')">发布反馈</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="submissionPreviewDialogVisible" :title="previewingSubmission ? `${previewingSubmission.original_filename} 在线预览` : '在线预览'" width="min(960px, 94vw)">
      <div v-if="submissionPreview?.previewable" class="assignment-rendered" v-html="renderContent(submissionPreviewMarkdown(), 'markdown')" />
      <el-empty v-else :description="submissionPreview?.message ?? '正在加载预览'" />
      <template #footer>
        <el-button @click="submissionPreviewDialogVisible = false">关闭</el-button>
        <el-button v-if="previewingSubmission" :icon="Download" @click="openSubmissionDownload(previewingSubmission)">下载文件</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="feedbackPreviewDialogVisible" title="反馈报告预览" width="min(960px, 94vw)">
      <div class="assignment-rendered" v-html="renderContent(generatedFeedbackReport(), 'markdown')" />
      <template #footer>
        <el-button @click="feedbackPreviewDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="llmConfigDialogVisible" title="LLM 配置" width="min(620px, 94vw)" class="structured-form-dialog">
      <el-form id="llm-config-form" label-position="top" @submit.prevent="saveLLMConfig">
        <section class="workflow-card">
          <h2>模型连接</h2>
        <el-form-item label="Provider">
          <el-input v-model="llmConfigForm.provider" />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="llmConfigForm.base_url" placeholder="https://api.deepseek.com/v1" />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="llmConfigForm.model" placeholder="deepseek-chat" />
        </el-form-item>
        </section>
        <section class="workflow-card">
          <h2>访问配置</h2>
        <el-form-item :label="llmConfig?.has_api_key ? 'API Key（留空则沿用已保存值）' : 'API Key'">
          <el-input v-model="llmConfigForm.api_key" type="password" show-password />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="llmConfigForm.enabled" />
        </el-form-item>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="llmConfigDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="Check" native-type="submit" form="llm-config-form">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="submissionRequirementDialogVisible" :title="editingRequirementIndex === null ? '新增提交项' : '编辑提交项'" width="min(720px, 94vw)" class="structured-form-dialog">
      <el-form id="submission-requirement-form" label-position="top" novalidate @submit.prevent="saveSubmissionRequirement">
        <section class="workflow-card">
          <h2>基本信息</h2>
        <div class="form-grid wide">
          <el-form-item label="Key">
            <el-input v-model="submissionRequirementForm.key" placeholder="code / report" />
          </el-form-item>
          <el-form-item label="名称">
            <el-input v-model="submissionRequirementForm.label" placeholder="Python 源代码 / 实验报告" />
          </el-form-item>
        </div>
        </section>
        <section class="workflow-card">
          <h2>文件规则</h2>
        <div class="form-grid wide">
          <el-form-item label="允许扩展名">
            <el-select v-model="submissionRequirementForm.allowed_extensions" multiple>
              <el-option v-for="item in extensionOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="大小上限 MB">
            <el-input-number v-model="submissionRequirementForm.max_size_mb" :min="0.1" :max="64" :step="0.5" controls-position="right" />
          </el-form-item>
        </div>
        <el-form-item class="filename-template-field">
          <template #label>
            <span>命名模板</span>
            <strong class="filename-preview-inline">{{ submissionFilenameExamples.join(' / ') }}</strong>
          </template>
          <el-input ref="filenameTemplateInput" v-model="submissionRequirementForm.filename_template" placeholder="{student_id}_{assignment_code}{extension}" @select="rememberFilenameSelection" @click="rememberFilenameSelection" @keyup="rememberFilenameSelection" @input="rememberFilenameSelection" @blur="rememberFilenameSelection" />
          <div class="filename-fields">
            <el-button v-for="field in [{ value: 'student_id', label: '学生编号' }, { value: 'student_no', label: '短编号' }, { value: 'name', label: '姓名' }, { value: 'assignment_code', label: '作业代码' }, { value: 'course_alias', label: '课程别名' }, { value: 'extension', label: '扩展名' }]" :key="field.value" size="small" @mousedown.prevent @click="insertFilenameField(field.value)">{{ field.label }} {{ '{' + field.value + '}' }}</el-button>
          </div>
        </el-form-item>
        </section>
        <section class="workflow-card">
          <h2>计分设置</h2>
        <div class="form-grid wide">
        <el-form-item label="必交">
          <el-switch v-model="submissionRequirementForm.required" @change="!submissionRequirementForm.required && (submissionRequirementForm.weight_percent = 0)" />
        </el-form-item>
        <el-form-item label="权重 %">
          <el-input-number v-model="submissionRequirementForm.weight_percent" :min="0" :max="100" :precision="2" :disabled="!submissionRequirementForm.required" controls-position="right" />
          <strong class="weight-score-hint">{{ submissionRequirementForm.required ? `（满分 ${Number((assignmentForm.max_score * Number(submissionRequirementForm.weight_percent ?? 0) / 100).toFixed(2))}）` : '（非必交项不计入总分）' }}</strong>
        </el-form-item>
        </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="submissionRequirementDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="Check" native-type="submit" form="submission-requirement-form">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="programEvaluationDialogVisible" :title="editingProgramEvaluationIndex === null ? '新增程序评测' : '编辑程序评测'" width="min(900px, 96vw)" class="structured-form-dialog">
      <el-form id="program-evaluation-form" label-position="top" @submit.prevent="saveProgramEvaluation">
        <section class="workflow-card">
          <h2>评测设置</h2>
        <div class="form-grid wide">
          <el-form-item label="模块名称">
            <el-input v-model="programEvaluationForm.name" />
          </el-form-item>
          <el-form-item label="输入文件">
            <el-select v-model="programEvaluationForm.input_file_key">
              <el-option v-for="item in assignmentForm.submission_requirements" :key="item.key" :label="`${item.label} (${item.key})`" :value="item.key" :disabled="!item.required" />
            </el-select>
          </el-form-item>
        </div>
        </section>
        <section class="workflow-card">
          <div class="drawer-toolbar">
            <div>
              <h2>测试用例</h2>
              <span>{{ programEvaluationForm.cases.length }} 个用例，共 {{ programEvaluationScore(programEvaluationForm) }}%</span>
            </div>
            <el-button :icon="CirclePlus" @click="addProgramTestCase">增加测试用例</el-button>
          </div>
          <div v-for="(testCase, index) in programEvaluationForm.cases" :key="`case-${index}`" class="evaluation-item">
            <div class="form-grid triple">
              <el-form-item label="名称">
                <el-input v-model="testCase.name" />
              </el-form-item>
              <el-form-item label="分数占比 %">
                <el-input-number v-model="testCase.score_percent" :min="1" :max="100" />
              </el-form-item>
              <el-form-item label="超时秒数">
                <el-input-number v-model="testCase.timeout_seconds" :min="1" :max="30" />
              </el-form-item>
            </div>
            <div class="form-grid wide">
              <el-form-item label="运行命令参数">
                <el-input v-model="testCase.args" placeholder='例如：--mode fast 3 "hello world"' />
              </el-form-item>
              <el-form-item label="期望输出">
                <el-input v-model="testCase.expected_output" type="textarea" :rows="3" />
              </el-form-item>
            </div>
            <div class="toolbar-actions">
              <el-checkbox v-model="testCase.is_hidden">隐藏用例</el-checkbox>
              <el-button type="danger" :icon="Delete" @click="removeProgramTestCase(index)">删除</el-button>
            </div>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="programEvaluationDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="Check" native-type="submit" form="program-evaluation-form">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="aiEvaluationDialogVisible" :title="editingAiEvaluationIndex === null ? '新增 AI 评测' : '编辑 AI 评测'" width="min(820px, 96vw)" class="structured-form-dialog">
      <el-form id="ai-evaluation-form" label-position="top" @submit.prevent="saveAiEvaluation">
        <section class="workflow-card">
          <h2>评测设置</h2>
        <div class="form-grid wide">
          <el-form-item label="模块名称">
            <el-input v-model="aiEvaluationForm.name" />
          </el-form-item>
          <el-form-item label="分数占比 %">
            <el-input-number v-model="aiEvaluationForm.score_percent" :min="1" :max="100" />
          </el-form-item>
        </div>
        <el-form-item label="输入文件">
          <el-select v-model="aiEvaluationForm.input_file_key">
            <el-option v-for="item in assignmentForm.submission_requirements" :key="item.key" :label="`${item.label} (${item.key})`" :value="item.key" :disabled="!item.required" />
          </el-select>
        </el-form-item>
        <el-form-item label="指定输入">
          <el-input v-model="aiEvaluationForm.input" type="textarea" :rows="3" />
        </el-form-item>
        </section>
        <section class="workflow-card">
          <div class="drawer-toolbar">
            <div>
              <h2>评分项目</h2>
              <span>{{ aiEvaluationForm.criteria_items.length }} 项，权重合计 {{ aiCriteriaWeightTotal(aiEvaluationForm) }}</span>
            </div>
            <el-button :icon="CirclePlus" @click="addAiCriterionItem">新增评分项目</el-button>
          </div>
          <div v-for="(criterion, index) in aiEvaluationForm.criteria_items" :key="`ai-criterion-${index}`" class="evaluation-item">
            <div class="form-grid wide">
              <el-form-item label="内容标准">
                <el-input v-model="criterion.content" type="textarea" :rows="3" />
              </el-form-item>
              <el-form-item label="权重">
                <el-input-number v-model="criterion.weight" :min="1" :max="100" />
              </el-form-item>
            </div>
            <div class="toolbar-actions">
              <el-button type="danger" :icon="Delete" @click="removeAiCriterionItem(index)">删除</el-button>
            </div>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="aiEvaluationDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="Check" native-type="submit" form="ai-evaluation-form">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="assignmentDialogVisible" :title="editingAssignmentId ? '编辑作业' : '新建作业'" fullscreen class="assignment-editor-dialog assignment-config-dialog" :before-close="closeTeacherMarkdownEditor">
      <el-form label-position="top" @submit.prevent>
        <section class="workflow-card" aria-labelledby="assignment-basics-title">
          <div class="card-header"><h2 id="assignment-basics-title">基本信息</h2></div>
          <div class="form-grid wide">
            <el-form-item label="作业标题">
              <el-input v-model="assignmentForm.title" />
            </el-form-item>
            <el-form-item label="作业代码">
              <el-input v-model="assignmentForm.code" placeholder="hw1 / exp1" />
            </el-form-item>
          </div>
          <div class="form-grid wide">
            <el-form-item label="类型">
              <el-select v-model="assignmentForm.type" @change="applyTypeDefaults">
                <el-option v-for="item in assignmentTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="总分">
              <el-input-number v-model="assignmentForm.max_score" :min="1" :max="1000" controls-position="right" />
            </el-form-item>
          </div>
          <div class="form-grid wide">
            <el-form-item label="截止时间">
              <el-date-picker v-model="assignmentForm.deadline" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" />
            </el-form-item>
            <el-form-item label="允许迟交">
              <el-switch v-model="assignmentForm.allow_late" />
            </el-form-item>
          </div>
          <el-form-item v-if="assignmentForm.allow_late" label="迟交规则">
            <el-input v-model="assignmentForm.late_policy" />
          </el-form-item>
        </section>
        <section class="workflow-card assignment-description-card" aria-labelledby="assignment-description-title">
          <div class="card-header">
            <h2 id="assignment-description-title">作业说明</h2>
            <el-tag effect="plain">Markdown</el-tag>
          </div>
          <MarkdownEditor v-if="teacherMarkdownDocument" :key="teacherMarkdownDocument.id" ref="teacherMarkdownEditor" library-role="teacher"
            v-model="assignmentForm.description" :document-id="teacherMarkdownDocument.id" :initial-revision="teacherMarkdownDocument.revision"
            :preview-source="assignmentFormMarkdown()" :filename="`${assignmentForm.code || 'assignment'}.md`" />
          <el-alert v-else title="正在加载 Markdown 编辑器…" type="info" :closable="false" />
        </section>
        <section class="workflow-card" aria-labelledby="assignment-files-title">
          <div class="card-header">
            <h2 id="assignment-files-title">需提交文件</h2>
            <div class="toolbar-actions">
              <el-tag effect="plain">{{ assignmentForm.submission_requirements.length }} 个提交项</el-tag>
              <el-tag :type="Math.abs(assignmentForm.submission_requirements.reduce((sum, item) => sum + (item.required ? Number(item.weight_percent ?? 0) : 0), 0) - 100) < 0.01 ? 'success' : 'danger'" effect="plain">权重合计 {{ assignmentForm.submission_requirements.reduce((sum, item) => sum + (item.required ? Number(item.weight_percent ?? 0) : 0), 0) }}%</el-tag>
              <el-button :icon="CirclePlus" @click="openSubmissionRequirementDialog()">添加提交项</el-button>
            </div>
          </div>
          <el-table :data="assignmentForm.submission_requirements" row-key="key" empty-text="暂无提交项">
            <el-table-column prop="label" label="名称" min-width="130" />
            <el-table-column prop="key" label="Key" width="110" />
            <el-table-column label="类型" min-width="150">
              <template #default="{ row }">{{ row.allowed_extensions.join(', ') }}</template>
            </el-table-column>
            <el-table-column label="大小" width="90">
              <template #default="{ row }">{{ row.max_size_mb }} MB</template>
            </el-table-column>
            <el-table-column prop="filename_template" label="命名模板" min-width="230" show-overflow-tooltip />
            <el-table-column label="必交" width="80">
              <template #default="{ row }">{{ row.required ? '是' : '否' }}</template>
            </el-table-column>
            <el-table-column label="权重 / 满分" min-width="130">
              <template #default="{ row }">{{ row.required ? `${row.weight_percent ?? 0}% / ${Number((assignmentForm.max_score * Number(row.weight_percent ?? 0) / 100).toFixed(2))}` : '不计分' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="94" class-name="operation-column">
              <template #default="{ $index }">
                <el-button :icon="Edit" circle title="编辑" @click="openSubmissionRequirementDialog($index)" />
                <el-button type="danger" :icon="Delete" circle title="删除" @click="removeSubmissionRequirement($index)" />
              </template>
            </el-table-column>
          </el-table>
        </section>
        <section class="workflow-card" aria-labelledby="assignment-program-title">
          <div class="card-header">
            <h2 id="assignment-program-title">程序评测</h2>
            <div class="toolbar-actions">
              <el-tag effect="plain">{{ assignmentForm.program_evaluations.length }} 个模块</el-tag>
              <el-button :icon="CirclePlus" @click="openProgramEvaluationDialog()">添加程序评测</el-button>
            </div>
          </div>
          <el-table v-if="assignmentForm.program_evaluations.length" :data="assignmentForm.program_evaluations" row-key="name">
            <el-table-column prop="name" label="模块" min-width="150" />
            <el-table-column label="输入文件" min-width="140">
              <template #default="{ row }">{{ requirementLabelForForm(row.input_file_key) }}</template>
            </el-table-column>
            <el-table-column label="测试用例" width="100">
              <template #default="{ row }">{{ row.cases.length }}</template>
            </el-table-column>
            <el-table-column label="分值占比" width="100">
              <template #default="{ row }">{{ programEvaluationScore(row) }}%</template>
            </el-table-column>
            <el-table-column label="操作" width="94" class-name="operation-column">
              <template #default="{ $index }">
                <el-button :icon="Edit" circle title="编辑" @click="openProgramEvaluationDialog($index)" />
                <el-button type="danger" :icon="Delete" circle title="删除" @click="removeProgramEvaluation($index)" />
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else :image-size="56" description="未配置程序评测" />
        </section>
        <section class="workflow-card" aria-labelledby="assignment-ai-title">
          <div class="card-header">
            <h2 id="assignment-ai-title">AI 评测</h2>
            <div class="toolbar-actions">
              <el-tag effect="plain">{{ assignmentForm.ai_evaluations.length }} 个模块</el-tag>
              <el-button :icon="CirclePlus" @click="openAiEvaluationDialog()">添加 AI 评测</el-button>
            </div>
          </div>
          <el-table v-if="assignmentForm.ai_evaluations.length" :data="assignmentForm.ai_evaluations" row-key="name">
            <el-table-column prop="name" label="模块" min-width="150" />
            <el-table-column label="输入文件" min-width="140">
              <template #default="{ row }">{{ requirementLabelForForm(row.input_file_key) }}</template>
            </el-table-column>
            <el-table-column prop="score_percent" label="分值占比 %" width="110" />
            <el-table-column label="评分项目" width="100">
              <template #default="{ row }">{{ normalizeAiEvaluationForForm(row).criteria_items.length }}</template>
            </el-table-column>
            <el-table-column label="权重合计" width="100">
              <template #default="{ row }">{{ aiCriteriaWeightTotal(row) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="94" class-name="operation-column">
              <template #default="{ $index }">
                <el-button :icon="Edit" circle title="编辑" @click="openAiEvaluationDialog($index)" />
                <el-button type="danger" :icon="Delete" circle title="删除" @click="removeAiEvaluation($index)" />
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else :image-size="56" description="未配置 AI 评测" />
        </section>
      </el-form>
      <template #footer>
        <el-button @click="closeTeacherMarkdownEditor(() => assignmentDialogVisible = false)">关闭</el-button>
        <el-button :icon="View" @click="openAssignmentPreview()">预览</el-button>
        <el-button :icon="Check" @click="saveAssignment('draft')">保存草稿</el-button>
        <el-button type="primary" :icon="DocumentAdd" @click="saveAssignment('published')">保存并发布</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="markdownDialogVisible" :title="`在线编辑 ${submittingRequirement?.label ?? 'Markdown 作业'}`" fullscreen class="assignment-editor-dialog student-markdown-dialog" :before-close="closeStudentMarkdownEditor" destroy-on-close>
      <el-alert title="草稿会自动保存。完成编辑后，请回到作业页面点击“确认提交作业”。" type="info" :closable="false" show-icon />
      <MarkdownEditor v-if="studentMarkdownDocument" :key="studentMarkdownDocument.id" ref="studentMarkdownEditor" library-role="student"
        v-model="studentMarkdownContent" :document-id="studentMarkdownDocument.id" :initial-revision="studentMarkdownDocument.revision"
        :filename="(expectedSubmissionName || 'report.md').replace('{extension}', '.md')" />
      <template #footer>
        <el-button v-if="submittingRequirement?.allowed_extensions.some(extension => extension !== '.md')" @click="uploadAlternativeFormat">上传其他格式</el-button>
        <el-button type="primary" @click="closeStudentMarkdownEditor(() => markdownDialogVisible = false)">保存并完成编辑</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="submissionDialogVisible" :title="submittingRequirement ? `提交 ${submittingRequirement.label}` : '提交作业'" width="560px">
      <div v-if="submittingAssignment && submittingRequirement" class="submission-guide">
        <div>
          <span>允许类型</span>
          <strong>{{ submittingRequirement.allowed_extensions.join(', ') }}</strong>
        </div>
        <div>
          <span>大小上限</span>
          <strong>{{ submittingRequirement.max_size_mb }} MB</strong>
        </div>
      </div>
      <el-alert v-if="submittingRequirement?.allowed_extensions.includes('.md')" title="若 Markdown 中有图片，需要在在线编辑器中上传图片；本地图片不会随 .md 文件上传。" type="warning" :closable="false" show-icon />
      <input ref="submissionFileInput" type="file" :accept="submittingRequirement?.allowed_extensions.join(',')" hidden @change="handleSubmissionFileChange" />
      <el-button class="submission-select-button" type="primary" plain :icon="Files" @click="submissionFileInput?.click()">选择文件</el-button>
      <div class="selected-file-label" role="status">{{ selectedSubmissionFile?.name || '尚未选择文件' }}</div>
      <template #footer>
        <el-button @click="submissionDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="Upload" :loading="submissionLoading" @click="submitAssignmentFile">
          {{ submittingAssignment && submittingRequirement && submissionForRequirement(submittingAssignment, submittingRequirement.key) ? '重新上传并校验' : '上传并校验' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="imageLibraryVisible" title="我的图片库" width="min(900px, 94vw)" destroy-on-close>
      <ImageLibrary v-if="imageLibraryVisible && (isTeacher || currentUser?.role === 'student')" :role="isTeacher ? 'teacher' : 'student'" />
    </el-dialog>
    <el-dialog v-model="copyDialogVisible" title="迁移作业设置" width="min(500px, 94vw)" :close-on-click-modal="!copyLoading" :show-close="!copyLoading">
      <p>复制“{{ copyingAssignment?.title }}”的说明、配图、提交规则与评测设置。目标作业保存为草稿，学生提交及成绩不迁移。请检查截止时间与固定写入的班级编号后发布。</p>
      <el-form id="assignment-copy-form" label-position="top" @submit.prevent="copyAssignmentSettings">
        <el-form-item label="目标教学班">
          <el-select v-model="copyClassId" placeholder="选择自己的另一个教学班">
            <el-option v-for="item in adminClasses.filter(item => item.id !== copyingAssignment?.class_id)" :key="item.id" :value="item.id" :label="`${item.alias} · ${item.course.name}`" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标作业代码"><el-input v-model="copyCode" maxlength="40" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="copyLoading" @click="copyDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!copyClassId || !copyCode.trim()" :loading="copyLoading" native-type="submit" form="assignment-copy-form">迁移为草稿</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="studentDialogVisible" :title="editingRosterId ? '编辑学生' : '新增学生'" width="min(620px, 94vw)" class="structured-form-dialog">
      <el-form id="roster-entry-form" label-position="top" @submit.prevent="saveRosterEntry">
        <section class="workflow-card">
          <h2>学生身份</h2>
        <el-form-item label="真实姓名">
          <el-input v-model="rosterForm.student_name" />
        </el-form-item>
          <el-form-item label="学号">
            <el-input v-model="rosterForm.student_number" />
          </el-form-item>
        </section>
        <section class="workflow-card">
          <h2>名单信息</h2>
          <el-form-item label="No.">
            <el-input v-model="rosterForm.student_no" placeholder="06" />
          </el-form-item>
        <el-form-item label="学生信息班级">
          <el-input v-model="rosterForm.source_class" />
        </el-form-item>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="studentDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="editingRosterId ? Check : CirclePlus" native-type="submit" form="roster-entry-form">
          {{ editingRosterId ? '保存' : '新增' }}
        </el-button>
      </template>
    </el-dialog>
  </main>
</template>
