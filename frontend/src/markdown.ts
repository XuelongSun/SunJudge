import MarkdownIt from 'markdown-it'
import { full as markdownEmoji } from 'markdown-it-emoji'
import hljs from 'highlight.js'
import katex from 'katex'
import type { TextFormat } from './api'

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
  const { source, tokens } = tokenizeMath(text)
  let html = markdownRenderer.render(source)
  tokens.forEach((token) => {
    html = html.split(token.placeholder).join(token.html)
  })
  return html
}

function tokenizeMath(text: string) {
  const tokens: Array<{ placeholder: string; html: string }> = []
  let source = text.replace(/(^|\n)\$\$([\s\S]+?)\$\$(?=\n|$)/g, (match, prefix: string, formula: string) => {
    const placeholder = `SUNJUDGE_MATH_BLOCK_${tokens.length}`
    tokens.push({ placeholder, html: renderMath(formula, true) })
    return `${prefix}${placeholder}`
  })
  source = source.replace(/\$([^$\n]+?)\$/g, (match, formula: string) => {
    const placeholder = `SUNJUDGE_MATH_INLINE_${tokens.length}`
    tokens.push({ placeholder, html: renderMath(formula, false) })
    return placeholder
  })
  return { source, tokens }
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
