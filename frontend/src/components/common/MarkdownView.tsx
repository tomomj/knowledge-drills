import { parseMarkdownBlocks } from '../../lib/markdown'

type MarkdownViewProps = {
  markdown: string
}

type HeadingTag = 'h3' | 'h4' | 'h5' | 'h6'

function headingTag(level: number): HeadingTag {
  return `h${Math.min(level + 2, 6)}` as HeadingTag
}

export function MarkdownView({ markdown }: MarkdownViewProps) {
  const blocks = parseMarkdownBlocks(markdown)
  return (
    <div className="markdown-view">
      {blocks.map((block, index) => {
        const key = `${block.type}-${index}`
        if (block.type === 'heading') {
          const Tag = headingTag(block.level)
          return <Tag key={key}>{block.text}</Tag>
        }
        if (block.type === 'list') {
          const ListTag = block.ordered ? 'ol' : 'ul'
          return (
            <ListTag key={key}>
              {block.items.map((item, itemIndex) => (
                <li key={`${item}-${itemIndex}`}>{item}</li>
              ))}
            </ListTag>
          )
        }
        if (block.type === 'code') {
          return (
            <pre key={key}>
              <code>{block.text}</code>
            </pre>
          )
        }
        return <p key={key}>{block.text}</p>
      })}
    </div>
  )
}
