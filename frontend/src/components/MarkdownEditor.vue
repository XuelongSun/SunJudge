<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { renderContent } from '../markdown'
import { markdownText } from '../reportTemplates'
import ImageLibrary from './ImageLibrary.vue'
import type { LibraryImage } from '../api'

const props = defineProps<{
  modelValue: string
  documentId?: number
  initialRevision?: number
  persistence?: 'document' | 'form'
  contextLabel?: string
  filename?: string
  previewSource?: string
  libraryRole?: 'teacher' | 'student'
}>()
const emit = defineEmits<{
  'update:modelValue': [value: string]
  saved: []
}>()
const textarea = ref<HTMLTextAreaElement>()
const imageInput = ref<HTMLInputElement>()
const markdownInput = ref<HTMLInputElement>()
const libraryVisible = ref(false)
let insertion: { start: number; end: number; top: number; left: number } | undefined
function rememberInsertion() {
  const editor = textarea.value
  if (editor) insertion = { start: editor.selectionStart, end: editor.selectionEnd, top: editor.scrollTop, left: editor.scrollLeft }
}
async function insertText(text: string) {
  const editor = textarea.value
  const position = insertion ?? { start: editor?.selectionStart ?? props.modelValue.length, end: editor?.selectionEnd ?? props.modelValue.length, top: editor?.scrollTop ?? 0, left: editor?.scrollLeft ?? 0 }
  const start = Math.min(position.start, props.modelValue.length)
  const end = Math.min(position.end, props.modelValue.length)
  emit('update:modelValue', props.modelValue.slice(0, start) + text + props.modelValue.slice(end))
  await nextTick()
  editor?.focus({ preventScroll: true })
  editor?.setSelectionRange(start + text.length, start + text.length)
  if (editor) { editor.scrollTop = position.top; editor.scrollLeft = position.left }
  insertion = { ...position, start: start + text.length, end: start + text.length }
}
async function indent(event: KeyboardEvent) {
  if (event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return
  event.preventDefault()
  const editor = textarea.value
  if (!editor) return
  const { selectionStart: start, selectionEnd: end, scrollTop: top } = editor
  const source = props.modelValue
  const begin = start === 0 ? 0 : source.lastIndexOf('\n', start - 1) + 1
  const lineEnd = source.indexOf('\n', start)
  const finish = start === end && event.shiftKey ? (lineEnd < 0 ? source.length : lineEnd) : end > start && source[end - 1] === '\n' ? end - 1 : end
  let next: string, left: number, right: number
  if (start === end && !event.shiftKey) {
    next = source.slice(0, start) + '    ' + source.slice(end)
    left = right = start + 4
  } else {
    const lines = source.slice(begin, finish).split('\n')
    let removedFirst = 0, delta = 0
    const changed = lines.map((line, index) => {
      const removed = event.shiftKey ? (line.match(/^(?:\t| {1,4})/)?.[0].length ?? 0) : 0
      if (index === 0) removedFirst = removed
      delta += event.shiftKey ? -removed : 4
      return event.shiftKey ? line.slice(removed) : '    ' + line
    }).join('\n')
    next = source.slice(0, begin) + changed + source.slice(finish)
    left = event.shiftKey ? Math.max(begin, start - removedFirst) : start + 4
    right = Math.max(left, end + delta)
  }
  emit('update:modelValue', next)
  await nextTick()
  editor.setSelectionRange(left, right)
  editor.scrollTop = top
  rememberInsertion()
}
function insertLibraryImage(image: LibraryImage) {
  const text = `![${markdownText(image.filename)}](${image.url})`
  libraryVisible.value = false
  void insertText(text)
}
const saving = ref(false)
const uploading = ref(0)
const saveError = ref('')
const dirty = computed(() => props.modelValue !== savedContent.value)
const savedContent = ref(props.modelValue)
let revision = props.initialRevision ?? 0
let conflicted = false
let timer: ReturnType<typeof setTimeout> | undefined
let saveQueue = Promise.resolve()
let uploadQueue = Promise.resolve()
const localForm = computed(() => props.persistence === 'form')
const status = computed(() => saveError.value || (uploading.value ? '图片上传中…' : saving.value ? '正在保存…' : localForm.value ? (dirty.value ? '待应用到作业' : '随作业保存') : dirty.value ? '等待保存…' : '草稿已保存'))

function persist() {
  if (localForm.value) return Promise.resolve()
  const task = saveQueue.catch(() => {}).then(async () => {
    if (conflicted) throw new Error(saveError.value)
    if (props.modelValue === savedContent.value) { saveError.value = ''; return }
    const content = props.modelValue
    saving.value = true
    try {
      if (!props.documentId) throw new Error('草稿尚未加载')
      const result = await api.saveMarkdownDocument(props.documentId, content, revision)
      revision = result.document.revision
      savedContent.value = content
      saveError.value = ''
      emit('saved')
    } catch (error) {
      saveError.value = (error as Error).message
      if (saveError.value.includes('其他窗口')) conflicted = true
      throw error
    } finally {
      saving.value = false
    }
  })
  saveQueue = task
  return task
}

watch(() => props.modelValue, () => {
  clearTimeout(timer)
  if (localForm.value) return
  timer = setTimeout(() => { void persist().catch(() => {}) }, 900)
})

async function flush() {
  clearTimeout(timer)
  // Input and image uploads can both change while a request is in flight.
  for (;;) {
    const pendingUploads = uploadQueue
    await pendingUploads
    if (localForm.value) {
      if (pendingUploads === uploadQueue) return
      continue
    }
    await persist()
    if (pendingUploads === uploadQueue && props.modelValue === savedContent.value) return
  }
}
defineExpose({ flush })
function warnUnsaved(event: BeforeUnloadEvent) {
  if (dirty.value || uploading.value || saving.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
onMounted(() => window.addEventListener('beforeunload', warnUnsaved))
onBeforeUnmount(() => {
  clearTimeout(timer)
  window.removeEventListener('beforeunload', warnUnsaved)
})

function addImages(files: File[]) {
  for (const file of files) {
    uploading.value++
    uploadQueue = uploadQueue.then(async () => {
      try {
        const result = localForm.value && props.libraryRole
          ? await api.uploadLibraryImage(props.libraryRole, file)
          : await api.uploadMarkdownImage(props.documentId!, file)
        const text = `![${markdownText(file.name.replace(/\.[^.]+$/, '') || '图片')}](${result.asset.url})`
        await insertText(text)
      } catch (error) {
        ElMessage.error(`图片上传失败：${(error as Error).message}`)
      } finally {
        uploading.value--
      }
    })
  }
}

function selectImages(event: Event) {
  const input = event.target as HTMLInputElement
  addImages(Array.from(input.files || []))
  input.value = ''
}
function pasteImages(event: ClipboardEvent) {
  const images = Array.from(event.clipboardData?.items || [])
    .filter(item => item.type.startsWith('image/')).map(item => item.getAsFile()).filter((file): file is File => !!file)
  if (images.length) { event.preventDefault(); addImages(images) }
}
function dropImages(event: DragEvent) {
  const files = Array.from(event.dataTransfer?.files || [])
  if (!files.length) return
  event.preventDefault()
  const images = files.filter(file => file.type.startsWith('image/') || /\.(png|jpe?g)$/i.test(file.name))
  if (images.length) addImages(images)
  else ElMessage.info('拖拽区域仅接收图片，Markdown 文件请使用“导入 .md”。')
}
async function importMarkdown(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (file.size > 1024 * 1024) { ElMessage.error('导入文件不能超过 1 MB'); return }
  try {
    const content = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer())
    emit('update:modelValue', content.replace(/^\uFEFF/, ''))
    ElMessage.info('已导入正文')
  } catch { ElMessage.error('无法读取文件，请使用 UTF-8 编码的 Markdown 文件。') }
}
function downloadMarkdown() {
  const url = URL.createObjectURL(new Blob([props.modelValue], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = props.filename || 'document.md'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
async function saveNow() {
  try { await flush(); if (localForm.value) emit('saved') } catch (error) { ElMessage.error((error as Error).message) }
}
</script>

<template>
  <section class="online-markdown-editor" @dragover.prevent @drop="dropImages">
    <div class="markdown-editor-toolbar">
      <div class="toolbar-actions markdown-editor-buttons">
        <el-button type="primary" :loading="uploading > 0" @mousedown.prevent="rememberInsertion" @click="rememberInsertion(); imageInput?.click()">插入图片</el-button>
        <el-button v-if="libraryRole" @mousedown.prevent="rememberInsertion" @click="rememberInsertion(); libraryVisible = true">从图片库选择</el-button>
        <el-button @click="markdownInput?.click()">导入 .md</el-button>
        <el-button @click="downloadMarkdown">下载 .md</el-button>
        <el-button v-if="!localForm" :loading="saving" @click="saveNow">保存草稿</el-button>
      </div>
      <span :class="{ 'markdown-save-error': saveError }" role="status" aria-live="polite">{{ status }}</span>
    </div>
    <input ref="imageInput" type="file" accept="image/png,image/jpeg" multiple hidden @change="selectImages" />
    <input ref="markdownInput" type="file" accept=".md" hidden @change="importMarkdown" />
    <el-dialog v-model="libraryVisible" title="我的图片库" width="min(900px, 94vw)" append-to-body destroy-on-close>
      <ImageLibrary v-if="libraryVisible && libraryRole" :role="libraryRole" selectable @select="insertLibraryImage" />
    </el-dialog>
    <div class="markdown-edit-grid">
      <label class="markdown-source-panel">
        <textarea ref="textarea" :value="modelValue" spellcheck="false" :aria-label="contextLabel ? `${contextLabel} 正文` : 'Markdown 正文'" @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value); rememberInsertion()" @click="rememberInsertion" @keyup="rememberInsertion" @select="rememberInsertion" @paste="rememberInsertion(); pasteImages($event)" @keydown.tab="indent" @keydown.ctrl.s.prevent="saveNow" @keydown.meta.s.prevent="saveNow" />
      </label>
      <section class="markdown-live-preview" :aria-label="contextLabel ? `${contextLabel} 预览` : 'Markdown 预览'">
        <div class="assignment-rendered" v-html="renderContent(previewSource ?? modelValue, 'markdown')" />
      </section>
    </div>
  </section>
</template>
