import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { File } from 'node:buffer'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick, reactive } from 'vue'
import ts from 'typescript'

globalThis.File ??= File
const require = createRequire(import.meta.url)
const Module = require('node:module')
const renderer = createRenderer({
  createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  insert() {}, remove() {}, setElementText() {}, setText() {}, setComment() {}, patchProp() {},
  parentNode: () => null, nextSibling: () => null
})

function mountEditor(api, file = { id: 'notes-old', filename: 'notes.md', content: '# 原附件', purpose: '补充说明' }, extraProps = {}) {
  const filename = fileURLToPath(new URL('../src/components/MaterialEditor.vue', import.meta.url))
  const { descriptor } = parse(readFileSync(filename, 'utf8'))
  const script = compileScript(descriptor, { id: 'material-editor-test' })
  const code = ts.transpileModule(script.content, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true
  } }).outputText
  const errors = [], applied = []
  const mod = new Module(filename)
  mod.paths = Module._nodeModulePaths(path.dirname(filename))
  const originalRequire = mod.require.bind(mod)
  mod.require = name => {
    if (name === './MarkdownEditor.vue') return { render: () => null }
    if (name === '../api') return { api }
    if (name === 'element-plus') return { ElMessage: { error: value => errors.push(value) } }
    return originalRequire(name)
  }
  mod._compile(code, filename)
  const component = mod.exports.default
  component.render = () => null
  const props = reactive({ modelValue: true, file: Object.freeze(file), ...extraProps })
  const app = renderer.createApp({ render: () => h(component, {
    ...props, onApply: value => applied.push(value), 'onUpdate:modelValue': value => { props.modelValue = value }
  }) })
  app.mount({})
  const state = app._instance.subTree.component.setupState
  return { state, props, errors, applied, destroy: () => app.unmount() }
}

async function settle() { for (let i = 0; i < 8; i++) await nextTick() }

test('editing MD emits only the selected attachment with its purpose and renamed file', async () => {
  for (const purpose of ['', '补充说明']) {
    const source = { id: 'old', filename: 'notes.md', content: '# 原文', purpose }
    const calls = []
    const ui = mountEditor({ validateCodeTemplate: async file => {
      calls.push({ name: file.name, content: await file.text() })
      return { template: { id: 'new', filename: file.name, content: await file.text(), file_size: file.size, purpose: '补充说明' } }
    } }, source)
    try {
      assert.equal(ui.state.roleLabel, '附件')
      assert.match(ui.state.contextLabel, /notes\.md/)
      ui.state.content = '# 改好的附件'
      ui.state.filename = 'renamed.md'
      ui.state.purpose = '新用途'
      await ui.state.applyChanges()
      assert.deepEqual(calls, [{ name: 'renamed.md', content: '# 改好的附件' }])
      assert.equal(source.content, '# 原文')
      assert.equal(ui.applied.length, 1)
      assert.equal(ui.applied[0].originalId, 'old')
      assert.equal(ui.applied[0].file.id, 'new')
      assert.equal(ui.applied[0].file.purpose, '新用途')
      assert.equal(ui.props.modelValue, false)
    } finally { ui.destroy() }
  }
})

test('apply waits for editor uploads and captures the latest body, without duplicate requests', async () => {
  let release
  const calls = []
  const ui = mountEditor({ validateCodeTemplate: async file => {
    calls.push(await file.text()); return { template: { id: 'new', filename: file.name } }
  } })
  try {
    ui.state.editor = { flush: () => new Promise(resolve => { release = resolve }) }
    const applying = ui.state.applyChanges()
    await ui.state.applyChanges()
    assert.equal(calls.length, 0)
    ui.state.content = '# 附件\n![图](/api/assets/image/content)'
    release()
    await applying
    assert.deepEqual(calls, ['# 附件\n![图](/api/assets/image/content)'])
    assert.equal(ui.applied.length, 1)
  } finally { ui.destroy() }
})

