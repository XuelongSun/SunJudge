<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, type LibraryImage } from '../api'

const props = defineProps<{ selectable?: boolean; role: 'teacher' | 'student' }>()
const emit = defineEmits<{ select: [image: LibraryImage] }>()
const images = ref<LibraryImage[]>([])
const previewUrls = computed(() => images.value.map(image => image.url))
const input = ref<HTMLInputElement>()
const loading = ref(false)
async function refresh() {
  loading.value = true
  try { images.value = (await api.listLibraryImages(props.role)).assets }
  catch (error) { ElMessage.error((error as Error).message) }
  finally { loading.value = false }
}
async function upload(event: Event) {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files ?? [])
  target.value = ''
  loading.value = true
  try {
    for (const file of files) await api.uploadLibraryImage(props.role, file)
    ElMessage.success('图片已加入图片库')
  } catch (error) { ElMessage.error((error as Error).message) }
  finally { await refresh() }
}
async function remove(image: LibraryImage) {
  try { await ElMessageBox.confirm(`删除图片“${image.filename}”？被作业引用的图片会受到保护。`, '删除图片', { type: 'warning' }) }
  catch { return }
  try { await api.deleteLibraryImage(props.role, image.id); await refresh() }
  catch (error) { ElMessage.error((error as Error).message) }
}
onMounted(refresh)
</script>

<template>
  <section v-loading="loading">
    <div class="toolbar-actions">
      <el-button type="primary" :disabled="loading" @click="input?.click()">上传图片</el-button>
      <el-button :disabled="loading" @click="refresh">刷新</el-button>
      <span>{{ images.length }} 张 · {{ (images.reduce((sum, image) => sum + image.file_size, 0) / 1024 / 1024).toFixed(1) }} MB</span>
    </div>
    <p class="muted-line">PNG/JPEG，单张 ≤ 5 MB；图片库上限 1000 张 / 500 MB。点击图片可预览，仍被作业或草稿引用的图片不能删除。</p>
    <input ref="input" type="file" accept="image/png,image/jpeg" multiple hidden @change="upload" />
    <div class="teacher-image-grid">
      <article v-for="(image, index) in images" :key="image.id" class="teacher-image-card">
        <el-image :src="image.url" :alt="image.filename" fit="contain" loading="lazy" :preview-src-list="previewUrls" :initial-index="index" preview-teleported />
        <span class="teacher-image-name" :title="image.filename">{{ image.filename }}</span>
        <div>
          <el-button v-if="selectable" type="primary" size="small" @click="emit('select', image)">插入</el-button>
          <el-button type="danger" plain size="small" :disabled="loading" @click="remove(image)">删除</el-button>
        </div>
      </article>
    </div>
    <el-empty v-if="!loading && !images.length" description="图片库为空，可上传图片或在 Markdown 编辑时直接上传" />
  </section>
</template>
