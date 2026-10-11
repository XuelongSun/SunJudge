import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const Module = require('node:module')
function loadTypeScript(name) {
  const filename = fileURLToPath(new URL(`../src/${name}.ts`, import.meta.url))
  const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true }
  }).outputText
  const module = new Module(filename)
  module.paths = Module._nodeModulePaths(path.dirname(filename))
  module._compile(compiled, filename)
  return module.exports
}
const { renderContent } = loadTypeScript('markdown')
const { homeworkMarkdown, feedbackMarkdown, reportDate, deadlineFromInput } = loadTypeScript('reportTemplates')
const { aiResultRows } = loadTypeScript('gradingPresentation')
const { progressPercent, filenamePreview, insertAtSelection, completionSegments } = loadTypeScript('presentation')

test('deadline input, saved UTC time and Markdown preview round trip in Shanghai time', () => {
  const input = '2030-10-11T23:59:00'
  const payload = deadlineFromInput(input)
  assert.equal(payload, '2030-10-11T23:59:00+08:00')
  assert.equal(new Date(payload).toISOString(), '2030-10-11T15:59:00.000Z')
  assert.equal(reportDate(payload), '2030-10-11 23:59:00')
  assert.equal(reportDate('2030-10-11T15:59:00').replace(' ', 'T'), input)
  assert.equal(deadlineFromInput(''), null)
})

test('progress ratios handle empty metrics and late submission durations', () => {
  assert.equal(progressPercent(3, 4), 75)
  assert.equal(progressPercent(0, 0), 0)
  assert.equal(progressPercent(null, 100), 0)
  assert.equal(progressPercent(8, 5), 100)
  assert.equal(progressPercent(-1, 5), 0)
  assert.equal(progressPercent(Infinity, 5), 0)
})

test('filename preview includes course alias and replaces repeated tokens', () => {
  assert.equal(filenamePreview('{course_alias}_{student_no}_{name}_{assignment_code}_{student_no}{extension}', {
    course_alias: 'OS202601', student_no: '06', name: '测试学生', assignment_code: 'hw1', extension: '.md'
  }), 'OS202601_06_测试学生_hw1_06.md')
})

test('completion bar separates completed, expired and pending proportions', () => {
  assert.deepEqual(completionSegments(6, 2, 10), { completed: 60, expired: 20 })
  assert.deepEqual(completionSegments(0, 10, 10), { completed: 0, expired: 100 })
  assert.deepEqual(completionSegments(10, 0, 10), { completed: 100, expired: 0 })
  assert.deepEqual(completionSegments(0, 0, 0), { completed: 0, expired: 0 })
  assert.deepEqual(completionSegments(9, 3, 10), { completed: 90, expired: 10 })
})

test('filename fields replace selections and leave the cursor after successive inserts', () => {
  const initial = 'prefix_report.md'
  const middle = insertAtSelection(initial, '{student_no}', 7, 13)
  assert.deepEqual(middle, { value: 'prefix_{student_no}.md', cursor: 19 })
  const next = insertAtSelection(middle.value, '{name}', middle.cursor, middle.cursor)
  assert.deepEqual(next, { value: 'prefix_{student_no}{name}.md', cursor: 25 })
  assert.equal(insertAtSelection(initial, '{course_alias}', 0).value, '{course_alias}prefix_report.md')
  assert.equal(insertAtSelection(initial, '{extension}', 999).value, 'prefix_report.md{extension}')
  assert.equal(insertAtSelection(initial, '{name}', 0, initial.length).value, '{name}')
})

test('report dates include seconds and consistently use Shanghai time', () => {
  assert.equal(reportDate('2026-10-08T12:00:00'), '2026-10-08 20:00:00')
  assert.equal(reportDate('2026-10-08T12:00:00Z'), '2026-10-08 20:00:00')
  assert.equal(reportDate(null), '未设置')
})

test('homework layout and emoji shortcodes render', () => {
  const source = homeworkMarkdown({ title: '练习', course: 'Python', teacher: '教师', publishedAt: '2026-10-08', deadline: '2026-10-10', maxScore: 100, description: '- **要求** :smile: ✅' })
  const html = renderContent(source, 'markdown')
  assert.match(html, /<h2>练习<\/h2>/)
  assert.match(html, /⌚/)
  assert.match(html, /💯/)
  assert.match(html, /😄 ✅/)
  assert.match(html, /<strong>要求<\/strong>/)
})

