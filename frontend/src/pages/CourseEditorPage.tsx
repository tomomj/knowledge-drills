import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { api, ApiClientError } from '../api/client'
import type { CourseDetail, CourseMetricsResponse, CourseMetricsRun } from '../api/types'
import { AppShell } from '../components/common/AppShell'
import { Breadcrumbs } from '../components/common/Breadcrumbs'
import { StatusBanner } from '../components/common/StatusBanner'

const MARKDOWN_LIMIT = 20_000
const DRILL_FOCUS_LIMIT = 500

type PageState =
  | { status: 'idle' }
  | { status: 'saving' }
  | { status: 'generating' }
  | { status: 'deleting' }
  | { status: 'ready'; message: string }
  | { status: 'failed'; message: string }

export function CourseEditorPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { courseId } = useParams()
  const [title, setTitle] = useState('')
  const [markdown, setMarkdown] = useState('')
  const [drillFocus, setDrillFocus] = useState('')
  const [course, setCourse] = useState<CourseDetail | null>(null)
  const [metrics, setMetrics] = useState<CourseMetricsResponse | null>(null)
  const [state, setState] = useState<PageState>({ status: 'idle' })
  const [deleteConfirming, setDeleteConfirming] = useState(false)

  useEffect(() => {
    let active = true
    async function loadCourse() {
      if (!courseId) {
        setCourse(null)
        setTitle('')
        setMarkdown('')
        setDrillFocus('')
        setMetrics(null)
        setDeleteConfirming(false)
        setState({ status: 'idle' })
        return
      }
      setMetrics(null)
      setState({ status: 'saving' })
      try {
        const [loaded, loadedMetrics] = await Promise.all([
          api.getCourse(courseId),
          loadCourseMetrics(courseId),
        ])
        if (active) {
          setCourse(loaded)
          setMetrics(loadedMetrics)
          setTitle(loaded.title)
          setMarkdown(loaded.markdown)
          setDrillFocus(loaded.drillFocus ?? '')
          setDeleteConfirming(false)
          const saveMessage = saveMessageFromLocationState(location.state)
          setState(saveMessage ? { status: 'ready', message: saveMessage } : { status: 'idle' })
        }
      } catch (error) {
        if (active) {
          setState({ status: 'failed', message: errorMessage(error) })
        }
      }
    }
    void loadCourse()
    return () => {
      active = false
    }
  }, [courseId, location.state])

  const validationError = validateCourse(title, markdown, drillFocus)
  const scoreProgression = buildScoreProgression(metrics)
  const latestRun = metrics?.runs.find((run) => run.drillRunId === course?.latestDrillRunId)
  const hasCurrentVersionDrill = Boolean(
    course?.latestDrillRunId &&
      (metrics === null || latestRun?.courseVersion === course.version),
  )

  async function saveCourse() {
    if (validationError) {
      setState({ status: 'failed', message: validationError })
      return
    }
    setState({ status: 'saving' })
    try {
      const saved = course
        ? await api.updateCourse(course.id, { title, markdown, drillFocus })
        : await api.createCourse({ title, markdown, drillFocus }).then((created) =>
            api.getCourse(created.courseId),
          )
      setCourse(saved)
      setTitle(saved.title)
      setMarkdown(saved.markdown)
      setDrillFocus(saved.drillFocus ?? '')
      setState({ status: 'ready', message: '保存しました。' })
      if (!course) {
        navigate(`/courses/${saved.id}`, {
          replace: true,
          state: { saveMessage: '保存しました。' },
        })
      }
    } catch (error) {
      setState({ status: 'failed', message: errorMessage(error) })
    }
  }

  async function generateDrill() {
    if (!course) {
      setState({ status: 'failed', message: '先に講座を保存してください。' })
      return
    }
    setState({ status: 'generating' })
    try {
      const drill = await api.generateDrill(course.id)
      setCourse({ ...course, latestDrillRunId: drill.drillRunId })
      setState({ status: 'ready', message: 'ドリルを生成しました。' })
      navigate(`/courses/${course.id}/drill-runs/${drill.drillRunId}`)
    } catch (error) {
      setState({ status: 'failed', message: errorMessage(error) })
    }
  }

  async function deleteCourse() {
    if (!course) {
      setState({ status: 'failed', message: '削除する講座がありません。' })
      return
    }
    if (!deleteConfirming) {
      setDeleteConfirming(true)
      return
    }
    setState({ status: 'deleting' })
    try {
      await api.deleteCourse(course.id)
      navigate('/courses')
    } catch (error) {
      setState({ status: 'failed', message: errorMessage(error) })
    }
  }

  return (
    <AppShell>
      <main className="page">
        <section className="page-head" aria-labelledby="course-editor-title">
          <div>
            <Breadcrumbs
              items={[
                { label: '講座一覧', to: '/courses' },
                { label: course ? course.title : '新しい講座' },
              ]}
            />
            <h1 id="course-editor-title">講座管理</h1>
            <p className="page-head__sub">社内資料を登録すると、AI が確認ドリルを生成します。</p>
          </div>
          <div className="toolbar">
            <button
              type="button"
              className="btn btn--secondary"
              onClick={generateDrill}
              disabled={!course || state.status === 'generating' || state.status === 'deleting'}
            >
              ドリルを生成
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={saveCourse}
              disabled={state.status === 'saving' || state.status === 'deleting'}
            >
              保存する
            </button>
          </div>
        </section>

        <StatusBanner tone="warning">
          MVP 検証では本物の機密社内資料を入力しないでください。
        </StatusBanner>

        {state.status === 'saving' ? <StatusBanner tone="info">保存中です。</StatusBanner> : null}
        {state.status === 'generating' ? (
          <StatusBanner tone="info">ドリルを生成中です。</StatusBanner>
        ) : null}
        {state.status === 'deleting' ? <StatusBanner tone="info">削除中です。</StatusBanner> : null}
        {state.status === 'ready' ? (
          <StatusBanner tone="success">{state.message}</StatusBanner>
        ) : null}
        {state.status === 'failed' ? (
          <StatusBanner tone="error">{state.message}</StatusBanner>
        ) : null}

        <section className="editor-grid">
          <div className="card">
            <div className="card__body" style={{ display: 'grid', gap: 18 }}>
              <label className="field">
                <span className="field__label">講座タイトル</span>
                <input value={title} onChange={(event) => setTitle(event.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">
                  教材 Markdown
                  <span className="field__hint">
                    {markdown.length.toLocaleString()} / {MARKDOWN_LIMIT.toLocaleString()} 文字
                  </span>
                </span>
                <textarea
                  className="editor-md"
                  value={markdown}
                  onChange={(event) => setMarkdown(event.target.value)}
                />
              </label>
              <label className="field">
                <span className="field__label">
                  出題観点
                  <span className="field__hint">
                    任意・{drillFocus.length.toLocaleString()} /{' '}
                    {DRILL_FOCUS_LIMIT.toLocaleString()} 文字
                  </span>
                </span>
                <textarea
                  className="editor-md editor-md--compact"
                  value={drillFocus}
                  placeholder="例: 例外条件や判断理由を重点的に確認"
                  onChange={(event) => setDrillFocus(event.target.value)}
                />
              </label>
            </div>
          </div>

          <aside className="editor-side" aria-label="講座の状態">
            <div className="card">
              <div className="card__head">
                <h2>講座の状態</h2>
                {course ? (
                  <span className="chip chip--success">保存済み</span>
                ) : (
                  <span className="chip chip--muted">未保存</span>
                )}
              </div>
              <div className="card__body" style={{ paddingTop: 8, paddingBottom: 8 }}>
                <dl className="side-list">
                  <div>
                    <dt>バージョン</dt>
                    <dd>{course ? `v${course.version}` : '-'}</dd>
                  </div>
                  <div>
                    <dt>更新履歴</dt>
                    <dd>
                      {course ? (
                        <Link className="side-link" to={`/courses/${course.id}/history`}>
                          差分を見る →
                        </Link>
                      ) : (
                        '-'
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>最新ドリル</dt>
                    <dd>
                      {course?.latestDrillRunId && hasCurrentVersionDrill ? (
                        <Link
                          className="side-link"
                          to={`/courses/${course.id}/drill-runs/${course.latestDrillRunId}?view=drill`}
                        >
                          確認する →
                        </Link>
                      ) : course ? (
                        '未生成'
                      ) : (
                        '-'
                      )}
                    </dd>
                  </div>
                  <div
                    className={
                      course?.latestPatchStatus === 'proposed' ? 'side-list__review' : undefined
                    }
                  >
                    <dt>
                      {course?.latestPatchStatus === 'proposed' ? (
                        <span className="side-list__label-stack">
                          <span>✦ AIの改善案</span>
                          <small>人の承認後に教材へ反映</small>
                        </span>
                      ) : (
                        '改善履歴'
                      )}
                    </dt>
                    <dd>
                      {course?.latestPatchId ? (
                        <Link
                          className={`side-link${
                            course.latestPatchStatus === 'proposed' ? ' side-link--review' : ''
                          }`}
                          to={`/patches/${course.latestPatchId}`}
                        >
                          {course.latestPatchStatus === 'proposed'
                            ? '人が確認する →'
                            : '内容を見る →'}
                        </Link>
                      ) : (
                        '-'
                      )}
                    </dd>
                  </div>
                </dl>
                {course ? (
                  <div className="danger-zone">
                    <button
                      type="button"
                      className="btn btn--danger"
                      onClick={deleteCourse}
                      disabled={state.status === 'deleting'}
                    >
                      {deleteConfirming ? '本当に削除する' : '講座を削除'}
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
            {scoreProgression ? <ScoreProgressionCard progression={scoreProgression} /> : null}
            <div className="next-step">
              <b>次のステップ</b>
              資料を保存したら「ドリルを生成」で確認テストを作成し、共有 URL を受講者に配布します。
            </div>
          </aside>
        </section>
      </main>
    </AppShell>
  )
}

type ScoredMetricsRun = CourseMetricsRun & {
  averageScore: number
  maxScore: number
}

type ScoreProgression = {
  runs: ScoredMetricsRun[]
  stepIndexes: number[]
  omittedCount: number
  uniformMaxScore: boolean
}

const SPARKLINE_WIDTH = 180
const SPARKLINE_HEIGHT = 64
const SPARKLINE_PADDING = 8
const MAX_VISIBLE_STEPS = 4

function ScoreProgressionCard({ progression }: { progression: ScoreProgression }) {
  const { runs, stepIndexes, omittedCount, uniformMaxScore } = progression
  const first = runs[0]
  const last = runs[runs.length - 1]
  const improved = scoreRate(last) >= scoreRate(first)
  const summary = uniformMaxScore
    ? `平均 ${formatMetricScore(first.averageScore)} → ${formatMetricScore(last.averageScore)} 点`
    : `スコア率 ${formatRatePercent(first)} → ${formatRatePercent(last)}`
  return (
    <article className="card metrics-card" aria-label="改善メトリクス">
      <div className="card__head">
        <h2>スコアの推移</h2>
        <span className={`chip chip--${improved ? 'success' : 'warning'}`}>{summary}</span>
      </div>
      <div className="card__body metrics-card__body">
        <ScoreSparkline runs={runs} />
        <div className="metrics-flow">
          {stepIndexes.map((runIndex, position) => {
            const run = runs[runIndex]
            const nextRunIndex = stepIndexes[position + 1]
            const nextRun = nextRunIndex !== undefined ? runs[nextRunIndex] : null
            const intervalDelta =
              nextRun && nextRunIndex === runIndex + 1 && nextRun.maxScore === run.maxScore
                ? nextRun.averageScore - run.averageScore
                : null
            const showsOmission = position === 0 && omittedCount > 0
            return (
              <div className="metrics-flow__segment" key={`${run.drillRunId}-${runIndex}`}>
                <MetricRunStep run={run} />
                {intervalDelta !== null ? (
                  <span
                    className={`metrics-flow__delta metrics-flow__delta--${
                      intervalDelta >= 0 ? 'up' : 'down'
                    }`}
                  >
                    {formatScoreDelta(intervalDelta)}
                  </span>
                ) : null}
                {showsOmission ? (
                  <span className="metrics-flow__skip">… {omittedCount} 版省略</span>
                ) : null}
              </div>
            )
          })}
        </div>
      </div>
    </article>
  )
}

function ScoreSparkline({ runs }: { runs: ScoredMetricsRun[] }) {
  const points = runs.map((run, index) => {
    const x =
      runs.length === 1
        ? SPARKLINE_WIDTH / 2
        : SPARKLINE_PADDING +
          (index * (SPARKLINE_WIDTH - SPARKLINE_PADDING * 2)) / (runs.length - 1)
    const clampedRate = Math.max(0, Math.min(1, scoreRate(run)))
    const y =
      SPARKLINE_PADDING + (1 - clampedRate) * (SPARKLINE_HEIGHT - SPARKLINE_PADDING * 2)
    return { x, y }
  })
  const path = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
    .join(' ')
  const firstPoint = points[0]
  const lastPoint = points[points.length - 1]
  const areaPath =
    firstPoint && lastPoint
      ? `${path} L ${lastPoint.x.toFixed(1)} ${SPARKLINE_HEIGHT - SPARKLINE_PADDING} L ${firstPoint.x.toFixed(1)} ${SPARKLINE_HEIGHT - SPARKLINE_PADDING} Z`
      : ''

  return (
    <svg
      className="metrics-sparkline"
      role="img"
      aria-label="バージョンごとの平均点の推移"
      viewBox={`0 0 ${SPARKLINE_WIDTH} ${SPARKLINE_HEIGHT}`}
      preserveAspectRatio="none"
    >
      {areaPath ? <path className="metrics-sparkline__area" d={areaPath} /> : null}
      <path className="metrics-sparkline__line" d={path} />
      {points.map((point, index) => (
        <circle
          key={`${runs[index].drillRunId}-${index}`}
          className="metrics-sparkline__point"
          cx={point.x}
          cy={point.y}
          r="3"
        />
      ))}
    </svg>
  )
}

function MetricRunStep({ run }: { run: ScoredMetricsRun }) {
  return (
    <div className="metrics-card__run">
      <strong>v{run.courseVersion}</strong>
      <span>
        {formatMetricScore(run.averageScore)} / {formatMetricMaxScore(run.maxScore)} 点
      </span>
      <small>回答 {run.answerCount} 件</small>
    </div>
  )
}

function saveMessageFromLocationState(state: unknown): string | null {
  if (
    typeof state === 'object' &&
    state !== null &&
    'saveMessage' in state &&
    typeof state.saveMessage === 'string'
  ) {
    return state.saveMessage
  }
  return null
}

async function loadCourseMetrics(courseId: string): Promise<CourseMetricsResponse | null> {
  try {
    return await api.getCourseMetrics(courseId)
  } catch {
    return null
  }
}

function buildScoreProgression(metrics: CourseMetricsResponse | null): ScoreProgression | null {
  const scoredRuns = (metrics?.runs ?? [])
    .map((run, index) => ({ run, index }))
    .filter((entry): entry is { run: ScoredMetricsRun; index: number } =>
      isScoredMetricsRun(entry.run),
    )
    .sort((left, right) => {
      const versionDiff = left.run.courseVersion - right.run.courseVersion
      return versionDiff !== 0 ? versionDiff : left.index - right.index
    })

  const runs = scoredRuns.map((entry) => entry.run)
  if (runs.length < 2) {
    return null
  }

  const capped = runs.length > MAX_VISIBLE_STEPS
  const stepIndexes = capped
    ? [0, runs.length - 2, runs.length - 1]
    : runs.map((_, index) => index)

  return {
    runs,
    stepIndexes,
    omittedCount: capped ? runs.length - stepIndexes.length : 0,
    uniformMaxScore: runs.every((run) => run.maxScore === runs[0].maxScore),
  }
}

function isScoredMetricsRun(run: CourseMetricsRun): run is ScoredMetricsRun {
  return (
    run.answerCount > 0 &&
    run.averageScore !== null &&
    run.maxScore !== null &&
    run.maxScore > 0
  )
}

function formatMetricScore(score: number): string {
  return score.toFixed(1)
}

function formatMetricMaxScore(score: number): string {
  return Number.isInteger(score) ? String(score) : score.toFixed(1)
}

function scoreRate(run: ScoredMetricsRun): number {
  return run.averageScore / run.maxScore
}

function formatRatePercent(run: ScoredMetricsRun): string {
  return `${Math.round(scoreRate(run) * 100)}%`
}

function formatScoreDelta(delta: number): string {
  return `${delta >= 0 ? '+' : ''}${delta.toFixed(1)} 点`
}

function validateCourse(title: string, markdown: string, drillFocus: string): string | null {
  if (!title.trim()) {
    return 'タイトルが必要です。'
  }
  if (!markdown.trim()) {
    return 'Markdown 本文が必要です。'
  }
  if (markdown.length > MARKDOWN_LIMIT) {
    return 'Markdown 本文が MVP の文字数上限を超えています。'
  }
  if (drillFocus.length > DRILL_FOCUS_LIMIT) {
    return '出題観点は 500 文字以内で入力してください。'
  }
  return null
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    return error.error.message
  }
  return '処理に失敗しました。'
}
