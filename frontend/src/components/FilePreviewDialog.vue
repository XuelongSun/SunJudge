<script setup lang="ts">
import { computed, ref } from 'vue'
import { CopyDocument, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { renderFilePreview } from '../markdown'

const props = withDefaults(defineProps<{
  modelValue: boolean
  filename: string
  content?: string | null
  loading?: boolean
  error?: string
  previewable?: boolean
  message?: string
}>(), { content: null, loading: false, error: '', previewable: true, message: '此文件暂不支持预览' })
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  download: []
  retry: []
  'content-click': [event: MouseEvent]
}>()
const rendered = computed(() => renderFilePreview(props.content ?? '', props.filename))
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
  <el-dialog :model-value="modelValue" :title="filename ? `${filename} 在线预览` : '在线预览'" class="file-preview-dialog" width="min(960px, 94vw)" append-to-body destroy-on-close @update:model-value="emit('update:modelValue', $event)">
    <el-skeleton v-if="loading" :rows="6" animated />
    <div v-else-if="error" role="alert">
      <el-alert :title="error" type="error" :closable="false" />
      <el-button @click="emit('retry')">重新加载</el-button>
    </div>
    <div v-else-if="previewable" class="assignment-rendered file-preview-content" @click="emit('content-click', $event)" v-html="rendered" />
    <el-empty v-else :description="message" />
    <template #footer>
      <div class="row-actions file-preview-actions">
        <el-button @click="emit('update:modelValue', false)">关闭</el-button>
        <el-button v-if="filename" :icon="Download" @click="emit('download')">下载文件</el-button>
        <el-button :icon="CopyDocument" :disabled="!canCopy" :loading="copying" @click="copyContent">复制内容</el-button>
      </div>
    </template>
  </el-dialog>
</template>
