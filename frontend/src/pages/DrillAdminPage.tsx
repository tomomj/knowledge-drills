import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { api, ApiClientError } from '../api/client'
import type { DrillAdmin, DrillAnswer, DrillStatus } from '../api/types'
import { AppShell } from '../components/common/AppShell'
import { AnalysisTimeline } from '../components/common/AnalysisTimeline'
import { Breadcrumbs } from '../components/common/Breadcrumbs'
import { StatusBanner } from '../components/common/StatusBanner'

type PageState =
  | { status: 'loading' }
  | { status: 'ready'; drill: DrillAdmin }
  | { status: 'failed'; message: string }

type AnswersState =
  | { status: 'loading' }
  | { status: 'ready'; answers: DrillAnswer[] }
  | { status: 'failed'; message: string }

type AnalysisState =
  | { status: 'loading' }
  | { status: 'failed'; message: string }

const ANSWER_STATUS_CHIPS: Record<DrillAnswer['status'], { label: string; tone: string }> = {
  grading: { label: '採点中', tone: 'muted' },
  graded: { label: '採点済み', tone: 'success' },
  failed: { label: '採点失敗', tone: 'error' },
}

const DRILL_STATUS_CHIPS: Record<DrillStatus, { label: string; tone: string }> = {
  generating: { label: '生成中', tone: 'muted' },
  ready: { label: '生成完了', tone: 'success' },
  failed: { label: '生成失敗', tone: 'error' },
  analyzing: { label: '分析中', tone: 'accent' },
  analyzed: { label: '分析済み', tone: 'accent' },
}

