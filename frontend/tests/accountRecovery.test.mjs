import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick, reactive } from 'vue'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const Module = require('node:module')
const renderer = createRenderer({
  createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  insert() {}, remove() {}, setElementText() {}, setText() {}, setComment() {}, patchProp() {},
  parentNode: () => null, nextSibling: () => null
})

function mountRecovery(api, mode = 'reset') {
  const filename = fileURLToPath(new URL('../src/components/AccountRecoveryDialog.vue', import.meta.url))
  const { descriptor } = parse(readFileSync(filename, 'utf8'))
  const script = compileScript(descriptor, { id: 'account-recovery-test' })
  const mod = new Module(filename)
  mod.paths = Module._nodeModulePaths(path.dirname(filename))
  const originalRequire = mod.require.bind(mod)
  mod.require = name => {
    if (name === '../api') return { api }
    if (name === 'element-plus') return { ElMessage: { error() {}, success() {}, warning() {} } }
    return originalRequire(name)
  }
  mod._compile(ts.transpileModule(script.content, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true
  } }).outputText, filename)
  const component = mod.exports.default
  component.render = () => null
  const events = []
  const props = reactive({ modelValue: true, mode })
  const app = renderer.createApp({ render: () => h(component, {
    ...props, 'onUpdate:modelValue': value => { props.modelValue = value },
    onReset: () => events.push('reset'), onBound: () => events.push('bound')
  }) })
  app.mount({})
  return { state: app._instance.subTree.component.setupState, props, events, destroy: () => app.unmount() }
}

for (const [role, identifier] of [['student', '测试学生'], ['teacher', 'teacher1'], ['admin', 'admin1']]) {
  test(`${role} recovery submits the same account identity when requesting and confirming`, async () => {
    const calls = []
    const ui = mountRecovery({
      requestPasswordReset: async payload => { calls.push(payload); return { message: '已申请' } },
      confirmPasswordReset: async payload => { calls.push(payload); return { message: '已重置' } }
    })
    try {
      ui.state.role = role
      ui.state.identifier = identifier
      ui.state.email = 'owner@example.test'
      await ui.state.sendCode()
      ui.state.code = 'email-code'
      ui.state.password = ui.state.confirmPassword = 'new-password'
      await ui.state.confirmRecovery()
      const identity = { email: 'owner@example.test', role, identifier }
      assert.deepEqual(calls, [identity, { ...identity, code: 'email-code', password: 'new-password' }])
      assert.deepEqual(ui.events, ['reset'])
    } finally { ui.destroy() }
  })
}

test('missing identity blocks recovery and editing the identity clears the old code', async () => {
  let requests = 0
  const ui = mountRecovery({ requestPasswordReset: async () => { requests++; return { message: '已申请' } } })
  try {
    ui.state.email = 'owner@example.test'
    await ui.state.sendCode()
    assert.equal(requests, 0)
    ui.state.identifier = 'Alice'
    await ui.state.sendCode()
    assert.equal(requests, 1)
    ui.state.code = 'old-code'
    ui.state.identifier = 'Bob'
    assert.equal(ui.state.code, '')
    ui.state.code = 'another-code'
    ui.state.role = 'teacher'
    assert.equal(ui.state.identifier, '')
    assert.equal(ui.state.code, '')
  } finally { ui.destroy() }
})

test('logged-in legacy users can verify their mailbox using the current password', async () => {
  const calls = []
  const ui = mountRecovery({
    requestEmailBinding: async (...args) => { calls.push(args); return { message: '已申请' } },
    confirmEmailBinding: async (...args) => { calls.push(args); return { message: '已绑定' } }
  }, 'bind')
  try {
    ui.state.email = 'owner@example.test'
    ui.state.password = 'current-password'
    await ui.state.sendCode()
    ui.state.code = 'binding-code'
    await ui.state.confirmRecovery()
    assert.deepEqual(calls, [['owner@example.test', 'current-password'], ['owner@example.test', 'binding-code']])
    assert.deepEqual(ui.events, ['bound'])
    await nextTick()
    assert.equal(ui.props.modelValue, false)
  } finally { ui.destroy() }
})
