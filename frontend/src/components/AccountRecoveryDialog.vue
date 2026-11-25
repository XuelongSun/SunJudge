<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api, type Role } from '../api'

const props = defineProps<{ mode: 'bind' | 'reset' }>()
const visible = defineModel<boolean>({ required: true })
const emit = defineEmits<{ reset: []; bound: [] }>()
const binding = computed(() => props.mode === 'bind')
const pending = ref(false)
const enabled = ref(true)
const verifiedEmail = ref<string | null>(null)
const email = ref('')
const password = ref('')
const code = ref('')
const confirmPassword = ref('')
const message = ref('')
const role = ref<Role>('student')
const identifier = ref('')
const resetIdentity = computed(() => ({ email: email.value, role: role.value, identifier: identifier.value.trim() }))
const identityMissing = computed(() => !binding.value && !identifier.value.trim())
let session = 0

watch(role, () => { identifier.value = '' }, { flush: 'sync' })
watch([role, identifier, email], () => { code.value = ''; message.value = '' }, { flush: 'sync' })

watch(visible, async open => {
  const current = ++session
  email.value = password.value = code.value = confirmPassword.value = message.value = ''
  role.value = 'student'
  identifier.value = ''
  verifiedEmail.value = null
  pending.value = false
  enabled.value = true
  if (!open || !binding.value) return
  pending.value = true
  try {
    const result = await api.recoveryEmail()
    if (current !== session) return
    verifiedEmail.value = result.email
    enabled.value = result.enabled
  } catch (error) {
    if (current === session) {
      enabled.value = false
      ElMessage.error((error as Error).message)
    }
  } finally {
    if (current === session) pending.value = false
  }
}, { flush: 'sync' })

async function sendCode() {
  if (pending.value || !email.value.trim() || identityMissing.value || (binding.value && !password.value)) return
  const current = session
  pending.value = true
  message.value = ''
  try {
    const result = binding.value ? await api.requestEmailBinding(email.value, password.value) : await api.requestPasswordReset(resetIdentity.value)
    if (current === session) {
      message.value = result.message
      if (binding.value) password.value = ''
    }
  } catch (error) {
    if (current === session) ElMessage.error((error as Error).message)
  } finally {
    if (current === session) pending.value = false
  }
}

async function confirmRecovery() {
  if (pending.value || !email.value.trim() || !code.value.trim() || identityMissing.value) return
  if (!binding.value && (password.value.length < 6 || password.value !== confirmPassword.value)) {
    ElMessage.warning('请输入至少 6 个字符的新密码，并确认两次输入一致')
    return
  }
  const current = session
  pending.value = true
  try {
    const result = binding.value ? await api.confirmEmailBinding(email.value, code.value) : await api.confirmPasswordReset({
      ...resetIdentity.value, code: code.value, password: password.value
    })
    if (current !== session) return
    ElMessage.success(result.message)
    if (binding.value) emit('bound')
    else emit('reset')
    visible.value = false
  } catch (error) {
    if (current === session) ElMessage.error((error as Error).message)
  } finally {
    if (current === session) pending.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" :title="binding ? '找回邮箱' : '找回密码'" width="min(480px, 94vw)" append-to-body destroy-on-close>
    <el-alert v-if="!enabled" title="邮件服务暂不可用" type="info" :closable="false" />
    <el-form v-else label-position="top" :disabled="pending" @submit.prevent="confirmRecovery">
      <p v-if="verifiedEmail">当前找回邮箱 {{ verifiedEmail }}</p>
      <template v-if="!binding">
        <el-form-item label="账号类型">
          <el-segmented v-model="role" :options="[{ label: '学生', value: 'student' }, { label: '教师', value: 'teacher' }, { label: '管理员', value: 'admin' }]" />
        </el-form-item>
        <el-form-item :label="role === 'student' ? '真实姓名' : '用户名'">
          <el-input v-model.trim="identifier" :aria-label="role === 'student' ? '真实姓名' : '用户名'" maxlength="80" autocomplete="username" />
        </el-form-item>
        <p>找回密码需使用已绑定邮箱。尚未绑定且已忘记密码，请联系站点运维核验身份后处理。</p>
      </template>
      <el-form-item :label="binding ? (verifiedEmail ? '新邮箱' : '邮箱') : '已绑定邮箱'">
        <el-input v-model.trim="email" type="email" autocomplete="email" maxlength="254" />
      </el-form-item>
      <el-form-item v-if="binding" label="当前密码">
        <el-input v-model="password" type="password" autocomplete="current-password" show-password />
      </el-form-item>
      <el-form-item label="邮件验证码">
        <div class="recovery-code-controls">
          <el-input v-model.trim="code" autocomplete="one-time-code" maxlength="32" placeholder="6位字母数字" aria-label="邮件验证码" />
          <el-button :disabled="!email || identityMissing || (binding && !password)" @click="sendCode">发送验证码</el-button>
        </div>
        <div v-if="message" role="status">{{ message }}</div>
      </el-form-item>
      <template v-if="!binding">
        <el-form-item label="新密码">
          <el-input v-model="password" type="password" autocomplete="new-password" show-password maxlength="1024" />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="confirmPassword" type="password" autocomplete="new-password" show-password maxlength="1024" />
        </el-form-item>
      </template>
      <el-button type="primary" native-type="submit" :disabled="!email || !code || identityMissing" :loading="pending">{{ binding ? '验证并绑定' : '重置密码' }}</el-button>
    </el-form>
  </el-dialog>
</template>
