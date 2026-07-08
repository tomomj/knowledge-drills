import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { api, ApiClientError } from '../api/client'
import type {
  CourseMetricsResponse,
  CourseMetricsRun,
  CourseRevisionDiff,
  CourseRevisionSummary,
} from '../api/types'
import { AppShell } from '../components/common/AppShell'
import { Breadcrumbs } from '../components/common/Breadcrumbs'
import { DiffViewer } from '../components/common/DiffViewer'
import { StatusBanner } from '../components/common/StatusBanner'

type PageState =
  | { status: 'loading' }
  | { status: 'ready'; revisions: CourseRevisionSummary[]; versionScores: Map<number, VersionScore> }
  | { status: 'failed'; message: string }

type DiffState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; diff: CourseRevisionDiff }
  | { status: 'failed'; message: string }

export function CourseHistoryPage() {
  const { courseId } = useParams()
  const [state, setState] = useState<PageState>({ status: 'loading' })
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [diffState, setDiffState] = useState<DiffState>({ status: 'idle' })

  useEffect(() => {
    let active = true
    async function load() {
      if (!courseId) {
        setState({ status: 'failed', message: '講座を識別できません。' })
        return
      }
      try {
        const [response, metrics] = await Promise.all([
          api.listCourseRevisions(courseId),
          loadCourseMetrics(courseId),
        ])
        if (active) {
          setState({
            status: 'ready',
            revisions: response.revisions,
            versionScores: buildVersionScoreMap(metrics),
          })
          setSelectedVersion(response.revisions[0]?.version ?? null)
        }
      } catch (error) {
        if (active) {
          setState({ status: 'failed', message: errorMessage(error) })
        }
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [courseId])

  useEffect(() => {
    let active = true
    async function loadDiff() {
      if (!courseId || selectedVersion === null || selectedVersion <= 1) {
        setDiffState({ status: 'idle' })
        return
      }
      setDiffState({ status: 'loading' })
      try {
        const diff = await api.diffCourseRevisions(courseId, selectedVersion - 1, selectedVersion)
        if (active) {
          setDiffState({ status: 'ready', diff })
        }
      } catch (error) {
        if (active) {
          setDiffState({ status: 'failed', message: errorMessage(error) })
        }
      }
    }
    void loadDiff()
    return () => {
      active = false
    }
  }, [courseId, selectedVersion])

  const revisions = state.status === 'ready' ? state.revisions : []
  const versionScores = state.status === 'ready' ? state.versionScores : new Map<number, VersionScore>()

  return (
    <AppShell>
      <main className="page">
        <section className="page-head" aria-labelledby="course-history-title">
          <div>
            <Breadcrumbs
              items={[
                { label: '講座一覧', to: '/courses' },
                { label: '講座管理', to: courseId ? `/courses/${courseId}` : undefined },
                { label: '更新履歴' },
              ]}
            />
            <h1 id="course-history-title">更新履歴</h1>
            <p className="page-head__sub">
              保存・修正案の適用のたびにバージョンが記録されます。選んだバージョンと 1
              つ前との差分を表示します。
            </p>
          </div>
        </section>

        {state.status === 'loading' ? (
          <StatusBanner tone="info">更新履歴を読み込んでいます。</StatusBanner>
        ) : null}
        {state.status === 'failed' ? (
          <StatusBanner tone="error">{state.message}</StatusBanner>
        ) : null}

        {state.status === 'ready' ? (
          <section className="history-grid">
            <div className="card select-list" aria-label="バージョン一覧">
              {revisions.map((revision) => {
                const meta = formatVersionMeta(
                  versionScores.get(revision.version) ?? null,
                  revision.updatedAt,
                )
                return (
                  <button
                    type="button"
                    key={revision.version}
                    className={`select-row${
                      revision.version === selectedVersion ? ' select-row--selected' : ''
                    }`}
                    onClick={() => setSelectedVersion(revision.version)}
                    aria-pressed={revision.version === selectedVersion}
                  >
                    <span className="select-row__label">v{revision.version}</span>
                    <span className="select-row__meta">{meta || '-'}</span>
                  </button>
                )
              })}
            </div>

            <div className="history-detail">
              {selectedVersion !== null && selectedVersion <= 1 ? (
                <StatusBanner tone="info">
                  v1 は最初のバージョンです。比較できる前のバージョンがありません。
                </StatusBanner>
              ) : null}
              {diffState.status === 'loading' ? (
                <StatusBanner tone="info">差分を読み込んでいます。</StatusBanner>
              ) : null}
              {diffState.status === 'failed' ? (
                <StatusBanner tone="error">{diffState.message}</StatusBanner>
              ) : null}
              {diffState.status === 'ready' ? (
                <DiffViewer
                  title={`v${diffState.diff.fromVersion} → v${diffState.diff.toVersion} の変更`}
                  diffText={diffState.diff.diffText}
                  emptyText="変更はありません"
                />
              ) : null}
            </div>
          </section>
        ) : null}
      </main>
    </AppShell>
  )
}

type ScoredMetricsRun = CourseMetricsRun & {
  averageScore: number
  maxScore: number
}

type VersionScore = {
  averageScore: number
  maxScore: number
}

async function loadCourseMetrics(courseId: string): Promise<CourseMetricsResponse | null> {
  try {
    return await api.getCourseMetrics(courseId)
  } catch {
    return null
  }
}

function buildVersionScoreMap(metrics: CourseMetricsResponse | null): Map<number, VersionScore> {
  const versionScores = new Map<number, VersionScore>()
  for (const run of metrics?.runs ?? []) {
    if (isScoredMetricsRun(run)) {
      versionScores.set(run.courseVersion, {
        averageScore: run.averageScore,
        maxScore: run.maxScore,
      })
    }
  }
  return versionScores
}

function isScoredMetricsRun(run: CourseMetricsRun): run is ScoredMetricsRun {
  return (
    run.answerCount > 0 &&
    run.averageScore !== null &&
    run.maxScore !== null &&
    run.maxScore > 0
  )
}

function formatVersionMeta(score: VersionScore | null, updatedAt: string | null): string {
  const parts: string[] = []
  if (score) {
    parts.push(`平均 ${formatMetricScore(score.averageScore)} / ${formatMetricMaxScore(score.maxScore)} 点`)
  }
  if (updatedAt) {
    parts.push(formatDateTime(updatedAt))
  }
  return parts.join(' · ')
}

function formatMetricScore(score: number): string {
  return score.toFixed(1)
}

function formatMetricMaxScore(score: number): string {
  return Number.isInteger(score) ? String(score) : score.toFixed(1)
}

function formatDateTime(isoString: string): string {
  const date = new Date(isoString)
  if (Number.isNaN(date.getTime())) {
    return isoString
  }
  return date.toLocaleString('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    return error.error.message
  }
  return '更新履歴の取得に失敗しました。'
}
