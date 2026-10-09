export function progressPercent(value: number | null | undefined, total: number | null | undefined) {
  if (value == null || total == null || !Number.isFinite(value) || !Number.isFinite(total) || total <= 0) return 0
  return Math.min(100, Math.max(0, Math.round(value / total * 10000) / 100))
}

export function filenamePreview(template: string, values: Record<string, string>) {
  return template.replace(/\{([^{}]+)\}/g, (placeholder, key: string) => values[key] ?? placeholder)
}

export function insertAtSelection(value: string, token: string, start: number, end = start) {
  const from = Math.min(value.length, Math.max(0, start))
  const to = Math.min(value.length, Math.max(from, end))
  return { value: value.slice(0, from) + token + value.slice(to), cursor: from + token.length }
}

export function completionSegments(completed: number, expired: number, total: number) {
  const done = progressPercent(completed, total)
  return { completed: done, expired: Math.min(100 - done, progressPercent(expired, total)) }
}