test('feedback tables withstand pipes, newlines and backticks; summary keeps Markdown', () => {
  const source = feedbackMarkdown({ name: 'A|B', studentNumber: '001', code: 'hw1', submittedAt: '-', deadline: '-', score: 75, course: 'Python', teacher: '教师', publishedAt: '-', comment: '## 建议\n\n- **继续** :thumbsup: ✅\n\n$x^2$\n\n```python\nprint(1)\n```', files: [{ label: '报告', filename: 'a`|b.md', weight: 100, score: 75, maxScore: 100, comment: '第一行|内容\n第二行' }] })
  const html = renderContent(source, 'markdown')
  assert.equal((html.match(/<table(?:\s[^>]*)?>/g) || []).length, 2)
  assert.match(html, /<table class="feedback-file-table">/)
  assert.match(source, /得分\/满分\|备注\|/)
  assert.equal((html.match(/<td/g) || []).length, 11)
  assert.match(html, /<td>A\|B<\/td>/)
  assert.match(html, /<code>a`\|b.md<\/code>/)
  assert.match(html, /<h2>建议<\/h2>/)
  assert.doesNotMatch(source, /\*\*评语：\*\*/)
  assert.match(source, /---\n\n## 建议/)
  assert.match(html, /<strong>继续<\/strong> 👍 ✅/)
  assert.match(html, /class="katex"/)
  assert.match(html, /class="hljs"/)
})

test('code keeps emoji shortcodes; raw HTML and executable links stay inert', () => {
  const html = renderContent('`:smile:`\n\n```\n:100:\n```\n\n<script>alert(1)</script>\n\n[x](javascript:alert(1))', 'markdown')
  assert.match(html, /<code>:smile:<\/code>/)
  assert.match(html, /:100:/)
  assert.doesNotMatch(html, /<script>|href="javascript:/)
  assert.match(html, /&lt;script&gt;/)
})

test('feedback column constraints recognize new and historical reports, leaving ordinary tables intact', () => {
  for (const label of ['备注', '评语']) {
    const html = renderContent(`|文件|提交文件|权重|得分/满分|${label}|\n|--|--|--|--|--|\n|报告|report.md|100%|80/100|${'很长的备注'.repeat(100)}|`, 'markdown')
    assert.match(html, /class="feedback-file-table"/)
    assert.match(html, /class="markdown-table-scroll"/)
    assert.ok(html.includes('很长的备注'.repeat(100)), 'long remarks must wrap without data loss')
  }
  assert.doesNotMatch(renderContent('|A|B|\n|--|--|\n|1|2|', 'markdown'), /feedback-file-table/)
})

test('AI legacy results calculate criterion caps and percentage weights from teacher configuration', () => {
  const rows = aiResultRows({ score_percent: 40,
    criteria_items: [{ content: '概念', weight: 1 }, { content: '分析', weight: 3 }],
    criteria_results: [{ content: '分析', score: 20, weight: 3 }, { content: '概念', score: 8, weight: 1 }]
  }, 100)
  assert.deepEqual(rows.map(row => [row.max_score, row.weight_percent]), [[30, 75], [10, 25]])
  const rounded = aiResultRows({ max_score: 10, criteria_results: [1, 2, 3].map(criterion_id => ({ criterion_id, weight: 1 })) }, 100)
  assert.deepEqual(rounded.map(row => row.max_score), [3.34, 3.33, 3.33])
  assert.equal(aiResultRows({ max_score: 40, criteria_results: [{ weight: 100, max_score: 39 }] }, 100)[0].max_score, 39)
})

test('publication footers use days while deadline and submission timestamps retain precision', () => {
  const homework = homeworkMarkdown({ title: '标题', course: '课程', teacher: '教师', publishedAt: '2026-10-09 12:34:56', deadline: '2026-10-10 08:00:00', maxScore: 100, description: '' })
  assert.match(homework, /课程 - 教师 - 2026-10-09\*/)
  assert.doesNotMatch(homework, /12:34:56/)
  assert.match(homework, /2026-10-10 08:00:00/)
  const feedback = feedbackMarkdown({ name: '学生', studentNumber: '001', code: 'hw1', submittedAt: '2026-10-09 08:30:00', deadline: '-', score: 80, course: '课程', teacher: '教师', publishedAt: '2026-10-09 12:34:56', comment: '', files: [] })
  assert.match(feedback, /2026-10-09 08:30:00/)
  assert.match(feedback, /课程 - 教师 - 2026-10-09\*/)
})
