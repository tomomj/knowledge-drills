import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import { api, ApiClientError } from '../api/client'
import type { DocumentPatch, FailureSignal, PatchStatus } from '../api/types'
import { AppShell } from '../components/common/AppShell'
import { Breadcrumbs } from '../components/common/Breadcrumbs'
import { DiffViewer } from '../components/common/DiffViewer'
import { StatusBanner } from '../components/common/StatusBanner'

type PageState =
  | { status: 'loading' }
  | { status: 'ready'; patch: DocumentPatch }
  | { status: 'failed'; message: string; patch?: DocumentPatch }

type Decision = 'apply' | 'reject'

const PATCH_STATUS_CHIPS: Record<PatchStatus, { label: string; tone: string }> = {
  proposed: { label: '提案中', tone: 'warning' },
  applied: { label: '適用済み', tone: 'success' },
  rejected: { label: '却下', tone: 'muted' },
  stale: { label: '要再分析', tone: 'error' },
}

export function PatchReviewPage() {
  const { patchId: patchIdParam } = useParams()
  const [searchParams] = useSearchParams()
  const patchId = patchIdParam ?? searchParams.get('patchId')
  const [state, setState] = useState<PageState>({ status: 'loading' })
  const [ownerFeedback, setOwnerFeedback] = useState('')
  const [pendingDecision, setPendingDecision] = useState<Decision | null>(null)

  useEffect(() => {
    let active = true
    async function load() {
      if (!patchId) {
        setState({ status: 'failed', message: 'Patch が見つかりません。' })
        return
      }
      try {
        const patch = await api.getPatch(patchId)
        if (active) {
          setState({ status: 'ready', patch })
          setOwnerFeedback(patch.ownerFeedback ?? '')
        }
      } catch (error) {
        if (active) {
          setState({ status: 'failed', message: errorMessage(error, 'Patch の取得に失敗しました。') })
        }
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [patchId])

  const patch = state.status === 'ready' ? state.patch : state.status === 'failed' ? state.patch : null
  const sampleSize = useMemo(
    () => patch?.failureSignals.reduce((total, signal) => total + signal.sampleSize, 0) ?? 0,
    [patch],
  )
  const canDecide = patch?.status === 'proposed' && pendingDecision === null

  async function decide(decision: Decision) {
    if (!patch) {
      return
    }
    setPendingDecision(decision)
    try {
      const payload = { ownerFeedback: ownerFeedback.trim() || null }
      const updated =
        decision === 'apply'
          ? await api.applyPatch(patch.id, payload)
          : await api.rejectPatch(patch.id, payload)
      setState({ status: 'ready', patch: updated })
      setOwnerFeedback(updated.ownerFeedback ?? '')
    } catch (error) {
      setState({
        status: 'failed',
        message: decisionErrorMessage(error),
        patch,
      })
    } finally {
      setPendingDecision(null)
    }
  }

  if (state.status === 'loading') {
    return (
      <AppShell>
        <main className="page">
          <StatusBanner tone="info">Patch を読み込んでいます。</StatusBanner>
        </main>
      </AppShell>
    )
  }

  const statusChip = patch ? PATCH_STATUS_CHIPS[patch.status] : null
  const courseUrl = patch ? `/courses/${patch.courseId}` : undefined
  const drillUrl = patch ? `/courses/${patch.courseId}/drill-runs/${patch.drillRunId}` : undefined

  return (
    <AppShell>
      <main className="page">
        <section className="page-head" aria-labelledby="patch-title">
          <div>
            <Breadcrumbs
              items={[
                { label: '講座一覧', to: '/courses' },
                { label: '講座管理', to: courseUrl },
                { label: 'ドリル確認', to: drillUrl },
                { label: '資料修正案' },
              ]}
            />
            <h1 id="patch-title">資料修正案のレビュー</h1>
            {patch ? (
              <div className="meta-chips" style={{ marginTop: 8 }}>
                {statusChip ? (
                  <span className={`chip chip--${statusChip.tone}`}>{statusChip.label}</span>
                ) : null}
                <span>ドリル {patch.drillRunId}</span>
                <span className="meta-chips__sep">·</span>
                <span>回答サンプル {sampleSize} 件</span>
              </div>
            ) : null}
          </div>
          <div className="toolbar">
            <button
              type="button"
              className="btn btn--danger"
              disabled={!canDecide}
              onClick={() => void decide('reject')}
            >
              却下する
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={!canDecide}
              onClick={() => void decide('apply')}
            >
              修正を適用する
            </button>
          </div>
        </section>

        {state.status === 'failed' ? <StatusBanner tone="error">{state.message}</StatusBanner> : null}
        {patch ? <PatchStatusBanner patch={patch} /> : null}
        {patch?.patchSummary ? (
          <StatusBanner tone="info">要約：{patch.patchSummary}</StatusBanner>
        ) : null}

        {patch ? (
          <section className="patch-grid">
            <div className="patch-col">
              {patch.failureSignals.map((signal) => (
                <FailureSignalItem key={signal.id} signal={signal} />
              ))}

              <article className="card">
                <div className="card__head">
                  <h2>リスクノート</h2>
                </div>
                <div className="card__body">
                  <ul className="plain-list">
                    {patch.riskNotes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                </div>
              </article>
            </div>

            <div className="patch-col">
              <DiffViewer title="提案される変更" diffText={patch.diffText} />
              <div className="card">
                <div className="card__body">
                  <label className="field">
                    <span className="field__label">
                      オーナーコメント
                      <span className="field__hint">任意</span>
                    </span>
                    <textarea
                      rows={4}
                      placeholder="適用・却下の理由や補足を残せます"
                      value={ownerFeedback}
                      onChange={(event) => setOwnerFeedback(event.target.value)}
                    />
                  </label>
                </div>
              </div>
            </div>
          </section>
        ) : null}
      </main>
    </AppShell>
  )
}

function PatchStatusBanner({ patch }: { patch: DocumentPatch }) {
  if (patch.status === 'stale') {
    return <StatusBanner tone="warning">このパッチは古くなっています。再分析が必要です。</StatusBanner>
  }
  if (patch.status === 'applied') {
    return <StatusBanner tone="success">パッチを適用しました。</StatusBanner>
  }
  if (patch.status === 'rejected') {
    return <StatusBanner tone="info">パッチを却下しました。</StatusBanner>
  }
  return null
}

function FailureSignalItem({ signal }: { signal: FailureSignal }) {
  const severity =
    signal.severity === 'high'
      ? { label: '重大度: 高', tone: 'error' }
      : signal.severity === 'medium'
        ? { label: '重大度: 中', tone: 'warning' }
        : { label: '重大度: 低', tone: 'muted' }
  return (
    <article className={`card signal signal--${signal.severity}`}>
      <div className="signal__head">
        <h2>{signal.title}</h2>
        <span className={`chip chip--${severity.tone}`}>{severity.label}</span>
      </div>
      <p className="signal__meta">
        サンプル {signal.sampleSize} 件
        {signal.confidenceNote ? ` · ${signal.confidenceNote}` : ''}
      </p>
      <dl className="signal-facts">
        <div>
          <dt>原因</dt>
          <dd>{signal.likelyCause}</dd>
        </div>
        <div>
          <dt>資料の欠落</dt>
          <dd>{signal.suspectedDocumentGap}</dd>
        </div>
        <div>
          <dt>修正方針</dt>
          <dd>{signal.recommendedChange}</dd>
        </div>
      </dl>
    </article>
  )
}

function decisionErrorMessage(error: unknown): string {
  if (error instanceof ApiClientError && error.error.code === 'patch_not_proposed') {
    return `Patch status: ${error.error.currentStatus ?? 'unknown'}`
  }
  return errorMessage(error, 'Patch の判断に失敗しました。')
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiClientError) {
    return error.error.message
  }
  return fallback
}
