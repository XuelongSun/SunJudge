// Metadata is literal text; Markdown is intentionally preserved only in document bodies.
export function reportDate(value: string | null): string {
  if (!value) return '未设置'
  const date = new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`)
  if (Number.isNaN(date.getTime())) return '未设置'
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
  }).format(date)
}

export function markdownText(value: unknown): string {
  return String(value ?? '').replace(/\r?\n/g, ' ').replace(/[\\`*_{}\[\]()#+.!|<>~]/g, '\\$&')
}

export function markdownFilename(value: unknown): string {
  const text = String(value || '-').replace(/\r?\n/g, ' ').replace(/\|/g, '\\|')
  const fence = '`'.repeat(Math.max(0, ...(text.match(/`+/g) || []).map(run => run.length)) + 1)
  return `${fence} ${text} ${fence}`
}

export function homeworkMarkdown(data: {
  title: string; course: string; teacher: string; publishedAt: string
  deadline: string; maxScore: number; description: string | null
}) {
  return [
    `## ${markdownText(data.title)}`,
    '', `*${markdownText(data.course)} - ${markdownText(data.teacher)} - ${markdownText(data.publishedAt.slice(0, 10))}*`,
    '', `**截止时间 :watch: ：${markdownText(data.deadline)}**`,
    '', `**分数 :100: ：${data.maxScore}**`, '', '---', '', data.description || ''
  ].join('\n')
}

export function feedbackMarkdown(data: {
  name: string; studentNumber: string; code: string; submittedAt: string; deadline: string
  score: number; course: string; teacher: string; publishedAt: string; comment: string
  files: Array<{ label: string; filename: string; weight: number; score: number; maxScore: number; comment: string }>
}) {
  const cell = markdownText
  return [
    '|姓名|学号|作业代码|提交时间|截止时间|得分|',
    '|--|--|--|--|--|--|',
    `|${[data.name, data.studentNumber, data.code, data.submittedAt, data.deadline, data.score].map(cell).join('|')}|`,
    '', '---', '', '|文件|提交文件|权重|得分/满分|备注|', '|:-:|:-:|:-:|:-:|--|',
    ...data.files.map(file => `|${cell(file.label)}|${markdownFilename(file.filename)}|${file.weight}%|${file.score} / ${file.maxScore}|${cell(file.comment || '-')}|`),
    '', '---', '', data.comment, '', '---',
    '', `*${cell(data.course)} - ${cell(data.teacher)} - ${cell(data.publishedAt.slice(0, 10))}*`
  ].join('\n')
}
