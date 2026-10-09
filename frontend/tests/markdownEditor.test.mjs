import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick, reactive, ref } from 'vue'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const Module = require('node:module')
// Mount the actual script setup with Vue's custom renderer; no browser is needed.
const renderer = createRenderer({
  createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  insert() {}, remove() {}, setElementText() {}, setText() {}, setComment() {}, patchProp() {},
  parentNode: () => null, nextSibling: () => null
})

function mountEditor(api) {
  const filename = fileURLToPath(new URL('../src/components/MarkdownEditor.vue', import.meta.url))
  const { descriptor } = parse(readFileSync(filename, 'utf8'))
  const script = compileScript(descriptor, { id: 'markdown-editor-test' })
  const code = ts.transpileModule(script.content, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true } }).outputText
  const errors = []
  const mod = new Module(filename)
  mod.paths = Module._nodeModulePaths(path.dirname(filename))
  const originalRequire = mod.require.bind(mod)
  mod.require = name => {
    if (name === '../api') return { api }
    if (name === '../markdown') return { renderContent: value => value }
    if (name === '../reportTemplates') return { markdownText: value => value }
    if (name === 'element-plus') return { ElMessage: { error: value => errors.push(value), info() {} } }
    return originalRequire(name)
  }
  mod._compile(code, filename)
  const component = mod.exports.default
  component.render = () => null
  const state = reactive({ content: '初始正文' })
  const editor = ref()
  globalThis.window = { addEventListener() {}, removeEventListener() {} }
  const app = renderer.createApp({ render: () => h(component, {
    ref: editor, modelValue: state.content, documentId: 1, initialRevision: 0,
    'onUpdate:modelValue': value => { state.content = value }
  }) })
  app.mount({})
  return { state, editor, errors, destroy: () => app.unmount() }
}

async function settleUntil(predicate) {
  for (let attempt = 0; attempt < 20 && !predicate(); attempt++) await nextTick()
  assert.ok(predicate(), 'async operation did not start')
}

test('flush serializes autosaves and includes edits made during an in-flight save', async () => {
  const calls = []
  let release
  const ui = mountEditor({ saveMarkdownDocument: async (id, content, revision) => {
    calls.push({ content, revision })
    if (calls.length === 1) await new Promise(resolve => { release = resolve })
    return { document: { revision: revision + 1 } }
  } })
  try {
    ui.state.content = '第一版'
    await nextTick()
    const flushed = ui.editor.value.flush()
    await settleUntil(() => calls.length === 1)
    ui.state.content = '第二版'
    await nextTick()
    assert.equal(calls.length, 1)
    release()
    await flushed
    assert.deepEqual(calls, [{ content: '第一版', revision: 0 }, { content: '第二版', revision: 1 }])
  } finally { ui.destroy() }
})

test('revision conflict preserves local text and never silently retries an overwrite', async () => {
  let calls = 0
  const ui = mountEditor({ saveMarkdownDocument: async () => {
    calls++
    throw new Error('草稿已在其他窗口更新')
  } })
  try {
    ui.state.content = '我的未保存正文'
    await nextTick()
    await assert.rejects(ui.editor.value.flush(), /其他窗口/)
    await assert.rejects(ui.editor.value.flush(), /其他窗口/)
    assert.equal(calls, 1)
    assert.equal(ui.state.content, '我的未保存正文')
  } finally { ui.destroy() }
})

test('flush waits for an image upload, inserts its URL and then saves the final text', async () => {
  let release
  const saves = []
  const ui = mountEditor({
    uploadMarkdownImage: () => new Promise(resolve => { release = resolve }),
    saveMarkdownDocument: async (id, content, revision) => {
      saves.push(content)
      return { document: { revision: revision + 1 } }
    }
  })
  try {
    ui.editor.value.$.setupState.addImages([{ name: '截图.png' }])
    const flushed = ui.editor.value.flush()
    await settleUntil(() => !!release)
    ui.state.content = '上传时继续输入'
    await nextTick()
    release({ asset: { url: '/api/assets/abc/content' } })
    await flushed
    assert.equal(ui.state.content, '上传时继续输入![截图](/api/assets/abc/content)')
    assert.equal(saves.at(-1), ui.state.content)
  } finally { ui.destroy() }
})

test('failed image upload leaves the document intact and shows an error', async () => {
  const ui = mountEditor({ uploadMarkdownImage: async () => { throw new Error('图片损坏') } })
  try {
    ui.editor.value.$.setupState.addImages([{ name: '坏图.png' }])
    await ui.editor.value.flush()
    assert.equal(ui.state.content, '初始正文')
    assert.match(ui.errors[0], /图片上传失败.*图片损坏/)
  } finally { ui.destroy() }
})

test('file selection, clipboard images and dropped images share the insertion pipeline', async () => {
  let uploads = 0
  let prevented = 0
  const ui = mountEditor({
    uploadMarkdownImage: async () => ({ asset: { url: `/api/assets/${++uploads}/content` } }),
    saveMarkdownDocument: async (id, content, revision) => ({ document: { revision: revision + 1 } })
  })
  try {
    const actions = ui.editor.value.$.setupState
    const file = { name: '截图.png', type: 'image/png' }
    const input = { files: [file], value: 'selected' }
    actions.selectImages({ target: input })
    assert.equal(input.value, '')
    actions.pasteImages({ clipboardData: { items: [{ type: file.type, getAsFile: () => file }] }, preventDefault: () => prevented++ })
    actions.dropImages({ dataTransfer: { files: [file] }, preventDefault: () => prevented++ })
    await ui.editor.value.flush()
    assert.equal(uploads, 3)
    assert.equal(prevented, 2)
    assert.equal((ui.state.content.match(/!\[截图\]/g) || []).length, 3)
  } finally { ui.destroy() }
})

test('an image queued during a slow text save is included before flush completes', async () => {
  let release
  const saves = []
  const ui = mountEditor({
    uploadMarkdownImage: async () => ({ asset: { url: '/api/assets/new/content' } }),
    saveMarkdownDocument: async (id, content, revision) => {
      saves.push(content)
      if (saves.length === 1) await new Promise(resolve => { release = resolve })
      return { document: { revision: revision + 1 } }
    }
  })
  try {
    ui.state.content = '正文'
    await nextTick()
    const flushed = ui.editor.value.flush()
    await settleUntil(() => !!release)
    ui.editor.value.$.setupState.addImages([{ name: '后插入.png' }])
    release()
    await flushed
    assert.equal(saves.at(-1), '正文![后插入](/api/assets/new/content)')
  } finally { ui.destroy() }
})
