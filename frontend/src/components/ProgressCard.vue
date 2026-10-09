<script setup lang="ts">
import { completionSegments } from '../presentation'
defineProps<{ label: string; value: string; percentage?: number; note?: string; accent?: boolean;
  completed?: number; expired?: number; total?: number; numberOnly?: boolean }>()
</script>

<template>
  <div class="progress-card" :class="{ 'progress-card-accent': accent, 'progress-card-number': numberOnly }">
    <span>{{ label }}</span>
    <strong>{{ value }}</strong>
    <div v-if="completed != null" class="completion-progress" role="img" :aria-label="`${label}：${value}，${note ?? ''}`">
      <span class="completion-progress-done" :style="{ width: `${completionSegments(completed, expired ?? 0, total ?? 0).completed}%` }" />
      <span class="completion-progress-expired" :style="{ width: `${completionSegments(completed, expired ?? 0, total ?? 0).expired}%` }" />
    </div>
    <el-progress v-else-if="!numberOnly" :aria-label="`${label}：${value}`" :percentage="percentage ?? 0" :show-text="false" :stroke-width="7" :color="accent ? 'var(--el-color-warning)' : undefined" />
    <small v-if="note">{{ note }}</small>
  </div>
</template>
