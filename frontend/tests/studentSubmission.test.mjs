import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

// Exercise the actual App handlers with API/state doubles, without booting services.
const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8').split('<script setup lang="ts">')[1].split('</script>')[0]
const source = ts.createSourceFile('App.ts', app, ts.ScriptTarget.ES2020, true)
const names = ['canSubmitRequirement', 'openSubmissionDialog', 'selectStudentAssignment']
const handlers = source.statements.filter(node => ts.isFunctionDeclaration(node) && names.includes(node.name?.text)).map(node => node.getText(source)).join('\n')
assert.equal(source.statements.filter(node => ts.isFunctionDeclaration(node) && names.includes(node.name?.text)).length, names.length)
const code = ts.transpileModule(handlers, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText
const expired = { id: 7, class_id: 1, read_at: '2030-01-01', status: 'published', is_expired: true, makeup_allowed: false,
  submission_requirements: [{ key: 'report', allowed_extensions: ['.md'] }] }
const allowed = () => ({ ...expired, is_expired: false, makeup_allowed: true })
function setup(api) {
  const ref = value => ({ value })
  const messages = []
  const bindings = { api, ElMessage: { error: message => messages.push(message), warning: message => messages.push(message) },
    selectedStudentClassId: ref(1), currentUser: ref({ role: 'student' }), studentAssignments: ref([{ ...expired }]),
    selectedStudentAssignmentId: ref(7), submittingAssignment: ref(null), submittingRequirement: ref(null), selectedSubmissionFile: ref(null),
    studentMarkdownDocument: ref(null), studentMarkdownContent: ref(''), markdownDialogVisible: ref(false), submissionDialogVisible: ref(false), submissionOpening: ref(false) }
  const actions = new Function(...Object.keys(bindings), `let submissionOpenRequest = 0;\n${code}\nreturn {${names.join(',')}}`)(...Object.values(bindings))
  return { ...bindings, ...actions, messages }
}

test('an expired cached assignment refreshes makeup permission and opens the online editor', async () => {
  const calls = []
  const ui = setup({ markAssignmentRead: async id => { calls.push(id); return { assignment: allowed() } },
    openMarkdownDocument: async () => ({ document: { id: 8, content: '# 补交' } }) })
  await ui.openSubmissionDialog(expired, expired.submission_requirements[0])
  assert.deepEqual(calls, [7])
  assert.equal(ui.markdownDialogVisible.value, true)
  assert.equal(ui.studentMarkdownContent.value, '# 补交')
  assert.equal(ui.studentAssignments.value[0].makeup_allowed, true)
  assert.equal(ui.submissionOpening.value, false)
})

test('local Markdown upload opens the file dialog after checking the fresh makeup permission', async () => {
  const ui = setup({ markAssignmentRead: async () => ({ assignment: allowed() }),
    openMarkdownDocument: () => { throw new Error('must use upload dialog') } })
  await ui.openSubmissionDialog(expired, expired.submission_requirements[0], true)
  assert.equal(ui.submissionDialogVisible.value, true)
  assert.equal(ui.markdownDialogVisible.value, false)
  assert.equal(ui.submittingAssignment.value.makeup_allowed, true)
})

test('denied or revoked makeup permission shows a message and opens neither dialog', async () => {
  for (const upload of [false, true]) {
    const ui = setup({ markAssignmentRead: async () => ({ assignment: expired }) })
    await ui.openSubmissionDialog(allowed(), expired.submission_requirements[0], upload)
    assert.equal(ui.submissionDialogVisible.value, false)
    assert.equal(ui.markdownDialogVisible.value, false)
    assert.match(ui.messages[0], /尚未获得补交权限/)
  }
})

test('reselecting an already read assignment refreshes its permission', async () => {
  const ui = setup({ markAssignmentRead: async () => ({ assignment: allowed() }) })
  await ui.selectStudentAssignment(expired)
  assert.equal(ui.studentAssignments.value[0].makeup_allowed, true)
  assert.equal(ui.canSubmitRequirement({ ...expired, makeup_allowed: true }), true)
  assert.equal(ui.canSubmitRequirement({ ...allowed(), assignment_grade: { status: 'published' } }), false)
})

test('switching classes while the editor loads discards a late response', async () => {
  let resolve
  const ui = setup({ markAssignmentRead: async () => ({ assignment: allowed() }),
    openMarkdownDocument: () => new Promise(done => { resolve = done }) })
  const pending = ui.openSubmissionDialog(expired, expired.submission_requirements[0])
  await Promise.resolve(); await Promise.resolve()
  ui.selectedStudentClassId.value = 2
  resolve({ document: { id: 8, content: '# stale' } })
  await pending
  assert.equal(ui.markdownDialogVisible.value, false)
  assert.equal(ui.submissionOpening.value, false)
})