export function DrillAdminPage() {
  const { courseId, drillRunId } = useParams()
  const navigate = useNavigate()
  const [state, setState] = useState<PageState>({ status: 'loading' })
  const [analysisState, setAnalysisState] = useState<AnalysisState | null>(null)
  const [answersState, setAnswersState] = useState<AnswersState>({ status: 'loading' })
  const [selectedAnswerId, setSelectedAnswerId] = useState<string | null>(null)
  const [answerQuery, setAnswerQuery] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let active = true
    async function load() {
      if (!courseId || !drillRunId) {
        setState({ status: 'failed', message: 'ドリル実行を識別できません。' })
        return
      }
      try {
        const drill = await api.getDrill(courseId, drillRunId)
        if (active) {
          setState({ status: 'ready', drill })
        }
      } catch (error) {
        if (active) {
          setState({ status: 'failed', message: errorMessage(error) })
        }
        return
      }
      try {
        const response = await api.getDrillAnswers(courseId, drillRunId)
        if (active) {
          setAnswersState({ status: 'ready', answers: response.answers })
        }
      } catch {
        if (active) {
          setAnswersState({ status: 'failed', message: '回答一覧の取得に失敗しました。' })
        }
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [courseId, drillRunId])

  useEffect(() => {
    if (analysisState?.status !== 'loading' || !courseId || !drillRunId) {
      return
    }

    let active = true
    const timer = window.setInterval(() => {
      void api
        .getDrill(courseId, drillRunId)
        .then((drill) => {
          if (active) {
            setState({ status: 'ready', drill })
          }
        })
        .catch(() => {
          // polling 中の一時失敗では最後に成功した timeline 表示を維持する
        })
    }, 1000)

    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [analysisState?.status, courseId, drillRunId])

  if (state.status === 'loading') {
    return (
      <AppShell>
        <main className="page">
          <StatusBanner tone="info">ドリルを読み込んでいます。</StatusBanner>
        </main>
      </AppShell>
    )
  }

  if (state.status === 'failed') {
    return (
      <AppShell>
        <main className="page">
          <StatusBanner tone="error">{state.message}</StatusBanner>
        </main>
      </AppShell>
    )
  }

  const { drill } = state
  const statusChip = DRILL_STATUS_CHIPS[drill.status]

  async function analyzeAnswers() {
    setAnalysisState({ status: 'loading' })
    try {
      const result = await api.analyzeDrill(drill.courseId, drill.id)
      navigate(
        `/courses/${drill.courseId}/drill-runs/${drill.id}/analysis?patchId=${result.patchId}`,
      )
    } catch (error) {
      setAnalysisState({ status: 'failed', message: analysisErrorMessage(error) })
    }
  }

  async function copyShareUrl() {
    if (!drill.shareUrl) {
      return
    }
    try {
      const absoluteUrl = new URL(drill.shareUrl, window.location.origin).toString()
      await navigator.clipboard.writeText(absoluteUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard 非対応環境では何もしない
    }
  }

  return (
    <AppShell>
      <main className="page">
        <section className="page-head" aria-labelledby="drill-admin-title">
          <div>
            <Breadcrumbs
              items={[
                { label: '講座一覧', to: '/courses' },
                { label: '講座管理', to: `/courses/${drill.courseId}` },
                { label: 'ドリル確認' },
              ]}
            />
            <h1 id="drill-admin-title">ドリル確認</h1>
            <p className="page-head__sub">
              生成された問題とルーブリックを確認し、共有 URL を配布します。
            </p>
          </div>
          <div className="toolbar">
            <button
              type="button"
              className="btn btn--primary"
              onClick={analyzeAnswers}
              disabled={!drill.canAnalyze || analysisState?.status === 'loading'}
            >
              回答を分析する
            </button>
          </div>
        </section>

        {drill.status === 'failed' ? (
          <StatusBanner tone="error">
            ドリル生成に失敗しました。{drill.errorMessage ?? ''}
          </StatusBanner>
        ) : null}
        {analysisState?.status === 'loading' ? (
          <StatusBanner tone="info">回答を分析中です。</StatusBanner>
        ) : null}
        {analysisState?.status === 'failed' && analysisState.message ? (
          <StatusBanner tone="error">{analysisState.message}</StatusBanner>
        ) : null}

        <section className="stat-row" aria-label="ドリルの状態">
          <div className="stat">
            <div className="stat__label">Status</div>
            <div className="stat__value">
              <span className={`chip chip--${statusChip.tone}`}>{statusChip.label}</span>
            </div>
          </div>
          <div className="stat">
            <div className="stat__label">資料バージョン</div>
            <div className="stat__value">v{drill.courseVersion}</div>
          </div>
          <div className="stat">
            <div className="stat__label">回答数</div>
            <div className="stat__value">
              {drill.answerCount}
              <span className="stat__unit">件</span>
            </div>
          </div>
          <div className="stat">
            <div className="stat__label">分析</div>
            <div className="stat__value">
              {drill.canAnalyze ? (
                <span className="chip chip--accent">実行可能</span>
              ) : (
                <span className="chip chip--muted">回答待ち</span>
              )}
            </div>
          </div>
        </section>

        <ScoreSummaryPanel drill={drill} />

        <AnalysisTimeline title="分析タイムライン" items={drill.analysisTimeline} />

        <div className="card">
          <div className="card__body share-row">
            <span className="share-row__label">共有 URL</span>
            <code>{drill.shareUrl ?? '-'}</code>
            <button
              type="button"
              className="tag-btn"
              onClick={copyShareUrl}
              disabled={!drill.shareUrl}
            >
              {copied ? 'コピーしました' : 'コピー'}
            </button>
            {drill.shareUrl ? (
              <a className="tag-btn" href={drill.shareUrl} target="_blank" rel="noreferrer">
                プレビュー
              </a>
            ) : null}
          </div>
        </div>

        <section className="question-stack">
          {drill.questions.map((question) => (
            <article className="card q-card" key={question.id}>
              <div className="q-main">
                <span className="q-num">{question.id}</span>
                <h2>{question.question}</h2>
                <p className="q-intent">
                  <b>出題意図</b>
                  {question.intent}
                </p>
              </div>
              <div className="q-rubric">
                <h3>ルーブリック</h3>
                <dl className="rubric-list">
                  {question.rubric.map((item) => (
                    <div key={item.criterion}>
                      <dt>{item.criterion}</dt>
                      <dd>{item.points} pts</dd>
                    </div>
                  ))}
                </dl>
              </div>
              <div className="q-answer-guide">
                <div className="q-answer-guide__block">
                  <h3>模範解答</h3>
                  <p>{question.idealAnswer}</p>
                </div>
                <div className="q-answer-guide__block">
                  <h3>教材の根拠</h3>
                  <ul>
                    {question.sourceEvidence.map((evidence) => (
                      <li key={`${evidence.sectionHeading}:${evidence.excerpt}`}>
                        <b>{evidence.sectionHeading}</b>
                        <span>{evidence.excerpt}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </article>
          ))}
        </section>

        <section style={{ display: 'grid', gap: 14 }} aria-label="回答一覧">
          <h2 className="section-title">回答一覧</h2>
          {answersState.status === 'loading' ? (
            <StatusBanner tone="info">回答を読み込んでいます。</StatusBanner>
          ) : null}
          {answersState.status === 'failed' ? (
            <StatusBanner tone="error">{answersState.message}</StatusBanner>
          ) : null}
          {answersState.status === 'ready' && answersState.answers.length === 0 ? (
            <StatusBanner tone="info">
              まだ回答がありません。共有 URL を受講者に配布しましょう。
            </StatusBanner>
          ) : null}
          {answersState.status === 'ready' && answersState.answers.length > 0 ? (
            <AnswerBrowser
              answers={answersState.answers}
              questions={drill.questions}
              query={answerQuery}
              onQueryChange={setAnswerQuery}
              selectedAnswerId={selectedAnswerId}
              onSelect={setSelectedAnswerId}
            />
          ) : null}
        </section>
      </main>
    </AppShell>
  )
}

type ScoreSummaryPanelProps = {
  drill: DrillAdmin
}

function ScoreSummaryPanel({ drill }: ScoreSummaryPanelProps) {
  const summary = drill.scoreSummary
  const gradedAnswerCount = summary?.gradedAnswerCount ?? 0
  const maxScore = summary?.maxScore ?? totalMaxScore(drill)

  return (
    <section className="card score-summary" aria-labelledby="score-summary-title">
      <div className="card__head">
        <h2 id="score-summary-title">分析前の採点状況</h2>
      </div>
      <div className="card__body score-summary__body">
        <dl className="score-summary__stats">
          <div>
            <dt>出題観点</dt>
            <dd>{drill.drillFocus ?? '未設定'}</dd>
          </div>
          <div>
            <dt>採点済み回答</dt>
            <dd>{gradedAnswerCount} 件</dd>
          </div>
          <div>
            <dt>平均点</dt>
            <dd>
              {formatScore(summary?.averageScore ?? null)} / {maxScore} 点
            </dd>
          </div>
        </dl>

        {gradedAnswerCount === 0 ? (
          <StatusBanner tone="info">採点済み回答がまだありません</StatusBanner>
        ) : null}

        {summary && summary.questions.length > 0 && gradedAnswerCount > 0 ? (
          <ul className="score-summary__questions" aria-label="設問別の採点状況">
            {summary.questions.map((question) => {
              const tags = [
                ...question.commonMissingPoints.map((point) => ({
                  label: '欠落',
                  value: point,
                })),
                ...question.failureTags.map((tag) => ({ label: 'タグ', value: tag })),
              ]

              return (
                <li key={question.questionId}>
                  <div className="score-summary__question-head">
                    <span className="q-num">{question.questionId}</span>
                    <span>
                      {formatScore(question.averageScore)} / {question.maxScore} 点
                    </span>
                    <span>{question.gradedAnswerCount} 件</span>
                  </div>
                  {tags.length > 0 ? (
                    <div className="score-summary__tags">
                      {tags.map((tag) => (
                        <span key={`${question.questionId}-${tag.label}-${tag.value}`}>
                          {tag.label}: {tag.value}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </li>
              )
            })}
          </ul>
        ) : null}
      </div>
    </section>
  )
}

type AnswerBrowserProps = {
  answers: DrillAnswer[]
  questions: DrillAdmin['questions']
  query: string
  onQueryChange: (value: string) => void
  selectedAnswerId: string | null
  onSelect: (id: string) => void
}

function AnswerBrowser({
  answers,
  questions,
  query,
  onQueryChange,
  selectedAnswerId,
  onSelect,
}: AnswerBrowserProps) {
  const trimmed = query.trim()
  const filtered = trimmed
    ? answers.filter((answer) => answer.learnerName.includes(trimmed))
    : answers
  const selected =
    filtered.find((answer) => answer.id === selectedAnswerId) ?? filtered[0] ?? null

  return (
    <>
      <div className="list-toolbar">
        <input
          type="search"
          placeholder="回答者名で検索…"
          aria-label="回答者名で検索"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
        />
        <span className="list-count">
          {filtered.length} / {answers.length} 件
        </span>
      </div>

      {filtered.length === 0 ? (
        <StatusBanner tone="info">「{trimmed}」に一致する回答者はいません。</StatusBanner>
      ) : (
        <div className="answers-grid">
          <div className="card select-list" aria-label="回答者一覧">
            {filtered.map((answer) => (
              <button
                type="button"
                key={answer.id}
                className={`select-row${answer.id === selected?.id ? ' select-row--selected' : ''}`}
                onClick={() => onSelect(answer.id)}
                aria-pressed={answer.id === selected?.id}
              >
                <span className="select-row__label">{answer.learnerName}</span>
                <span className="select-row__meta">
                  {answer.status === 'graded' &&
                  answer.totalScore !== null &&
                  answer.maxScore !== null
                    ? `${answer.totalScore} / ${answer.maxScore} 点`
                    : ANSWER_STATUS_CHIPS[answer.status].label}
                </span>
              </button>
            ))}
          </div>

          {selected ? (
            <article className="card ans" aria-label={`${selected.learnerName} の回答`}>
              <div className="ans__head">
                <span className="ans__name">{selected.learnerName}</span>
                <span className={`chip chip--${ANSWER_STATUS_CHIPS[selected.status].tone}`}>
                  {ANSWER_STATUS_CHIPS[selected.status].label}
                </span>
                {selected.totalScore !== null && selected.maxScore !== null ? (
                  <span className="ans__score">
                    {selected.totalScore} / {selected.maxScore} 点
                  </span>
                ) : null}
              </div>
              {questions.map((question) => {
                const answerText = selected.answers[question.id]
                const grading = selected.gradingResults.find(
                  (result) => result.questionId === question.id,
                )
                return (
                  <div className="ans__qa" key={question.id}>
                    <p className="ans__q">
                      <span className="q-num">{question.id}</span>
                      {question.question}
                    </p>
                    <p className="ans__a">{answerText ?? '-'}</p>
                    {grading ? (
                      <p className="ans__fb">
                        <b>
                          {grading.score} / {grading.maxScore} 点
                        </b>
                        {grading.feedback}
                      </p>
                    ) : null}
                  </div>
                )
              })}
            </article>
          ) : null}
        </div>
      )}
    </>
  )
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    return error.error.message
  }
  return 'ドリルの取得に失敗しました。'
}

function analysisErrorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.error.code === 'no_graded_answers') {
      return '採点済み回答がありません。回答後に再試行してください。'
    }
    if (error.error.code === 'drill_not_analyzable') {
      return 'このドリルは分析できない状態です。'
    }
    return error.error.message
  }
  return '分析に失敗しました。再試行してください。'
}

function formatScore(value: number | null): string {
  return value === null ? '未計測' : value.toFixed(1)
}

function totalMaxScore(drill: DrillAdmin): number {
  return drill.questions.reduce((total, question) => total + question.maxScore, 0)
}
