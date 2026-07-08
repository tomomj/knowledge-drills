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

export function AnalysisTimeline({ title, items }: AnalysisTimelineProps) {
  if (items.length === 0) {
    return null
  }

  const phases = groupTimelineItems(items)

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

                return (
                  <li key={item.id} className="analysis-timeline__item">
                    <div className="analysis-timeline__head">
                      <span className={`chip chip--${status.tone}`}>{status.label}</span>
                      <h4>{item.title}</h4>
                    </div>
                    {item.summary ? (
                      <p className="analysis-timeline__summary">{item.summary}</p>
                    ) : null}
                    {item.evidence.length > 0 ? (
                      <ul className="analysis-timeline__evidence">
                        {item.evidence.map((entry, index) => (
                          <li key={`${item.id}-${index}`}>{entry}</li>
                        ))}
                      </ul>
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
