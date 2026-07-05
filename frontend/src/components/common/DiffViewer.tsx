type DiffViewerProps = {
  title: string
  diffText: string
  emptyText?: string
}

export function DiffViewer({ title, diffText, emptyText = 'No changes' }: DiffViewerProps) {
  return (
    <section aria-label="Diff" className="diff-viewer">
      <div className="diff-viewer__title">{title}</div>
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
