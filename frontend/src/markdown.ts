import MarkdownIt from 'markdown-it'
import { full as markdownEmoji } from 'markdown-it-emoji'
import hljs from 'highlight.js'
import katex from 'katex'
import type { TextFormat } from './api'

export function renderFilePreview(content: string, filename: string): string {
  const body = content.replace(/^\uFEFF/, '')
  if (filename.toLowerCase().endsWith('.md')) return renderContent(body, 'markdown')
  const extension = filename.toLowerCase().split('.').pop() ?? ''
  const language = ({ py: 'python', c: 'c', cpp: 'cpp', cc: 'cpp' } as Record<string, string>)[extension] ?? ''
  const longest = (body.match(/`+/g) ?? []).reduce((maximum, run) => Math.max(maximum, run.length), 0)
  const fence = '`'.repeat(Math.max(3, longest + 1))
  return renderContent(`${fence}${language}\n${body}\n${fence}`, 'markdown')
}

const markdownRenderer = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  highlight(code, language) {
    const normalizedLanguage = language && hljs.getLanguage(language) ? language : ''
    if (normalizedLanguage) {
      return `<pre class="hljs"><code>${hljs.highlight(code, { language: normalizedLanguage, ignoreIllegals: true }).value}</code></pre>`
    }
    return `<pre class="hljs"><code>${escapeHtml(code)}</code></pre>`
  }
})

markdownRenderer.use(markdownEmoji)

const inlineMathDelimiters = new Map([['$', '$'], ['\\(', '\\)'], ['\\[', '\\]']])

// Parse math as Markdown tokens, so code and link destinations stay untouched.
// Backslash delimiters must be recognized before Markdown consumes the escape.
markdownRenderer.inline.ruler.before('escape', 'math_inline', (state, silent) => {
  const start = state.pos
  const opening = state.src[start] === '$' ? '$' : state.src.slice(start, start + 2)
  const closing = inlineMathDelimiters.get(opening)
  if (!closing) return false
  if (opening === '$' && (state.src[start + 1] === '$' || state.src[start - 1] === '$')) return false
  for (let end = start + opening.length; end < state.posMax; end++) {
    const character = state.src[end]
    if (character === '\n' && opening === '$') break
    if (end + closing.length <= state.posMax && state.src.startsWith(closing, end)) {
      const formula = state.src.slice(start + opening.length, end)
      if (!formula.trim()) return false
      if (!silent) {
        const token = state.push('math_inline', 'math', 0)
        token.content = formula
        token.markup = opening
      }
      state.pos = end + closing.length
      return true
    }
    if (character === '\\') { end++; continue }
  }
  return false
})

markdownRenderer.block.ruler.after('fence', 'math_block', (state, startLine, endLine, silent) => {
  if (state.sCount[startLine]! - state.blkIndent >= 4) return false
  const start = state.bMarks[startLine]! + state.tShift[startLine]!
  const opening = state.src.slice(start, start + 2)
  if (opening !== '$$' && opening !== '\\[') return false
  const closing = opening === '$$' ? '$$' : '\\]'
  for (let line = startLine; line < endLine; line++) {
    if (line > startLine && !state.isEmpty(line) && state.sCount[line]! < state.blkIndent) break
    const lineStart = state.bMarks[line]! + state.tShift[line]!
    const text = state.src.slice(lineStart, state.eMarks[line]).trimEnd()
    let closingPosition = text.indexOf(closing, line === startLine ? opening.length : 0)
    while (closingPosition !== -1 && isEscaped(text, closingPosition)) {
      closingPosition = text.indexOf(closing, closingPosition + closing.length)
    }
    if (closingPosition === -1) continue
    // Let the inline rule handle a formula followed by text or another formula.
    if (closingPosition + closing.length !== text.length) return false
    const formula = state.getLines(startLine, line + 1, state.blkIndent, false).trim().slice(2, -2)
    if (!formula.trim()) return false
    if (silent) return true
    const token = state.push('math_block', 'math', 0)
    token.content = formula
    token.markup = opening
    token.map = [startLine, line + 1]
    state.line = line + 1
    return true
  }
  return false
}, { alt: ['paragraph', 'reference', 'blockquote', 'list'] })

markdownRenderer.renderer.rules.math_inline = (tokens, index) => renderMath(tokens[index]!.content, tokens[index]!.markup === '\\[')
markdownRenderer.renderer.rules.math_block = (tokens, index) => `${renderMath(tokens[index]!.content, true)}\n`

markdownRenderer.renderer.rules.table_open = (tokens, index, options, _env, renderer) => {
  const headers: string[] = []
  for (let cursor = index + 1; cursor < tokens.length && tokens[cursor].type !== 'thead_close'; cursor++) {
    if (tokens[cursor].type === 'inline') headers.push(tokens[cursor].content)
  }
  // Recognize both current and historical feedback layouts, without constraining other tables.
  if (headers.length === 5 && headers.slice(0, 4).join('|') === '文件|提交文件|权重|得分/满分'
    && ['备注', '评语'].includes(headers[4]!)) tokens[index]!.attrJoin('class', 'feedback-file-table')
  return `<div class="markdown-table-scroll">${renderer.renderToken(tokens, index, options)}`
}
markdownRenderer.renderer.rules.table_close = () => '</table></div>\n'

export function renderContent(value: string | null, format: TextFormat) {
  const text = value || ''
  if (format !== 'markdown') {
    return escapeHtml(text).replace(/\n/g, '<br>')
  }
  return markdownRenderer.render(text)
}

function isEscaped(source: string, position: number): boolean {
  let backslashes = 0
  for (let index = position - 1; index >= 0 && source[index] === '\\'; index--) backslashes++
  return backslashes % 2 === 1
}

function renderMath(formula: string, displayMode: boolean) {
  try {
    return katex.renderToString(formula.trim(), { displayMode, throwOnError: false, strict: false })
  } catch {
    return `<code>${escapeHtml(formula)}</code>`
  }
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}
