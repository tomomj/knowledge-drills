import { describe, expect, it } from 'vitest'

import { parseMarkdownBlocks } from './markdown'

describe('parseMarkdownBlocks', () => {
  it('parses headings and paragraphs', () => {
    expect(parseMarkdownBlocks('# 教材\n\n## 方針\n根拠を確認します。\n判断を記録します。')).toEqual([
      { type: 'heading', level: 1, text: '教材' },
      { type: 'heading', level: 2, text: '方針' },
      { type: 'paragraph', text: '根拠を確認します。\n判断を記録します。' },
    ])
  })

  it('parses unordered and ordered lists', () => {
    expect(parseMarkdownBlocks('- 領収書\n- 上長確認\n\n1. 申請\n2. 承認')).toEqual([
      { type: 'list', ordered: false, items: ['領収書', '上長確認'] },
      { type: 'list', ordered: true, items: ['申請', '承認'] },
    ])
  })

  it('parses fenced code blocks without treating contents as markdown', () => {
    expect(parseMarkdownBlocks('```\n# not a heading\nline\n```')).toEqual([
      { type: 'code', text: '# not a heading\nline' },
    ])
  })

  it('splits a paragraph when a new block starts without a blank line', () => {
    expect(parseMarkdownBlocks('本文です。\n## 次の見出し')).toEqual([
      { type: 'paragraph', text: '本文です。' },
      { type: 'heading', level: 2, text: '次の見出し' },
    ])
  })

  it('handles empty input', () => {
    expect(parseMarkdownBlocks('')).toEqual([])
  })
})
