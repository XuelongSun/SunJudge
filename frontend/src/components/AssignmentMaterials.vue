<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Download, View } from '@element-plus/icons-vue'
import { api, type CodeTemplate } from '../api'
import { renderContent } from '../markdown'
import FilePreviewDialog from './FilePreviewDialog.vue'

const props = withDefaults(defineProps<{ assignmentId?: number; files?: CodeTemplate[]; fallbackMarkdown: string; headerMarkdown?: string; showDescription?: boolean; previewOnly?: boolean }>(), { showDescription: true, previewOnly: false })
const selectedId = ref<string>()
const previewDialogVisible = ref(false)
const content = ref('')
const loading = ref(false)
const error = ref('')
let requestVersion = 0
const selectedFile = computed(() => props.files?.find(file => file.id === selectedId.value))

async function selectFile(file?: CodeTemplate) {
  const version = ++requestVersion
  selectedId.value = file?.id
  previewDialogVisible.value = Boolean(file)
  content.value = ''
  error.value = ''
  loading.value = Boolean(file)
  if (!file) return
  try {
    const source = file.content ?? (await api.previewCodeTemplate(props.assignmentId ?? 0, file.id)).template.content
    if (version !== requestVersion) return
    if (typeof source !== 'string') throw new Error('文件内容无效，请重试')
    content.value = source
  } catch (reason) {
    if (version === requestVersion) error.value = (reason as Error).message
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

function showDefault() { return selectFile() }

function downloadSelected(file = selectedFile.value) {
  if (!file) return
  const link = document.createElement('a')
  const url = file.url ?? URL.createObjectURL(new Blob([file.content ?? (file.id === selectedId.value ? content.value : '')], { type: 'text/plain;charset=utf-8' }))
  link.href = url
  link.download = file.filename
  link.click()
  if (!file.url) URL.revokeObjectURL(url)
}

function followAttachmentLink(event: MouseEvent) {
  if (!(event.target instanceof Element)) return
  const anchor = event.target.closest('a')
  const href = anchor?.getAttribute('href')
  if (!href) return
  let filename: string
  try { filename = decodeURIComponent(href.split('#')[0]!.split('?')[0]!).replace(/^\.\//, '') }
  catch { return }
  const file = props.files?.find(item => item.filename === filename || item.url === href)
  if (file) { event.preventDefault(); void selectFile(file) }
}

watch(() => [props.assignmentId, props.files], showDefault, { immediate: true, deep: true })
watch(previewDialogVisible, visible => { if (!visible && selectedId.value) void showDefault() }, { flush: 'sync' })
onBeforeUnmount(() => { requestVersion++ })
defineExpose({ selectFile, downloadSelected })
</script>

<template>
  <div class="assignment-materials">
    <section v-if="showDescription && !previewOnly" class="workflow-card student-assignment-description" aria-label="作业说明">
      <div class="assignment-rendered" @click="followAttachmentLink" v-html="renderContent(fallbackMarkdown, 'markdown')" />
    </section>
    <section v-if="files?.length && !previewOnly" class="workflow-card assignment-attachments" aria-label="作业附件">
      <div class="card-header"><h2>作业附件</h2><el-tag effect="plain">{{ files.length }}</el-tag></div>
      <el-table :data="files" row-key="id">
        <el-table-column prop="filename" label="文件名" min-width="180" />
        <el-table-column label="用途" min-width="140"><template #default="{ row }">{{ row.purpose || '—' }}</template></el-table-column>
        <el-table-column label="操作" width="210"><template #default="{ row }">
          <div class="row-actions attachment-actions">
            <el-button :icon="View" @click="selectFile(row)">预览</el-button>
            <el-button :icon="Download" @click="downloadSelected(row)">下载</el-button>
          </div>
        </template></el-table-column>
      </el-table>
    </section>
    <FilePreviewDialog v-model="previewDialogVisible" :filename="selectedFile?.filename ?? ''" :content="content" :loading="loading" :error="error" @retry="selectFile(selectedFile)" @download="downloadSelected()" @content-click="followAttachmentLink" />
  </div>
</template>
