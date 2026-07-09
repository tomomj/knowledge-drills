export type AnalysisStepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped'

export type AnalysisTimelineItemView = {
  id: string
  title: string
  status: AnalysisStepStatus
  summary: string | null
  evidence: string[]
  completedAt: string | null
}

type AnalysisTimelineProps = {
  title: string
  items: AnalysisTimelineItemView[]
  evidenceDisplay?: 'expanded' | 'collapsed'
}

type ChipTone = 'accent' | 'error' | 'muted' | 'success' | 'warning'

const STATUS_META: Record<AnalysisStepStatus, { label: string; tone: ChipTone }> = {
  pending: { label: '未開始', tone: 'muted' },
  running: { label: '実行中', tone: 'warning' },
  completed: { label: '完了', tone: 'success' },
  failed: { label: '失敗', tone: 'error' },
  skipped: { label: 'スキップ', tone: 'muted' },
}

type TimelinePhaseDefinition = {
  id: string
  title: string
  description: string
  itemIds: readonly string[]
}

type TimelinePhase = TimelinePhaseDefinition & {
  items: AnalysisTimelineItemView[]
}

const TIMELINE_PHASES: TimelinePhaseDefinition[] = [
  {
    id: 'input',
    title: '入力確認',
    description: '採点済み回答を集め、分析に使う材料を確認します。',
    itemIds: ['collect_answers'],
  },
  {
    id: 'pattern',
    title: 'つまずき分析',
    description: '回答と採点結果から、繰り返し出ている理解不足を抽出します。',
    itemIds: ['detect_failure_patterns'],
  },
  {
    id: 'evidence',
    title: '根拠レビュー',
    description: '教材本文と照合し、根拠の弱い所見を修正案から外します。',
    itemIds: ['match_course_evidence'],
  },
  {
    id: 'decision',
    title: '修正判断',
    description: '採用する所見を選び、資料への変更案と注意点をまとめます。',
    itemIds: ['decide_patch_strategy', 'create_patch'],
  },
]

const FALLBACK_PHASE: TimelinePhaseDefinition = {
  id: 'other',
  title: 'その他',
  description: '固定カテゴリにない補足的な分析ログです。',
  itemIds: [],
}

export function AnalysisTimeline({
  title,
  items,
  evidenceDisplay = 'expanded',
}: AnalysisTimelineProps) {
  if (items.length === 0) {
    return null
  }

  const phases = groupTimelineItems(items)
  const durations = elapsedDurations(items)

  return (
    <section className="analysis-timeline" aria-label={title}>
      <h2>{title}</h2>
      <div className="analysis-timeline__groups">
        {phases.map((phase) => (
          <div key={phase.id} className="analysis-timeline__group">
            <div className="analysis-timeline__group-head">
              <h3>{phase.title}</h3>
              <p>{phase.description}</p>
            </div>
            <ol className="analysis-timeline__list">
              {phase.items.map((item) => {
                const status = STATUS_META[item.status]
                const duration = durations.get(item.id)
                const canShowSummary = item.status !== 'pending' && Boolean(item.summary)
                const canShowEvidence =
                  item.status !== 'pending' &&
                  item.status !== 'running' &&
                  item.evidence.length > 0

                return (
                  <li
                    key={item.id}
                    className={`analysis-timeline__item analysis-timeline__item--${item.status}`}
                  >
                    <div className="analysis-timeline__head">
                      <span
                        className={`analysis-timeline__state analysis-timeline__state--${item.status}`}
                        aria-label={item.status === 'running' ? status.label : undefined}
                        aria-hidden={item.status === 'running' ? undefined : true}
                      >
                        {item.status === 'running' ? '' : statusIcon(item.status)}
                      </span>
                      <span className={`chip chip--${status.tone}`}>{status.label}</span>
                      <h4>{item.title}</h4>
                      {duration ? (
                        <span className="analysis-timeline__duration">{formatDuration(duration)}</span>
                      ) : null}
                    </div>
                    {canShowSummary ? (
                      <p className="analysis-timeline__summary">{item.summary}</p>
                    ) : null}
                    {canShowEvidence ? (
                      <EvidenceList item={item} evidenceDisplay={evidenceDisplay} />
                    ) : null}
                  </li>
                )
              })}
            </ol>
          </div>
        ))}
      </div>
    </section>
  )
}

type EvidenceListProps = {
  item: AnalysisTimelineItemView
  evidenceDisplay: 'expanded' | 'collapsed'
}

function EvidenceList({ item, evidenceDisplay }: EvidenceListProps) {
  const list = (
    <ul className="analysis-timeline__evidence">
      {item.evidence.map((entry, index) => (
        <li key={`${item.id}-${index}`}>{entry}</li>
      ))}
    </ul>
  )

  if (evidenceDisplay === 'expanded') {
    return list
  }

  return (
    <details className="analysis-timeline__evidence-details">
      <summary>根拠を表示</summary>
      {list}
    </details>
  )
}

function groupTimelineItems(items: AnalysisTimelineItemView[]): TimelinePhase[] {
  const phaseByItemId = new Map<string, TimelinePhaseDefinition>()
  for (const phase of TIMELINE_PHASES) {
    for (const itemId of phase.itemIds) {
      phaseByItemId.set(itemId, phase)
    }
  }

  const phases = new Map<string, TimelinePhase>(
    TIMELINE_PHASES.map((phase) => [phase.id, { ...phase, items: [] }]),
  )
  const fallback: TimelinePhase = { ...FALLBACK_PHASE, items: [] }

  for (const item of items) {
    const phase = phaseByItemId.get(item.id)
    const target = phase ? phases.get(phase.id) : fallback
    if (target) {
      target.items.push(item)
    }
  }

  const visiblePhases = Array.from(phases.values()).filter((phase) => phase.items.length > 0)
  if (fallback.items.length > 0) {
    visiblePhases.push(fallback)
  }
  return visiblePhases
}

function elapsedDurations(items: AnalysisTimelineItemView[]): Map<string, number> {
  const durations = new Map<string, number>()
  let previousCompletedAt: number | null = null

  for (const item of items) {
    if (item.status !== 'completed' || !item.completedAt) {
      continue
    }
    const completedAt = Date.parse(item.completedAt)
    if (Number.isNaN(completedAt)) {
      continue
    }
    if (previousCompletedAt !== null) {
      const elapsedSeconds = Math.max(0, Math.round((completedAt - previousCompletedAt) / 1000))
      durations.set(item.id, elapsedSeconds)
    }
    previousCompletedAt = completedAt
  }

  return durations
}

function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}秒`
  }
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (remainingSeconds === 0) {
    return `${minutes}分`
  }
  return `${minutes}分${remainingSeconds}秒`
}

function statusIcon(status: AnalysisStepStatus): string {
  if (status === 'completed') {
    return '✓'
  }
  if (status === 'failed') {
    return '!'
  }
  if (status === 'skipped') {
    return '-'
  }
  return ''
}
