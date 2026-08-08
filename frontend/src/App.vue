<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Check,
  CirclePlus,
  Close,
  Delete,
  DocumentAdd,
  Edit,
  Moon,
  Refresh,
  Sunny,
  SwitchButton,
  Upload,
  View
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api, type AdminClass, type PublicClass, type Role, type RosterEntry, type TeacherStatus, type User } from './api'

const currentUser = ref<User | null>(null)
const teachers = ref<User[]>([])
const adminClasses = ref<AdminClass[]>([])
const studentClasses = ref<PublicClass[]>([])
const selectedClassId = ref<number | undefined>()
const selectedStudentClassId = ref<number | undefined>()
const roster = ref<RosterEntry[]>([])
const selectedFile = ref<File | null>(null)
const loading = ref(false)
const teacherLoading = ref(false)
const classLoading = ref(false)
const rosterLoading = ref(false)
const authMode = ref<'login' | 'register'>('login')
const registerRole = ref<'student' | 'teacher'>('student')
const theme = ref<'light' | 'dark'>('light')

const classDialogVisible = ref(false)
const importDialogVisible = ref(false)
const rosterDrawerVisible = ref(false)
const studentDialogVisible = ref(false)
const classMetaDialogVisible = ref(false)
const editingRosterId = ref<number | null>(null)
const editingClassId = ref<number | null>(null)

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

const isAdmin = computed(() => currentUser.value?.role === 'admin')
const isTeacher = computed(() => currentUser.value?.role === 'teacher')
const pendingTeachers = computed(() => teachers.value.filter((teacher) => teacher.teacher_status === 'pending'))
const currentClass = computed(() => adminClasses.value.find((item) => item.id === selectedClassId.value))
const currentStudentClass = computed(() => studentClasses.value.find((item) => item.id === selectedStudentClassId.value))
const selectedClassRosterCount = computed(() => currentClass.value?.roster_count ?? roster.value.length)
const accountDisplayName = computed(() => {
  if (!currentUser.value) {
    return ''
  }
  return currentUser.value.role === 'student' ? currentUser.value.student_name ?? '' : currentUser.value.username
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

function selectStudentClass(courseClass: PublicClass) {
  selectedStudentClassId.value = selectedStudentClassId.value === courseClass.id ? undefined : courseClass.id
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
  selectedClassId.value = undefined
  selectedStudentClassId.value = undefined
  rosterDrawerVisible.value = false
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

function showComingSoon(feature: string) {
  ElMessage.info(`${feature} 将在后续里程碑开放`)
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
                  <el-table-column label="作业" width="90">
                    <template #default>0</template>
                  </el-table-column>
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
          <el-table-column label="作业" width="90">
            <template #default>0</template>
          </el-table-column>
          <el-table-column label="操作" width="520" fixed="right">
            <template #default="{ row }">
              <div class="row-actions">
                <el-button :icon="View" @click="openRosterDrawer(row)">学生列表</el-button>
                <el-button :icon="View" @click="showComingSoon('作业列表')">作业列表</el-button>
                <el-button :icon="DocumentAdd" @click="showComingSoon('发布作业')">发布作业</el-button>
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
          <el-table :data="studentClasses" v-loading="classLoading" row-key="id" empty-text="暂无班级">
            <el-table-column v-if="!currentStudentClass" prop="course.semester" label="学期" min-width="130" />
            <el-table-column prop="course.name" label="课程" min-width="170" />
            <el-table-column v-if="!currentStudentClass" prop="course.teacher_name" label="教师" min-width="120" />
            <el-table-column prop="alias" label="别名" width="120" />
            <el-table-column v-if="!currentStudentClass" prop="student.student_id" label="编号" min-width="150" />
            <el-table-column label="操作" width="90" fixed="right">
              <template #default="{ row }">
                <el-button
                  :icon="View"
                  circle
                  :type="selectedStudentClassId === row.id ? 'primary' : 'default'"
                  :title="selectedStudentClassId === row.id ? '收起班级' : '进入班级'"
                  @click="selectStudentClass(row)"
                />
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
          <div class="assignment-empty">暂无作业</div>
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
