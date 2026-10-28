import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick, reactive, provide, inject } from 'vue'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const Module = require('node:module')
const renderer = createRenderer({
  createElement: tag => ({ tag, children: [], props: {} }), createText: text => ({ text }), createComment: text => ({ comment: text }),
  insert(node, parent, anchor) { parent.children ??= []; const index = parent.children.indexOf(anchor); parent.children.splice(index < 0 ? parent.children.length : index, 0, node); node.parent = parent },
  remove(node) { const list = node.parent?.children; if (list) list.splice(list.indexOf(node), 1) },
  setElementText(node, text) { node.text = text }, setText(node, text) { node.text = text }, setComment() {},
  patchProp(node, key, _old, value) { node.props[key] = value },
  parentNode: node => node.parent, nextSibling: () => null
})
const transpile = source => ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true
} }).outputText
const markdownFilename = fileURLToPath(new URL('../src/markdown.ts', import.meta.url))
const markdownModule = new Module(markdownFilename)
markdownModule.paths = Module._nodeModulePaths(path.dirname(markdownFilename))
markdownModule._compile(transpile(readFileSync(markdownFilename, 'utf8')), markdownFilename)

const previewMessages = []

function loadPreviewDialog() {
  const filename = fileURLToPath(new URL('../src/components/FilePreviewDialog.vue', import.meta.url))
  const { descriptor } = parse(readFileSync(filename, 'utf8'))
  const mod = new Module(filename)
  mod.paths = Module._nodeModulePaths(path.dirname(filename))
  const originalRequire = mod.require.bind(mod)
  mod.require = name => name === '../markdown' ? markdownModule.exports : name === 'element-plus' ? { ElMessage: { success: message => previewMessages.push({ type: 'success', message }), warning: message => previewMessages.push({ type: 'warning', message }) } } : originalRequire(name)
  const script = compileScript(descriptor, { id: 'preview-dialog-test' })
  mod._compile(transpile(script.content), filename)
  const template = compileTemplate({ source: descriptor.template.content, filename, id: 'preview-dialog-test', compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
  const renderModule = new Module(filename)
  renderModule.paths = mod.paths
  renderModule._compile(transpile(template.code), filename)
  mod.exports.default.render = renderModule.exports.render
  return mod.exports.default
}
const previewDialog = loadPreviewDialog()
const previewHtml = ui => ui.state.selectedFile ? markdownModule.exports.renderFilePreview(ui.state.content, ui.state.selectedFile.filename) : ''

function mountMaterials(api, files = [], renderTemplate = false, extraProps = {}) {
  const filename = fileURLToPath(new URL('../src/components/AssignmentMaterials.vue', import.meta.url))
  const { descriptor } = parse(readFileSync(filename, 'utf8'))
  const mod = new Module(filename)
  mod.paths = Module._nodeModulePaths(path.dirname(filename))
  const originalRequire = mod.require.bind(mod)
  mod.require = name => name === '../api' ? { api } : name === '../markdown' ? markdownModule.exports : name === './FilePreviewDialog.vue' ? (renderTemplate ? previewDialog : { render: () => null }) : originalRequire(name)
  const script = compileScript(descriptor, { id: 'materials-test' })
  mod._compile(transpile(script.content), filename)
  const component = mod.exports.default
  component.render = () => null
  if (renderTemplate) {
    const template = compileTemplate({ source: descriptor.template.content, filename, id: 'materials-test', compilerOptions: { bindingMetadata: script.bindings } })
    assert.deepEqual(template.errors, [])
    const renderModule = new Module(filename)
    renderModule.paths = mod.paths
    renderModule._compile(transpile(template.code), filename)
    component.render = renderModule.exports.render
  }
  const props = reactive({ assignmentId: 1, files, fallbackMarkdown: '# 在线说明', headerMarkdown: '# 作业信息', ...extraProps })
  const app = renderer.createApp({ render: () => h(component, props) })
  for (const name of ['el-tag', 'el-button', 'el-skeleton', 'el-alert', 'el-empty']) app.component(name, { setup: (_props, { slots }) => () => h('div', slots.default?.()) })
  app.component('el-dialog', { props: ['modelValue', 'title', 'width', 'appendToBody', 'destroyOnClose'], setup: (props, { slots }) => () => props.modelValue ? h('dialog', { title: props.title }, [slots.default?.(), slots.footer?.()]) : null })
  app.component('el-table', { props: ['data'], setup(props, { slots }) { provide('rows', () => props.data); return () => h('div', slots.default?.()) } })
  app.component('el-table-column', { props: ['prop', 'label', 'minWidth', 'width'], setup: (props, { slots }) => {
    const rows = inject('rows', () => [])
    return () => h('div', rows().map(row => slots.default ? slots.default({ row }) : h('span', String(row[props.prop] ?? ''))))
  } })
  const root = {}
  app.mount(root)
  const state = app._instance.subTree.component.setupState
  return { state, props, root, destroy: () => app.unmount() }
}

async function settle() { for (let i = 0; i < 8; i++) await nextTick() }
const md = { id: 'main', filename: 'README.md', purpose: '阅读资料' }
const py = { id: 'py', filename: 'starter.py', purpose: '代码框架' }

test('the independent description never fetches or selects an attachment by default', async () => {
  const calls = []
  const ui = mountMaterials({ previewCodeTemplate: async (assignmentId, id) => {
    calls.push({ assignmentId, id }); return { template: { ...md, content: '\uFEFF## 主文件正文' } }
  } }, [md, py])
  try {
    await settle()
    assert.deepEqual(calls, [])
    assert.equal(ui.state.selectedId, undefined)
    assert.equal(previewHtml(ui), '')
    assert.equal(ui.props.fallbackMarkdown, '# 在线说明')
    assert.equal(ui.state.loading, false)
  } finally { ui.destroy() }
})

test('legacy assignments keep their online description; staged MD and Python render safely without requests', async () => {
  const ui = mountMaterials({ previewCodeTemplate: () => { throw new Error('unexpected request') } })
  try {
    assert.equal(previewHtml(ui), '')
    const code = '```\n# fake heading\n<script>unsafe()</script>\nprint(1)'
    ui.props.files = [{ ...md, content: '# 主说明\n<script>unsafe()</script>' }, { ...py, content: code }]
    await settle()
    await ui.state.selectFile(ui.props.files[0])
    assert.match(previewHtml(ui), /<h1>主说明<\/h1>/)
    assert.doesNotMatch(previewHtml(ui), /<script>/)
    await ui.state.selectFile(ui.props.files[1])
    assert.match(previewHtml(ui), /class="hljs"/)
    assert.doesNotMatch(previewHtml(ui), /<script>|<h1>fake heading/)
    assert.match(previewHtml(ui), /fake heading/)
  } finally { ui.destroy() }
})

test('late responses never overwrite a more recently selected attachment', async () => {
  let release
  const ui = mountMaterials({ previewCodeTemplate: async (_assignmentId, id) => {
    if (id === 'main') return new Promise(resolve => { release = resolve })
    return { template: { ...py, content: 'print("current")' } }
  } }, [md, py])
  try {
    const pending = ui.state.selectFile(md)
    await ui.state.selectFile(py)
    release({ template: { ...md, content: '# 旧请求' } })
    await pending
    await settle()
    assert.equal(ui.state.selectedId, 'py')
    assert.match(ui.state.content, /current/)
    assert.doesNotMatch(previewHtml(ui), /旧请求/)
    assert.equal(ui.state.loading, false)
  } finally { ui.destroy() }
})

test('attachment actions share a row and preview opens a dialog while the main description remains in place', async () => {
  const ui = mountMaterials({}, [], true)
  const nodes = (root) => [root, ...(root.children ?? []).flatMap(nodes)]
  try {
    assert.deepEqual(nodes(ui.root).filter(node => node.tag === 'section').map(node => node.props['aria-label']), ['作业说明'])
    ui.props.files = [{ ...md, content: '# 附件正文' }]
    await settle()
    await ui.state.selectFile(ui.props.files[0])
    await settle()
    const cards = nodes(ui.root).filter(node => node.tag === 'section')
    assert.deepEqual(cards.map(node => node.props['aria-label']), ['作业说明', '作业附件'])
    assert.match(nodes(cards[0]).find(node => node.props?.innerHTML)?.props.innerHTML, /在线说明/)
    assert.equal(nodes(cards[1]).filter(node => node.props?.innerHTML).length, 0)
    const actions = nodes(cards[1]).find(node => node.props?.class?.includes('attachment-actions'))
    assert.equal(actions.children.length, 2)
    const dialog = nodes(ui.root).find(node => node.tag === 'dialog')
    assert.match(dialog.props.title, /README.md 在线预览/)
    assert.match(nodes(dialog).find(node => node.props?.innerHTML)?.props.innerHTML, /附件正文/)
    ui.state.previewDialogVisible = false
    await settle()
    assert.equal(nodes(ui.root).filter(node => node.tag === 'dialog').length, 0)
    assert.equal(ui.state.selectedId, undefined)
    ui.props.files = []
    await settle()
    assert.deepEqual(nodes(ui.root).filter(node => node.tag === 'section').map(node => node.props['aria-label']), ['作业说明'])
  } finally { ui.destroy() }
})

test('preview failures can retry and switching assignments clears the old contents', async () => {
  let attempts = 0
  const ui = mountMaterials({ previewCodeTemplate: async (assignmentId) => {
    if (++attempts === 1) throw new Error('文件已移除')
    return { template: { ...md, content: `# 作业 ${assignmentId}` } }
  } }, [md])
  try {
    await ui.state.selectFile(md)
    assert.equal(ui.state.error, '文件已移除')
    await ui.state.selectFile(md)
    assert.equal(ui.state.error, '')
    assert.match(previewHtml(ui), /作业 1/)
    ui.props.assignmentId = 2
    await settle()
    assert.equal(previewHtml(ui), '')
    assert.equal(ui.state.selectedId, undefined)
    await ui.state.selectFile(md)
    assert.match(previewHtml(ui), /作业 2/)
  } finally { ui.destroy() }
})

test('relative Markdown attachment links switch the viewer instead of navigating away', async () => {
  const ui = mountMaterials({}, [{ ...md, content: '# 主说明\n[框架](./starter.py)' }, { ...py, content: 'print(1)' }])
  const originalElement = globalThis.Element
  let prevented = false
  class LinkTarget { closest() { return { getAttribute: () => './starter.py' } } }
  globalThis.Element = LinkTarget
  try {
    await settle()
    ui.state.followAttachmentLink({ target: new LinkTarget(), preventDefault() { prevented = true } })
    await settle()
    assert.equal(prevented, true)
    assert.equal(ui.state.selectedId, 'py')
    assert.match(previewHtml(ui), /hljs/)
    await ui.state.showDefault()
    assert.equal(ui.state.selectedId, undefined)
    assert.equal(ui.props.fallbackMarkdown, '# 在线说明')
  } finally { ui.destroy(); globalThis.Element = originalElement }
})


test('closing an attachment preview cancels a pending request and does not reopen on its late response', async () => {
  let release
  const ui = mountMaterials({ previewCodeTemplate: () => new Promise(resolve => { release = resolve }) }, [md])
  try {
    const pending = ui.state.selectFile(md)
    assert.equal(ui.state.previewDialogVisible, true)
    ui.state.previewDialogVisible = false
    await settle()
    release({ template: { ...md, content: '# Late content' } })
    await pending
    assert.equal(ui.state.previewDialogVisible, false)
    assert.equal(ui.state.selectedId, undefined)
    assert.equal(ui.state.content, '')
  } finally { ui.destroy() }
})


test('teacher preview-only mode adds no duplicate list and opens a staged file in the shared dialog', async () => {
  const ui = mountMaterials({ previewCodeTemplate: () => { throw new Error('unexpected request') } },
    [{ ...py, content: 'print("staged")' }], true, { previewOnly: true })
  const nodes = root => [root, ...(root.children ?? []).flatMap(nodes)]
  try {
    assert.equal(nodes(ui.root).filter(node => node.tag === 'section').length, 0)
    await ui.state.selectFile(ui.props.files[0])
    await settle()
    assert.equal(nodes(ui.root).filter(node => node.tag === 'section').length, 0)
    const dialog = nodes(ui.root).find(node => node.tag === 'dialog')
    assert.match(dialog.props.title, /starter.py 在线预览/)
    assert.match(nodes(dialog).find(node => node.props?.innerHTML)?.props.innerHTML, /staged/)
  } finally { ui.destroy() }
})

test('downloads use the authorized URL for saved files and a filename-preserving Blob for staged files', async () => {
  const ui = mountMaterials({})
  const originalDocument = globalThis.document
  const create = URL.createObjectURL, revoke = URL.revokeObjectURL
  const clicks = [], blobs = [], revoked = []
  globalThis.document = { createElement: () => ({ click() { clicks.push({ href: this.href, filename: this.download }) } }) }
  URL.createObjectURL = blob => { blobs.push(blob); return 'blob:staged' }
  URL.revokeObjectURL = url => revoked.push(url)
  try {
    ui.state.downloadSelected({ ...py, url: '/api/assignments/1/code-templates/py/download' })
    ui.state.downloadSelected({ ...md, content: '# Staged Markdown' })
    assert.deepEqual(clicks, [
      { href: '/api/assignments/1/code-templates/py/download', filename: 'starter.py' },
      { href: 'blob:staged', filename: 'README.md' }
    ])
    assert.equal(await blobs[0].text(), '# Staged Markdown')
    assert.deepEqual(revoked, ['blob:staged'])
  } finally { globalThis.document = originalDocument; URL.createObjectURL = create; URL.revokeObjectURL = revoke; ui.destroy() }
})


const previewNodes = root => [root, ...(root.children ?? []).flatMap(previewNodes)]
const previewText = root => (root.text ?? '') + (root.children ?? []).map(previewText).join('')
const copyButton = root => previewNodes(root).find(node => node.tag === 'div' && previewText(node) === '复制内容')
function mockClipboard(writeText) {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { clipboard: { writeText } } })
  return () => { if (original) Object.defineProperty(globalThis, 'navigator', original); else delete globalThis.navigator }
}