test('cancel waits for pending uploads but never applies the changed material', async () => {
  let release
  const ui = mountEditor({ validateCodeTemplate: () => { throw new Error('unexpected validation') } })
  try {
    ui.state.content = '# 未应用'
    ui.state.editor = { flush: () => new Promise(resolve => { release = resolve }) }
    let closed = false
    const closing = ui.state.closeEditor(() => { closed = true; ui.props.modelValue = false })
    assert.equal(closed, false)
    release()
    await closing
    assert.equal(closed, true)
    assert.equal(ui.applied.length, 0)
    assert.equal(ui.props.file.content, '# 原附件')
  } finally { ui.destroy() }
})

test('closing during validation discards a late response', async () => {
  let release
  const ui = mountEditor({ validateCodeTemplate: async () => new Promise(resolve => { release = resolve }) })
  try {
    const applying = ui.state.applyChanges()
    await settle()
    ui.props.modelValue = false
    await settle()
    release({ template: { id: 'new', filename: 'notes.md', content: '# Late' } })
    await applying
    assert.equal(ui.applied.length, 0)
  } finally { ui.destroy() }
})

test('validation failures retain local content and keep the dialog open', async () => {
  const ui = mountEditor({ validateCodeTemplate: async () => { throw new Error('单个文件不能超过 1 MB') } })
  try {
    ui.state.content = '# 待修改正文'
    await ui.state.applyChanges()
    assert.equal(ui.state.content, '# 待修改正文')
    assert.equal(ui.props.modelValue, true)
    assert.equal(ui.state.saving, false)
    assert.equal(ui.applied.length, 0)
    assert.deepEqual(ui.errors, ['单个文件不能超过 1 MB'])
  } finally { ui.destroy() }
})

test('the Markdown editor does not edit a Python attachment', async () => {
  const ui = mountEditor({}, { id: 'py', filename: 'starter.py', content: '# TODO', purpose: '补充说明' })
  try {
    await ui.state.applyChanges()
    assert.equal(ui.applied.length, 0)
    assert.deepEqual(ui.errors, ['仅支持编辑 Markdown 文件'])
  } finally { ui.destroy() }
})

test('new Markdown validates its chosen filename and emits an append operation without changing the blank source', async () => {
  const source = { id: '', filename: '说明.md', content: '', file_size: 0, purpose: '实验资料' }
  const calls = []
  const ui = mountEditor({ validateCodeTemplate: async file => {
    calls.push({ filename: file.name, content: await file.text() })
    return { template: { id: 'created', filename: file.name, content: await file.text(), file_size: file.size } }
  } }, source)
  try {
    assert.equal(ui.state.creating, true)
    ui.state.filename = '实验说明'
    ui.state.content = '# 实验要求'
    await ui.state.applyChanges()
    assert.deepEqual(calls, [{ filename: '实验说明.md', content: '# 实验要求' }])
    assert.equal(ui.applied[0].originalId, '')
    assert.equal(ui.applied[0].file.purpose, '实验资料')
    assert.equal(source.content, '')
    assert.equal(ui.props.modelValue, false)
  } finally { ui.destroy() }
})

test('new Markdown rejects blank and duplicate names without overwriting an existing attachment', async () => {
  let calls = 0
  const ui = mountEditor({ validateCodeTemplate: () => { calls++; throw new Error('unexpected request') } },
    { id: '', filename: '附件.md', content: '', file_size: 0, purpose: '补充说明' },
    { existingNames: ['README.MD'] })
  try {
    ui.state.content = '# 不应覆盖'
    ui.state.filename = ' '
    await ui.state.applyChanges()
    ui.state.filename = 'readme'
    await ui.state.applyChanges()
    assert.equal(calls, 0)
    assert.equal(ui.applied.length, 0)
    assert.deepEqual(ui.errors, ['请填写文件名', '文件名已存在'])
    assert.equal(ui.props.modelValue, true)
    assert.equal(ui.state.content, '# 不应覆盖')
  } finally { ui.destroy() }
})
