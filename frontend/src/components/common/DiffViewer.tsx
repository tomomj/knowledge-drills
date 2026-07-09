import { countDiffLines } from '../../lib/diffStats'

type DiffViewerProps = {
  title: string
  diffText: string
  emptyText?: string
  versionLabel?: string
}

export function DiffViewer({
  title,
  diffText,
  emptyText = 'No changes',
  versionLabel,
}: DiffViewerProps) {
  const stats = countDiffLines(diffText)

  return (
    <section aria-label="Diff" className="diff-viewer">
      <div className="diff-viewer__head">
        <div className="diff-viewer__title">{title}</div>
        <div className="diff-viewer__meta">
          {versionLabel ? <span>{versionLabel}</span> : null}
          <span>
            +{stats.added} −{stats.removed}
          </span>
        </div>
      </div>
      <pre>
        {diffText
          ? diffText.split('\n').map((line, index) => (
              <span key={index} className={`diff-line${diffLineClass(line)}`}>
                {line || ' '}
              </span>
            ))
          : emptyText}
      </pre>
    </section>
  )
}

function diffLineClass(line: string): string {
  if (line.startsWith('+')) {
    return ' diff-line--add'
  }
  if (line.startsWith('-')) {
    return ' diff-line--del'
  }
  return ''
}
