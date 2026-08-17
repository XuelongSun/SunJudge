<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Check,
  CirclePlus,
  Close,
  Delete,
  DocumentAdd,
  Edit,
  Files,
  Moon,
  Refresh,
  Sunny,
  SwitchButton,
  Upload,
  View
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  api,
  type AdminClass,
  type Assignment,
  type AssignmentPayload,
  type AssignmentSubmissionRow,
  type AssignmentType,
  type AiEvaluation,
  type ProgramEvaluation,
  type PublicClass,
  type Role,
  type RosterEntry,
  type TeacherStatus,
  type TextFormat,
  type User
} from './api'

const currentUser = ref<User | null>(null)
const teachers = ref<User[]>([])
const adminClasses = ref<AdminClass[]>([])
const studentClasses = ref<PublicClass[]>([])
const selectedClassId = ref<number | undefined>()
const selectedStudentClassId = ref<number | undefined>()
const roster = ref<RosterEntry[]>([])
const managedAssignments = ref<Assignment[]>([])
const studentAssignments = ref<Assignment[]>([])
const submissionRows = ref<AssignmentSubmissionRow[]>([])
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
const rosterDrawerVisible = ref(false)
const assignmentsDrawerVisible = ref(false)
const assignmentDialogVisible = ref(false)
const assignmentPreviewDrawerVisible = ref(false)
const submissionsDrawerVisible = ref(false)
const submissionDialogVisible = ref(false)
const studentDialogVisible = ref(false)
const classMetaDialogVisible = ref(false)
const editingRosterId = ref<number | null>(null)
const editingClassId = ref<number | null>(null)
const editingAssignmentId = ref<number | null>(null)
const submittingAssignment = ref<Assignment | null>(null)

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
  description_format: 'text' as TextFormat,
  deadline: '',
  allow_late: false,
  late_policy: '',
  max_score: 100,
  allowed_extensions: ['.py', '.md', '.zip', '.jpg', '.png'] as string[],
  max_size_mb: 5,
  filename_template: '{student_id}_{assignment_code}{extension}',
  rubric: '',
  rubric_format: 'text' as TextFormat,
  program_evaluations: [] as ProgramEvaluation[],
  ai_evaluations: [] as AiEvaluation[]
})

