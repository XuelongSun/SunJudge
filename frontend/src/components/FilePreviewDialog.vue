<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { CopyDocument, Download } from '@element-plus/icons-vue'
import { ElDialog, ElMessage } from 'element-plus'
import { renderFilePreview } from '../markdown'

const props = withDefaults(defineProps<{
  modelValue: boolean
  filename: string
  content?: string | null
  loading?: boolean
  error?: string
  previewable?: boolean
  message?: string
  dockTarget?: string
  downloadable?: boolean
}>(), { content: null, loading: false, error: '', previewable: true, message: '此文件暂不支持预览', downloadable: true })
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  download: []
  retry: []
  'content-click': [event: MouseEvent]
}>()
const docked = ref(false)
const raw = ref(false)
const markdown = computed(() => props.filename.toLowerCase().endsWith('.md'))
const title = computed(() => props.filename ? `${props.filename} 在线预览` : '在线预览')
const dialogProps = computed(() => ({
  modelValue: props.modelValue, title: title.value, width: 'min(960px, 94vw)', appendToBody: true, destroyOnClose: true,
  'onUpdate:modelValue': (value: boolean) => emit('update:modelValue', value)
}))
const rendered = computed(() => renderFilePreview(props.content ?? '', props.filename))
watch(() => props.filename, () => { raw.value = false })
watch(() => props.modelValue, visible => {
  if (!visible) { docked.value = false; raw.value = false }
})
const copying = ref(false)
const canCopy = computed(() => props.modelValue && !props.loading && !props.error && props.previewable && props.content !== null && !copying.value)

async function copyContent() {
  if (!canCopy.value) return
  const source = props.content!
  copying.value = true
  try {
    await navigator.clipboard.writeText(source)
    ElMessage.success('已复制原始内容')
  } catch {
    ElMessage.warning('复制失败，请重试或下载文件')
  } finally {
    copying.value = false
  }
}
</script>

<template>
  <Teleport :to="dockTarget || 'body'" :disabled="!docked || !dockTarget">
    <component :is="docked && dockTarget ? 'aside' : ElDialog" v-if="modelValue || !docked" v-bind="docked && dockTarget ? { 'aria-label': title } : dialogProps" class="file-preview-dialog">
      <strong v-if="docked" class="file-preview-dock-title">{{ title }}</strong>
      <div v-if="markdown && previewable && !loading && !error" class="file-preview-mode">
        <el-switch v-model="raw" active-text="显示原文" aria-label="显示 Markdown 原文" />
      </div>
      <div class="file-preview-body">
        <el-skeleton v-if="loading" :rows="6" animated />
        <div v-else-if="error" role="alert">
          <el-alert :title="error" type="error" :closable="false" />
          <el-button @click="emit('retry')">重新加载</el-button>
        </div>
        <pre v-else-if="previewable && markdown && raw" class="file-preview-source" v-text="content ?? ''" />
        <div v-else-if="previewable" class="assignment-rendered file-preview-content" @click="emit('content-click', $event)" v-html="rendered" />
        <el-empty v-else :description="message" />
      </div>
      <div class="row-actions file-preview-actions">
        <el-button @click="emit('update:modelValue', false)">关闭</el-button>
        <el-button v-if="dockTarget" @click="docked = !docked">{{ docked ? '恢复弹窗' : '悬停预览' }}</el-button>
        <el-button v-if="filename" :icon="Download" :disabled="!downloadable" @click="emit('download')">下载文件</el-button>
        <el-button :icon="CopyDocument" :disabled="!canCopy" :loading="copying" @click="copyContent">复制内容</el-button>
      </div>
    </component>
  </Teleport>
</template>