test('copy content writes exact Python and Markdown sources including whitespace and BOM, never rendered HTML', async () => {
  const sources = ['\ufeffdef run():\r\n    return "<tag>"\r\n', '# Heading\n\n```python\nprint(1)\n```\n![图](/api/assets/image/content)\n']
  const files = [{ ...py, content: sources[0] }, { ...md, content: sources[1] }]
  const writes = []
  const restore = mockClipboard(async text => { writes.push(text) })
  const ui = mountMaterials({}, files, true)
  previewMessages.length = 0
  try {
    for (const file of files) {
      await ui.state.selectFile(file)
      await settle()
      const button = copyButton(ui.root)
      assert.equal(button.props.disabled, false)
      await button.props.onClick()
    }
    assert.deepEqual(writes, sources)
    assert.deepEqual(previewMessages.map(item => item.type), ['success', 'success'])
  } finally { restore(); ui.destroy() }
})

test('copy content is disabled while loading or after a failed preview and cannot write stale content', async () => {
  let reject
  const writes = []
  const restore = mockClipboard(async text => { writes.push(text) })
  const ui = mountMaterials({ previewCodeTemplate: () => new Promise((_resolve, fail) => { reject = fail }) }, [md], true)
  try {
    const pending = ui.state.selectFile(md)
    await settle()
    assert.equal(copyButton(ui.root).props.disabled, true)
    await copyButton(ui.root).props.onClick()
    reject(new Error('加载失败'))
    await pending
    await settle()
    assert.equal(copyButton(ui.root).props.disabled, true)
    await copyButton(ui.root).props.onClick()
    assert.deepEqual(writes, [])
  } finally { restore(); ui.destroy() }
})

test('clipboard rejection shows a short warning, prevents duplicate writes and enables retry', async () => {
  let reject, attempts = 0
  const restore = mockClipboard(() => { attempts++; return new Promise((_resolve, fail) => { reject = fail }) })
  const ui = mountMaterials({}, [{ ...py, content: 'print(1)' }], true)
  previewMessages.length = 0
  try {
    await ui.state.selectFile(ui.props.files[0])
    await settle()
    const button = copyButton(ui.root)
    const copying = button.props.onClick()
    await button.props.onClick()
    await settle()
    assert.equal(attempts, 1)
    assert.equal(copyButton(ui.root).props.disabled, true)
    reject(new Error('Permission denied'))
    await copying
    await settle()
    assert.deepEqual(previewMessages, [{ type: 'warning', message: '复制失败，请重试或下载文件' }])
    assert.equal(copyButton(ui.root).props.disabled, false)
  } finally { restore(); ui.destroy() }
})