const isAdmin = computed(() => currentUser.value?.role === 'admin')
const isTeacher = computed(() => currentUser.value?.role === 'teacher')
const pendingTeachers = computed(() => teachers.value.filter((teacher) => teacher.teacher_status === 'pending'))
const currentClass = computed(() => adminClasses.value.find((item) => item.id === selectedClassId.value))
const currentStudentClass = computed(() => studentClasses.value.find((item) => item.id === selectedStudentClassId.value))
const selectedAssignment = computed(() => managedAssignments.value.find((item) => item.id === selectedAssignmentId.value))
const selectedStudentAssignment = computed(() => studentAssignments.value.find((item) => item.id === selectedStudentAssignmentId.value))
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
    deadline: assignmentForm.deadline || null,
    allow_late: assignmentForm.allow_late,
    late_policy: assignmentForm.late_policy || null,
    max_score: Number(assignmentForm.max_score),
    file_rules: {
      allowed_extensions: assignmentForm.allowed_extensions,
      max_size_mb: Number(assignmentForm.max_size_mb),
      filename_template: assignmentForm.filename_template
    },
    rubric: { text: assignmentForm.rubric },
    rubric_format: assignmentForm.rubric_format,
    program_evaluations: assignmentForm.program_evaluations,
    ai_evaluations: assignmentForm.ai_evaluations,
    status: 'draft',
    created_at: '',
    updated_at: '',
    published_at: null,
    submission: null
  } as Assignment
})
const selectedClassRosterCount = computed(() => currentClass.value?.roster_count ?? roster.value.length)
const accountDisplayName = computed(() => {
  if (!currentUser.value) {
    return ''
  }
  return currentUser.value.role === 'student' ? currentUser.value.student_name ?? '' : currentUser.value.username
})
const expectedSubmissionName = computed(() => {
  if (!submittingAssignment.value || !currentStudentClass.value) {
    return ''
  }
  const fileExt = selectedSubmissionFile.value ? `.${selectedSubmissionFile.value.name.split('.').pop()}` : '{extension}'
  const student = currentStudentClass.value.student
  return submittingAssignment.value.file_rules.filename_template
    .replace('{student_id}', student?.student_id ?? '')
    .replace('{student_no}', student?.student_no ?? '')
    .replace('{assignment_code}', submittingAssignment.value.code)
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

function submissionStatusLabel(assignment: Assignment) {
  if (!assignment.submission) {
    return '未提交'
  }
  return assignment.submission.status === 'late' ? '已迟交' : '已提交'
}

function submissionStatusType(assignment: Assignment) {
  if (!assignment.submission) {
    return 'info'
  }
  return assignment.submission.status === 'late' ? 'warning' : 'success'
}

function formatDate(value: string | null) {
  if (!value) {
    return '未设置'
  }
  return new Date(value).toLocaleString()
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

function renderContent(value: string | null, format: TextFormat) {
  const text = value || ''
  if (format !== 'markdown') {
    return escapeHtml(text).replace(/\n/g, '<br>')
  }
  return text
    .split(/\n{2,}/)
    .map((block) => {
      const trimmed = block.trim()
      if (!trimmed) {
        return ''
      }
      if (trimmed.startsWith('### ')) {
        return `<h3>${inlineMarkdown(trimmed.slice(4))}</h3>`
      }
      if (trimmed.startsWith('## ')) {
        return `<h2>${inlineMarkdown(trimmed.slice(3))}</h2>`
      }
      if (trimmed.startsWith('# ')) {
        return `<h1>${inlineMarkdown(trimmed.slice(2))}</h1>`
      }
      if (trimmed.startsWith('- ')) {
        const items = trimmed
          .split('\n')
          .filter((line) => line.startsWith('- '))
          .map((line) => `<li>${inlineMarkdown(line.slice(2))}</li>`)
          .join('')
        return `<ul>${items}</ul>`
      }
      return `<p>${inlineMarkdown(trimmed).replace(/\n/g, '<br>')}</p>`
    })
    .join('')
}

function inlineMarkdown(value: string) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
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

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
}

function handleSubmissionFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectedSubmissionFile.value = input.files?.[0] ?? null
}

function openImportDialog(courseClass: AdminClass) {
  selectedClassId.value = courseClass.id
  importForm.class_id = courseClass.id
  selectedFile.value = null
  importDialogVisible.value = true
}

async function importRoster() {
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
  rosterLoading.value = true
  try {
    const result = await api.importRosterExcel(formData)
    ElMessage.success(`导入完成：新增 ${result.imported_count} 人，更新 ${result.updated_count} 人`)
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
  try {
    selectedClassId.value = classId
    importForm.class_id = classId
    const result = await api.listRoster(classId)
    roster.value = result.roster
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    rosterLoading.value = false
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
  assignmentForm.title = ''
  assignmentForm.code = ''
  assignmentForm.type = type
  assignmentForm.description = ''
  assignmentForm.description_format = 'text'
  assignmentForm.deadline = ''
  assignmentForm.allow_late = false
  assignmentForm.late_policy = ''
  assignmentForm.max_score = 100
  assignmentForm.allowed_extensions = ['.py', '.md', '.zip', '.jpg', '.png']
  assignmentForm.max_size_mb = 5
  assignmentForm.filename_template = '{student_id}_{assignment_code}{extension}'
  assignmentForm.rubric = ''
  assignmentForm.rubric_format = 'text'
  assignmentForm.program_evaluations = []
  assignmentForm.ai_evaluations = []
}

function openAssignmentDialog(courseClass: AdminClass, assignment?: Assignment) {
  selectedClassId.value = courseClass.id
  if (!assignment) {
    resetAssignmentForm()
  } else {
    editingAssignmentId.value = assignment.id
    assignmentForm.title = assignment.title
    assignmentForm.code = assignment.code
    assignmentForm.type = assignment.type
    assignmentForm.description = assignment.description ?? ''
    assignmentForm.description_format = assignment.description_format
    assignmentForm.deadline = assignment.deadline ? assignment.deadline.slice(0, 19) : ''
    assignmentForm.allow_late = assignment.allow_late
    assignmentForm.late_policy = assignment.late_policy ?? ''
    assignmentForm.max_score = assignment.max_score
    assignmentForm.allowed_extensions = assignment.file_rules.allowed_extensions
    assignmentForm.max_size_mb = assignment.file_rules.max_size_mb
    assignmentForm.filename_template = assignment.file_rules.filename_template
    assignmentForm.rubric = String(assignment.rubric.text ?? '')
    assignmentForm.rubric_format = assignment.rubric_format
    assignmentForm.program_evaluations = assignment.program_evaluations.map((item) => ({ ...item }))
    assignmentForm.ai_evaluations = assignment.ai_evaluations.map((item) => ({ ...item }))
  }
  assignmentDialogVisible.value = true
}

function openAssignmentPreview(assignment?: Assignment) {
  selectedAssignmentId.value = assignment?.id
  assignmentPreviewDrawerVisible.value = true
}

function assignmentPayload(status: Assignment['status']): AssignmentPayload {
  return {
    title: assignmentForm.title,
    code: assignmentForm.code,
    type: assignmentForm.type,
    description: assignmentForm.description,
    description_format: assignmentForm.description_format,
    deadline: assignmentForm.deadline || null,
    allow_late: assignmentForm.allow_late,
    late_policy: assignmentForm.late_policy,
    max_score: Number(assignmentForm.max_score),
    file_rules: {
      allowed_extensions: assignmentForm.allowed_extensions,
      max_size_mb: Number(assignmentForm.max_size_mb),
      filename_template: assignmentForm.filename_template
    },
    rubric: { text: assignmentForm.rubric },
    rubric_format: assignmentForm.rubric_format,
    program_evaluations: assignmentForm.program_evaluations,
    ai_evaluations: assignmentForm.ai_evaluations,
    status
  }
}

function addProgramEvaluation() {
  assignmentForm.program_evaluations.push({
    name: `程序评测 ${assignmentForm.program_evaluations.length + 1}`,
    input: '',
    expected_output: '',
    score_percent: 10,
    timeout_seconds: 2,
    is_hidden: false
  })
}

function removeProgramEvaluation(index: number) {
  assignmentForm.program_evaluations.splice(index, 1)
}

function addAiEvaluation() {
  assignmentForm.ai_evaluations.push({
    name: `AI 评测 ${assignmentForm.ai_evaluations.length + 1}`,
    input: '',
    grading_criteria: '',
    score_percent: 10
  })
}

function removeAiEvaluation(index: number) {
  assignmentForm.ai_evaluations.splice(index, 1)
}

async function saveAssignment(status: Assignment['status']) {
  if (!selectedClassId.value) {
    return
  }
  try {
    if (editingAssignmentId.value) {
      await api.updateAssignment(editingAssignmentId.value, assignmentPayload(status))
    } else {
      await api.createAssignment(selectedClassId.value, assignmentPayload(status))
    }
    ElMessage.success(status === 'published' ? '作业已发布' : '草稿已保存')
    assignmentDialogVisible.value = false
    await loadManagedAssignments(selectedClassId.value)
    await loadTeacherDashboard()
  } catch (error) {
    ElMessage.error((error as Error).message)
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

async function openSubmissionsDrawer(row: Assignment) {
  selectedAssignmentId.value = row.id
  submissionsDrawerVisible.value = true
  await loadSubmissions(row.id)
}

async function loadSubmissions(assignmentId: number) {
  submissionLoading.value = true
  try {
    const result = await api.listAssignmentSubmissions(assignmentId)
    submissionRows.value = result.submissions
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submissionLoading.value = false
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

function openSubmissionDialog(assignment: Assignment) {
  submittingAssignment.value = assignment
  selectedSubmissionFile.value = null
  submissionDialogVisible.value = true
}

function selectStudentAssignment(row: Assignment) {
  selectedStudentAssignmentId.value = row.id
}

function studentClassRowClassName({ row }: { row: PublicClass }) {
  return row.id === selectedStudentClassId.value ? 'is-selected-row clickable-row' : 'clickable-row'
}

function studentAssignmentRowClassName({ row }: { row: Assignment }) {
  return row.id === selectedStudentAssignmentId.value ? 'is-selected-row clickable-row' : 'clickable-row'
}

async function submitAssignmentFile() {
  if (!submittingAssignment.value || !selectedSubmissionFile.value || !selectedStudentClassId.value) {
    ElMessage.error('请先选择要提交的文件')
    return
  }
  const formData = new FormData()
  formData.append('file', selectedSubmissionFile.value)
  submissionLoading.value = true
  try {
    await api.submitAssignment(submittingAssignment.value.id, formData)
    ElMessage.success('提交成功，格式检查已通过')
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
        <el-button :icon="theme === 'light' ? Moon : Sunny" circle title="切换主题" @click="toggleTheme" />
        <el-button v-if="currentUser" :icon="SwitchButton" @click="logout">退出</el-button>
      </div>
    </section>

    <section v-if="!currentUser" class="auth-panel">
      <el-tabs v-model="authMode" stretch>
        <el-tab-pane label="登录" name="login">
          <el-form class="form" label-position="top" @submit.prevent>
            <el-form-item label="登录名">
              <el-input v-model="loginForm.username" autocomplete="username" placeholder="教师昵称 / 学生真实姓名或编号" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="loginForm.password" type="password" autocomplete="current-password" show-password />
            </el-form-item>
            <el-button class="primary-action" type="primary" :loading="loading" @click="submitLogin">登录</el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="注册 / 申请" name="register">
          <el-form class="form" label-position="top" @submit.prevent>
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
            <el-button class="primary-action" type="primary" :icon="CirclePlus" :loading="loading" @click="submitRegister">
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
          <el-tag effect="plain">{{ adminClasses.length }} 个班级</el-tag>
          <el-button :icon="Refresh" :loading="classLoading" @click="loadTeacherDashboard">刷新</el-button>
        </div>
      </section>

      <section class="dashboard-card">
        <el-table :data="adminClasses" v-loading="classLoading" row-key="id" empty-text="暂无教学班">
          <el-table-column prop="course.semester" label="学期" min-width="130" />
          <el-table-column prop="course.name" label="课程" min-width="180" />
          <el-table-column prop="alias" label="别名" min-width="130" />
          <el-table-column prop="roster_count" label="学生" width="90" />
          <el-table-column prop="assignment_count" label="作业" width="90" />
          <el-table-column label="操作" width="520" fixed="right">
            <template #default="{ row }">
              <div class="row-actions">
                <el-button :icon="View" @click="openRosterDrawer(row)">学生列表</el-button>
                <el-button :icon="Files" @click="openAssignmentsDrawer(row)">作业列表</el-button>
                <el-button :icon="DocumentAdd" type="primary" @click="openAssignmentDialog(row)">发布作业</el-button>
                <el-button :icon="Edit" @click="openClassMetaDialog(row)">编辑课程</el-button>
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
            <el-button :icon="Refresh" circle title="刷新" :loading="classLoading" @click="loadStudentDashboard" />
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

        <section v-if="currentStudentClass" class="dashboard-card">
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
          </el-table>
          <section v-if="selectedStudentAssignment" class="assignment-detail-panel">
            <div class="card-header">
              <div>
                <h2>{{ selectedStudentAssignment.title }}</h2>
                <p>{{ formatDate(selectedStudentAssignment.deadline) }} · {{ selectedStudentAssignment.max_score }} 分</p>
              </div>
              <el-button type="primary" :icon="Upload" @click="openSubmissionDialog(selectedStudentAssignment)">提交作业</el-button>
            </div>
            <div class="assignment-rendered" v-html="renderContent(selectedStudentAssignment.description, selectedStudentAssignment.description_format)" />
            <div class="assignment-rules">
              <div>
                <span>允许文件</span>
                <strong>{{ selectedStudentAssignment.file_rules.allowed_extensions.join(', ') }}</strong>
              </div>
              <div>
                <span>大小上限</span>
                <strong>{{ selectedStudentAssignment.file_rules.max_size_mb }} MB</strong>
              </div>
              <div>
                <span>命名模板</span>
                <strong>{{ selectedStudentAssignment.file_rules.filename_template }}</strong>
              </div>
            </div>
            <h2>评分标准</h2>
            <div class="assignment-rendered" v-html="renderContent(String(selectedStudentAssignment.rubric.text ?? ''), selectedStudentAssignment.rubric_format)" />
          </section>
        </section>
      </section>
    </section>

    <el-dialog v-model="classDialogVisible" title="添加教学班" width="420px">
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="班级别名">
          <el-input v-model="classForm.class_alias" placeholder="OS202601" />
        </el-form-item>
        <el-form-item label="课程名称">
          <el-input v-model="classForm.course_name" placeholder="可先留空，导入 Excel 后自动更新" />
        </el-form-item>
        <el-form-item label="课程号">
          <el-input v-model="classForm.course_code" placeholder="可先留空" />
        </el-form-item>
        <el-form-item label="学期">
          <el-input v-model="classForm.semester" placeholder="2025-2026-2" />
        </el-form-item>
        <el-form-item label="邀请码">
          <el-input :model-value="classForm.class_alias || '填写别名后生成'" disabled />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="classDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="CirclePlus" @click="createTeachingClass">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="classMetaDialogVisible" title="编辑课程信息" width="460px">
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="教学班名称">
          <el-input v-model="classMetaForm.class_name" />
        </el-form-item>
        <el-form-item label="课程名称">
          <el-input v-model="classMetaForm.course_name" />
        </el-form-item>
        <el-form-item label="课程号">
          <el-input v-model="classMetaForm.course_code" />
        </el-form-item>
        <el-form-item label="学期">
          <el-input v-model="classMetaForm.semester" placeholder="2025-2026-2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="classMetaDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="Check" @click="updateClassMeta">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importDialogVisible" title="导入学生名单" width="460px">
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="目标教学班">
          <el-input :model-value="currentClass ? `${currentClass.name} (${currentClass.alias})` : ''" disabled />
        </el-form-item>
        <el-form-item label="Excel 名单">
          <input class="file-input" type="file" accept=".xlsx,.xlsm" @change="handleFileChange" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="Upload" :loading="rosterLoading" @click="importRoster">导入</el-button>
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
      <el-table :data="roster" v-loading="rosterLoading" row-key="id" empty-text="暂无学生名单">
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
      <el-table :data="managedAssignments" v-loading="assignmentLoading" row-key="id" empty-text="暂无作业">
        <el-table-column prop="title" label="作业" min-width="180" />
        <el-table-column prop="code" label="代码" width="100" />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">{{ assignmentTypeLabel(row.type) }}</template>
        </el-table-column>
        <el-table-column label="规则" min-width="220">
          <template #default="{ row }">{{ row.file_rules.allowed_extensions.join(', ') }} / {{ row.file_rules.filename_template }}</template>
        </el-table-column>
        <el-table-column label="截止时间" min-width="160">
          <template #default="{ row }">{{ formatDate(row.deadline) }}</template>
        </el-table-column>
        <el-table-column label="提交" width="90">
          <template #default="{ row }">{{ row.submission_count ?? 0 }}/{{ currentClass?.roster_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="assignmentStatusType(row.status)" effect="plain">{{ assignmentStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button :icon="View" @click="openSubmissionsDrawer(row)">提交状态</el-button>
              <el-button :icon="View" @click="openAssignmentPreview(row)">预览</el-button>
              <el-button :icon="Edit" @click="currentClass && openAssignmentDialog(currentClass, row)">编辑</el-button>
              <el-button v-if="row.status === 'draft'" type="primary" :icon="Check" @click="publishAssignment(row)">发布</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <el-drawer v-model="assignmentPreviewDrawerVisible" size="72%" :title="`${previewAssignment.title} 预览`">
      <section class="assignment-detail-panel preview-panel">
        <div class="card-header">
          <div>
            <h2>{{ previewAssignment.title }}</h2>
            <p>{{ assignmentTypeLabel(previewAssignment.type) }} · {{ formatDate(previewAssignment.deadline) }} · {{ previewAssignment.max_score }} 分</p>
          </div>
          <el-tag :type="assignmentStatusType(previewAssignment.status)" effect="plain">{{ assignmentStatusLabel(previewAssignment.status) }}</el-tag>
        </div>
        <div class="assignment-rendered" v-html="renderContent(previewAssignment.description, previewAssignment.description_format)" />
        <div class="assignment-rules">
          <div>
            <span>允许文件</span>
            <strong>{{ previewAssignment.file_rules.allowed_extensions.join(', ') || '-' }}</strong>
          </div>
          <div>
            <span>大小上限</span>
            <strong>{{ previewAssignment.file_rules.max_size_mb }} MB</strong>
          </div>
          <div>
            <span>命名模板</span>
            <strong>{{ previewAssignment.file_rules.filename_template }}</strong>
          </div>
        </div>
        <h2>评分标准</h2>
        <div class="assignment-rendered" v-html="renderContent(String(previewAssignment.rubric.text ?? ''), previewAssignment.rubric_format)" />
        <section class="evaluation-preview">
          <div class="card-header">
            <div>
              <h2>程序评测</h2>
              <p>{{ previewAssignment.program_evaluations.length }} 个模块</p>
            </div>
          </div>
          <el-table :data="previewAssignment.program_evaluations" row-key="name" empty-text="未添加程序评测，发布后将由教师手动批改或使用其它评测方式">
            <el-table-column prop="name" label="名称" min-width="140" />
            <el-table-column prop="score_percent" label="占比 %" width="100" />
            <el-table-column prop="timeout_seconds" label="超时" width="90" />
            <el-table-column label="隐藏" width="80">
              <template #default="{ row }">{{ row.is_hidden ? '是' : '否' }}</template>
            </el-table-column>
            <el-table-column prop="input" label="输入" min-width="180" show-overflow-tooltip />
            <el-table-column prop="expected_output" label="期望输出" min-width="180" show-overflow-tooltip />
          </el-table>
        </section>
        <section class="evaluation-preview">
          <div class="card-header">
            <div>
              <h2>AI 评测</h2>
              <p>{{ previewAssignment.ai_evaluations.length }} 个模块</p>
            </div>
          </div>
          <el-table :data="previewAssignment.ai_evaluations" row-key="name" empty-text="未添加 AI 评测，发布后将由教师手动批改或使用其它评测方式">
            <el-table-column prop="name" label="名称" min-width="140" />
            <el-table-column prop="score_percent" label="占比 %" width="100" />
            <el-table-column prop="input" label="指定输入" min-width="200" show-overflow-tooltip />
            <el-table-column prop="grading_criteria" label="评分标准" min-width="240" show-overflow-tooltip />
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
        <el-button :icon="Refresh" :loading="submissionLoading" @click="selectedAssignmentId && loadSubmissions(selectedAssignmentId)">刷新</el-button>
      </div>
      <el-table :data="submissionRows" v-loading="submissionLoading" row-key="roster.id" empty-text="暂无名单">
        <el-table-column prop="roster.student_no" label="No." width="80" />
        <el-table-column prop="roster.student_name" label="姓名" min-width="120" />
        <el-table-column prop="roster.student_id" label="编号" min-width="150" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.state === 'submitted' ? 'success' : 'info'" effect="plain">{{ row.state === 'submitted' ? '已提交' : '未提交' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文件" min-width="180">
          <template #default="{ row }">{{ row.submission?.original_filename ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="时间" min-width="170">
          <template #default="{ row }">{{ row.submission ? formatDate(row.submission.submitted_at) : '-' }}</template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ row.submission ? formatSize(row.submission.file_size) : '-' }}</template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <el-dialog v-model="assignmentDialogVisible" :title="editingAssignmentId ? '编辑作业' : '新建作业'" width="720px">
      <el-form label-position="top" @submit.prevent>
        <div class="form-grid wide">
          <el-form-item label="作业标题">
            <el-input v-model="assignmentForm.title" />
          </el-form-item>
          <el-form-item label="作业代码">
            <el-input v-model="assignmentForm.code" placeholder="hw1 / exp1" />
          </el-form-item>
        </div>
        <div class="form-grid triple">
          <el-form-item label="类型">
            <el-select v-model="assignmentForm.type" @change="applyTypeDefaults">
              <el-option v-for="item in assignmentTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="总分">
            <el-input-number v-model="assignmentForm.max_score" :min="1" :max="1000" controls-position="right" />
          </el-form-item>
          <el-form-item label="大小上限 MB">
            <el-input-number v-model="assignmentForm.max_size_mb" :min="0.1" :max="64" :step="0.5" controls-position="right" />
          </el-form-item>
        </div>
        <el-form-item label="说明编辑方式">
          <el-segmented
            v-model="assignmentForm.description_format"
            :options="[
              { label: 'TXT', value: 'text' },
              { label: 'Markdown', value: 'markdown' }
            ]"
          />
        </el-form-item>
        <el-form-item label="作业说明">
          <el-input v-model="assignmentForm.description" type="textarea" :rows="4" />
        </el-form-item>
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
        <div class="form-grid wide">
          <el-form-item label="允许扩展名">
            <el-select v-model="assignmentForm.allowed_extensions" multiple>
              <el-option v-for="item in extensionOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="命名模板">
            <el-input v-model="assignmentForm.filename_template" placeholder="{student_id}_{assignment_code}{extension}" />
          </el-form-item>
        </div>
        <el-form-item label="评分标准编辑方式">
          <el-segmented
            v-model="assignmentForm.rubric_format"
            :options="[
              { label: 'TXT', value: 'text' },
              { label: 'Markdown', value: 'markdown' }
            ]"
          />
        </el-form-item>
        <el-form-item label="评分标准">
          <el-input v-model="assignmentForm.rubric" type="textarea" :rows="4" />
        </el-form-item>
        <section class="evaluation-editor">
          <div class="drawer-toolbar">
            <div>
              <strong>程序评测</strong>
              <span>{{ assignmentForm.program_evaluations.length }} 个模块</span>
            </div>
            <el-button :icon="CirclePlus" @click="addProgramEvaluation">添加程序评测</el-button>
          </div>
          <div v-for="(evaluation, index) in assignmentForm.program_evaluations" :key="`program-${index}`" class="evaluation-item">
            <div class="form-grid triple">
              <el-form-item label="名称"><el-input v-model="evaluation.name" /></el-form-item>
              <el-form-item label="成绩占比 %"><el-input-number v-model="evaluation.score_percent" :min="1" :max="100" /></el-form-item>
              <el-form-item label="超时秒数"><el-input-number v-model="evaluation.timeout_seconds" :min="1" :max="30" /></el-form-item>
            </div>
            <div class="form-grid wide">
              <el-form-item label="输入"><el-input v-model="evaluation.input" type="textarea" :rows="3" /></el-form-item>
              <el-form-item label="期望输出"><el-input v-model="evaluation.expected_output" type="textarea" :rows="3" /></el-form-item>
            </div>
            <div class="toolbar-actions">
              <el-checkbox v-model="evaluation.is_hidden">隐藏用例</el-checkbox>
              <el-button type="danger" :icon="Delete" @click="removeProgramEvaluation(index)">删除</el-button>
            </div>
          </div>
        </section>
        <section class="evaluation-editor">
          <div class="drawer-toolbar">
            <div>
              <strong>AI 评测</strong>
              <span>{{ assignmentForm.ai_evaluations.length }} 个模块</span>
            </div>
            <el-button :icon="CirclePlus" @click="addAiEvaluation">添加 AI 评测</el-button>
          </div>
          <div v-for="(evaluation, index) in assignmentForm.ai_evaluations" :key="`ai-${index}`" class="evaluation-item">
            <div class="form-grid wide">
              <el-form-item label="名称"><el-input v-model="evaluation.name" /></el-form-item>
              <el-form-item label="成绩占比 %"><el-input-number v-model="evaluation.score_percent" :min="1" :max="100" /></el-form-item>
            </div>
            <el-form-item label="指定输入"><el-input v-model="evaluation.input" type="textarea" :rows="3" /></el-form-item>
            <el-form-item label="评分标准"><el-input v-model="evaluation.grading_criteria" type="textarea" :rows="3" /></el-form-item>
            <el-button type="danger" :icon="Delete" @click="removeAiEvaluation(index)">删除</el-button>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="assignmentDialogVisible = false">取消</el-button>
        <el-button :icon="View" @click="openAssignmentPreview()">预览</el-button>
        <el-button :icon="Check" @click="saveAssignment('draft')">保存草稿</el-button>
        <el-button type="primary" :icon="DocumentAdd" @click="saveAssignment('published')">保存并发布</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="submissionDialogVisible" :title="submittingAssignment ? `提交 ${submittingAssignment.title}` : '提交作业'" width="560px">
      <div v-if="submittingAssignment" class="submission-guide">
        <div>
          <span>允许类型</span>
          <strong>{{ submittingAssignment.file_rules.allowed_extensions.join(', ') }}</strong>
        </div>
        <div>
          <span>大小上限</span>
          <strong>{{ submittingAssignment.file_rules.max_size_mb }} MB</strong>
        </div>
        <div>
          <span>命名要求</span>
          <strong>{{ expectedSubmissionName || submittingAssignment.file_rules.filename_template }}</strong>
        </div>
      </div>
      <input class="file-input" type="file" :accept="submittingAssignment?.file_rules.allowed_extensions.join(',')" @change="handleSubmissionFileChange" />
      <template #footer>
        <el-button @click="submissionDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="Upload" :loading="submissionLoading" @click="submitAssignmentFile">提交并检查</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="studentDialogVisible" :title="editingRosterId ? '编辑学生' : '新增学生'" width="500px">
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="真实姓名">
          <el-input v-model="rosterForm.student_name" />
        </el-form-item>
        <div class="form-grid">
          <el-form-item label="No.">
            <el-input v-model="rosterForm.student_no" placeholder="06" />
          </el-form-item>
          <el-form-item label="学号">
            <el-input v-model="rosterForm.student_number" />
          </el-form-item>
        </div>
        <el-form-item label="学生信息班级">
          <el-input v-model="rosterForm.source_class" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="studentDialogVisible = false">取消</el-button>
        <el-button type="primary" :icon="editingRosterId ? Check : CirclePlus" @click="saveRosterEntry">
          {{ editingRosterId ? '保存' : '新增' }}
        </el-button>
      </template>
    </el-dialog>
  </main>
</template>
