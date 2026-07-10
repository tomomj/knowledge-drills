export type MarkdownBlock =
  | { type: 'heading'; level: number; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'code'; text: string }

const headingPattern = /^(#{1,6})\s+(.*)$/
const unorderedItemPattern = /^[-*+]\s+(.*)$/
const orderedItemPattern = /^\d+[.)]\s+(.*)$/

export function parseMarkdownBlocks(markdown: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = []
  const lines = markdown.split('\n')
  let index = 0

  while (index < lines.length) {
    const trimmed = lines[index].trim()
    if (!trimmed) {
      index += 1
      continue
    }

    if (trimmed.startsWith('```')) {
      const code: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        code.push(lines[index])
        index += 1
      }
      index += 1
      blocks.push({ type: 'code', text: code.join('\n') })
      continue
    }

    const heading = headingPattern.exec(trimmed)
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2].trim() })
      index += 1
      continue
    }

    const ordered = orderedItemPattern.test(trimmed)
    if (ordered || unorderedItemPattern.test(trimmed)) {
      const itemPattern = ordered ? orderedItemPattern : unorderedItemPattern
      const items: string[] = []
      while (index < lines.length) {
        const item = itemPattern.exec(lines[index].trim())
        if (!item) {
          break
        }
        items.push(item[1].trim())
        index += 1
      }
      blocks.push({ type: 'list', ordered, items })
      continue
    }

    const paragraph: string[] = [trimmed]
    index += 1
    while (index < lines.length) {
      const next = lines[index].trim()
      if (!next || isBlockStart(next)) {
        break
      }
      paragraph.push(next)
      index += 1
    }
    blocks.push({ type: 'paragraph', text: paragraph.join('\n') })
  }

  return blocks
}

function isBlockStart(line: string): boolean {
  return (
    line.startsWith('```') ||
    headingPattern.test(line) ||
    unorderedItemPattern.test(line) ||
    orderedItemPattern.test(line)
  )
}
