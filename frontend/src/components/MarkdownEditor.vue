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
  documentId: number
  initialRevision: number
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
function insertLibraryImage(image: LibraryImage) {
  const editor = textarea.value
  const start = editor?.selectionStart ?? props.modelValue.length
  const end = editor?.selectionEnd ?? start
  const text = `![${markdownText(image.filename)}](${image.url})`
  emit('update:modelValue', props.modelValue.slice(0, start) + text + props.modelValue.slice(end))
  libraryVisible.value = false
  void nextTick(() => { editor?.focus(); editor?.setSelectionRange(start + text.length, start + text.length) })
}
const saving = ref(false)
const uploading = ref(0)
const saveError = ref('')
const dirty = computed(() => props.modelValue !== savedContent.value)
const savedContent = ref(props.modelValue)
let revision = props.initialRevision
let conflicted = false
let timer: ReturnType<typeof setTimeout> | undefined
let saveQueue = Promise.resolve()
let uploadQueue = Promise.resolve()
const status = computed(() => saveError.value || (uploading.value ? '图片上传中…' : saving.value ? '正在保存…' : dirty.value ? '等待保存…' : '草稿已保存'))

function persist() {
  const task = saveQueue.catch(() => {}).then(async () => {
    if (conflicted) throw new Error(saveError.value)
    if (props.modelValue === savedContent.value) { saveError.value = ''; return }
    const content = props.modelValue
    saving.value = true
    try {
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
  timer = setTimeout(() => { void persist().catch(() => {}) }, 900)
})

async function flush() {
  clearTimeout(timer)
  // Input and image uploads can both change while a request is in flight.
  for (;;) {
    const pendingUploads = uploadQueue
    await pendingUploads
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
        const result = await api.uploadMarkdownImage(props.documentId, file)
        const editor = textarea.value
        const start = editor?.selectionStart ?? props.modelValue.length
        const end = editor?.selectionEnd ?? start
        const text = `![${markdownText(file.name.replace(/\.[^.]+$/, '') || '图片')}](${result.asset.url})`
        emit('update:modelValue', props.modelValue.slice(0, start) + text + props.modelValue.slice(end))
        await nextTick()
        editor?.focus()
        editor?.setSelectionRange(start + text.length, start + text.length)
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
    ElMessage.info('正文已导入，本地配图请通过“插入图片”重新上传。')
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
  try { await flush() } catch (error) { ElMessage.error((error as Error).message) }
}
</script>

<template>
  <section class="online-markdown-editor" @dragover.prevent @drop="dropImages">
    <div class="markdown-editor-toolbar">
      <div class="toolbar-actions markdown-editor-buttons">
        <el-button type="primary" :loading="uploading > 0" @click="imageInput?.click()">插入图片</el-button>
        <el-button v-if="libraryRole" @click="libraryVisible = true">从图片库选择</el-button>
        <el-button @click="markdownInput?.click()">导入 .md</el-button>
        <el-button @click="downloadMarkdown">下载 .md</el-button>
        <el-button :loading="saving" @click="saveNow">保存草稿</el-button>
      </div>
      <span :class="{ 'markdown-save-error': saveError }" role="status" aria-live="polite">{{ status }}</span>
    </div>
    <p class="muted-line">支持粘贴截图、拖拽图片（PNG/JPEG，单张 ≤ 5 MB）。草稿自动保存，保存不代表提交或发布。</p>
    <input ref="imageInput" type="file" accept="image/png,image/jpeg" multiple hidden @change="selectImages" />
    <input ref="markdownInput" type="file" accept=".md" hidden @change="importMarkdown" />
    <el-dialog v-model="libraryVisible" title="我的图片库" width="min(900px, 94vw)" append-to-body destroy-on-close>
      <ImageLibrary v-if="libraryVisible && libraryRole" :role="libraryRole" selectable @select="insertLibraryImage" />
    </el-dialog>
    <div class="markdown-edit-grid">
      <label class="markdown-source-panel">
        <textarea ref="textarea" :value="modelValue" spellcheck="false" aria-label="Markdown 正文" @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)" @paste="pasteImages" @keydown.ctrl.s.prevent="saveNow" @keydown.meta.s.prevent="saveNow" />
      </label>
      <section class="markdown-live-preview" aria-label="Markdown 预览">
        <div class="assignment-rendered" v-html="renderContent(previewSource ?? modelValue, 'markdown')" />
      </section>
    </div>
  </section>
</template>
