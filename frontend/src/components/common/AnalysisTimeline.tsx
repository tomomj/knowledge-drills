import type { AnalysisStepStatus, AnalysisTimelineItem } from '../../api/types'

type AnalysisTimelineProps = {
  title: string
  items: AnalysisTimelineItem[]
}

type ChipTone = 'accent' | 'error' | 'muted' | 'success' | 'warning'

const STATUS_META: Record<AnalysisStepStatus, { label: string; tone: ChipTone }> = {
  pending: { label: '未開始', tone: 'muted' },
  running: { label: '実行中', tone: 'warning' },
  completed: { label: '完了', tone: 'success' },
  failed: { label: '失敗', tone: 'error' },
  skipped: { label: 'スキップ', tone: 'muted' },
}

export function AnalysisTimeline({ title, items }: AnalysisTimelineProps) {
  if (items.length === 0) {
    return null
  }

  return (
    <section className="analysis-timeline" aria-label={title}>
      <h2>{title}</h2>
      <ol className="analysis-timeline__list">
        {items.map((item) => {
          const status = STATUS_META[item.status]
          const evidence = item.evidence.slice(0, 3)

          return (
            <li key={item.id} className="analysis-timeline__item">
              <div className="analysis-timeline__head">
                <span className={`chip chip--${status.tone}`}>{status.label}</span>
                <h3>{item.title}</h3>
              </div>
              {item.summary ? <p className="analysis-timeline__summary">{item.summary}</p> : null}
              {evidence.length > 0 ? (
                <ul className="analysis-timeline__evidence">
                  {evidence.map((entry, index) => (
                    <li key={`${item.id}-${index}`}>{entry}</li>
                  ))}
                </ul>
              ) : null}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
