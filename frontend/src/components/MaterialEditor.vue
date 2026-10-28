<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api, type CodeTemplate } from '../api'
import MarkdownEditor from './MarkdownEditor.vue'

const props = defineProps<{ modelValue: boolean; file: CodeTemplate; existingNames?: string[] }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  apply: [value: { originalId: string; file: CodeTemplate }]
}>()
const content = ref('')
const filename = ref(props.file.filename)
const purpose = ref(props.file.purpose ?? '')
const creating = computed(() => !props.file.id)
const saving = ref(false)
const editor = ref<{ flush: () => Promise<void> }>()
const roleLabel = computed(() => '附件')
const contextLabel = computed(() => `${roleLabel.value} · ${filename.value}`)
let version = 0
watch(() => props.modelValue, (visible) => {
  version++
  if (visible) {
    content.value = props.file.content ?? ''
    filename.value = props.file.filename
    purpose.value = props.file.purpose ?? ''
  }
}, { immediate: true })
onBeforeUnmount(() => { version++ })

async function applyChanges() {
  if (saving.value || !props.modelValue) return
  const request = version
  const originalId = props.file.id
  saving.value = true
  try {
    await editor.value?.flush()
    let name = filename.value.trim()
    if (!name) throw new Error('请填写文件名')
    if (!name.includes('.')) name += '.md'
    if (!name.toLowerCase().endsWith('.md')) throw new Error('仅支持编辑 Markdown 文件')
    if (props.existingNames?.some(value => value.toLowerCase() === name.toLowerCase())) throw new Error('文件名已存在')
    if (purpose.value.trim().length > 120 || /[\u0000-\u001f]/.test(purpose.value)) throw new Error('附件用途须为不超过 120 字的单行文字')
    const file = new File([content.value], name, { type: 'text/markdown' })
    const result = await api.validateCodeTemplate(file)
    if (request !== version || !props.modelValue) return
    emit('apply', { originalId, file: { ...result.template, purpose: purpose.value.trim() } })
    emit('update:modelValue', false)
  } catch (error) {
    if (request === version) ElMessage.error((error as Error).message)
  } finally { saving.value = false }
}

async function closeEditor(done: () => void) {
  if (saving.value) return
  saving.value = true
  try { await editor.value?.flush(); done() }
  catch (error) { ElMessage.error((error as Error).message) }
  finally { saving.value = false }
}
</script>

<template>
  <el-dialog :model-value="modelValue" :title="`${creating ? '新建' : '编辑'}${contextLabel}`" fullscreen append-to-body destroy-on-close :before-close="closeEditor" :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving" @update:model-value="emit('update:modelValue', $event)">
    <div class="material-editor-context is-attachment">
      <el-tag type="warning" effect="dark">附件</el-tag>
      <el-input v-model="filename" aria-label="Markdown 文件名" placeholder="文件名.md" maxlength="120" class="material-filename-input" :disabled="saving" />
      <el-input v-model="purpose" aria-label="附件用途" placeholder="用途（选填）" maxlength="120" class="material-filename-input" :disabled="saving" />
    </div>
    <MarkdownEditor v-if="modelValue" ref="editor" v-model="content" persistence="form" library-role="teacher" :filename="filename" :context-label="contextLabel" @saved="applyChanges" />
    <template #footer>
      <el-button :disabled="saving" @click="closeEditor(() => emit('update:modelValue', false))">取消</el-button>
      <el-button type="primary" :loading="saving" @click="applyChanges">应用到作业</el-button>
    </template>
  </el-dialog>
</template>
