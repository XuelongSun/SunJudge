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
process.env.TZ = 'Asia/Shanghai'

const { renderContent, renderFilePreview } = loadTypeScript('markdown')
const { homeworkMarkdown, feedbackMarkdown, reportDate, deadlineFromInput, deadlineTimeInfo } = loadTypeScript('reportTemplates')
const { aiResultRows } = loadTypeScript('gradingPresentation')
const { progressPercent, filenamePreview, insertAtSelection, completionSegments } = loadTypeScript('presentation')

test('Bash fenced blocks preserve dollar substitutions without creating math or placeholders', () => {
  const command = 'for i in $(seq -w 1 20); do touch info_${i}.txt; done'
  const html = renderContent(`\`\`\`bash\n${command}\n\`\`\``, 'markdown')
  assert.match(html, /class="hljs"/)
  assert.equal(html.replace(/<[^>]*>/g, '').trim(), command)
  assert.doesNotMatch(html, /katex|SUNJUDGE_MATH/)
  const preview = renderFilePreview('command = "$(seq -w 1 20) ${i}"', 'framework.py')
  assert.match(preview.replace(/<[^>]*>/g, ''), /\$\(seq -w 1 20\) \$\{i\}/)
  assert.doesNotMatch(preview, /katex|SUNJUDGE_MATH/)
})

test('all code contexts keep literal dollars and display math delimiters', () => {
  for (const source of ['~~~bash\necho $HOME ${USER} $$\n~~~',
    '    echo $HOME ${USER} $$', '> ```bash\n> echo $HOME ${USER} $$\n> ```',
    '- 框架\n\n  ```bash\n  echo $HOME ${USER} $$\n  ```',
    '```text\n$$\nx^2\n$$\n```', '`echo $HOME ${USER}`', '``echo `pwd` $HOME ${USER}``']) {
    const html = renderContent(source, 'markdown')
    assert.doesNotMatch(html, /katex|SUNJUDGE_MATH/, source)
    assert.match(html, /\$/)
  }
})

test('math stays enabled outside code, with inline and multi-line display formulas', () => {
  const html = renderContent('公式 $x^2$，命令 `echo $HOME ${USER}`\n\n$$\nx^2 + y^2\n$$\n\n$$z^2$$', 'markdown')
  assert.match(html, /class="katex"/)
  assert.equal((html.match(/class="katex-display"/g) ?? []).length, 2)
  assert.match(html, /<code>echo \$HOME \$\{USER\}<\/code>/)
  for (const source of ['> $$\n> x^2\n> $$', '- 公式\n\n  $$\n  x^2\n  $$']) {
    assert.match(renderContent(source, 'markdown'), /class="katex-display"/)
  }
  assert.doesNotMatch(renderContent('$$unclosed\n\ntext', 'markdown'), /katex/)
})

test('escaped dollars, link destinations and old placeholder text are not turned into math HTML', () => {
  const html = renderContent('\\$x\\$ [链接](/files/$x$.md) SUNJUDGE_MATH_INLINE_0 以及 $y^2$', 'markdown')
  assert.match(html, /\$x\$/)
  assert.match(html, /href="\/files\/\$x\$\.md"/)
  assert.match(html, /SUNJUDGE_MATH_INLINE_0/)
  assert.equal((html.match(/class="katex"/g) ?? []).length, 1)
})

test('deadline input, saved UTC time and Markdown preview round trip in Shanghai time', () => {
  const input = '2030-10-11T23:59:00'
  const payload = deadlineFromInput(input)
  assert.equal(payload, '2030-10-11T15:59:00.000Z')
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


test('shared file preview renders Markdown and fences code safely including BOM and embedded backticks', () => {
  assert.match(renderFilePreview('\ufeff# 附件', 'NOTES.MD'), /<h1>附件<\/h1>/)
  const code = '```\n<script>alert(1)</script>\n# code heading\nprint(1)'
  const html = renderFilePreview(code, 'starter.py')
  assert.match(html, /class="hljs"/)
  assert.doesNotMatch(html, /<script>|<h1>/)
  assert.match(html, /code heading/)
  assert.doesNotMatch(renderFilePreview('<img src=x>', 'unknown.txt'), /<img/)
})


test('deadline entry follows the browser timezone including daylight saving', () => {
  const original = process.env.TZ
  try {
    for (const [zone, date, expected] of [
      ['Asia/Shanghai', '2030-11-05T22:00:00', '2030-11-05T14:00:00.000Z'],
      ['America/New_York', '2030-07-05T22:00:00', '2030-07-06T02:00:00.000Z'],
      ['America/New_York', '2030-11-05T22:00:00', '2030-11-06T03:00:00.000Z']]) {
      process.env.TZ = zone
      assert.equal(deadlineFromInput(date), expected)
      assert.equal(reportDate(expected).replace(' ', 'T'), date)
    }
  } finally { process.env.TZ = original }
})


test('deadline verification shows browser zone, selected-date offset and the exact UTC payload', () => {
  const original = process.env.TZ
  try {
    for (const [zone, value, offset, utc] of [
      ['Asia/Shanghai', '2030-11-05T22:00:00', 'UTC+08:00', '2030-11-05 14:00:00 UTC'],
      ['America/New_York', '2030-07-05T22:00:00', 'UTC-04:00', '2030-07-06 02:00:00 UTC'],
      ['America/New_York', '2030-11-05T22:00:00', 'UTC-05:00', '2030-11-06 03:00:00 UTC'],
      ['Asia/Kathmandu', '2030-11-05T22:00:00', 'UTC+05:45', '2030-11-05 16:15:00 UTC'],
      ['UTC', '2030-11-05T22:00:00', 'UTC+00:00', '2030-11-05 22:00:00 UTC']]) {
      process.env.TZ = zone
      const result = deadlineTimeInfo(value)
      assert.ok(result.timeZone)
      assert.equal(result.offset, offset)
      assert.equal(result.utc, utc)
      assert.equal(result.utc.replace(' UTC', '.000Z').replace(' ', 'T'), deadlineFromInput(value))
    }
    assert.equal(deadlineTimeInfo('').utc, null)
    assert.equal(deadlineTimeInfo('invalid').utc, null)
  } finally { process.env.TZ = original }
})
