import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { api, ApiClientError } from '../api/client'
import type { LearnerDrill, SubmitAnswerResponse } from '../api/types'
import { AppShell } from '../components/common/AppShell'
import { MarkdownView } from '../components/common/MarkdownView'
import { StatusBanner } from '../components/common/StatusBanner'

type PageState =
  | { status: 'loading' }
  | { status: 'ready'; drill: LearnerDrill; submitError?: string }
  | { status: 'submitting'; drill: LearnerDrill }
  | { status: 'submitted'; result: SubmitAnswerResponse }
  | { status: 'invalidToken'; message: string }
  | { status: 'failed'; message: string }

type LearnerPhase = 'reading' | 'answering'

export function LearnerDrillPage() {
  const { shareToken } = useParams()
  const [state, setState] = useState<PageState>({ status: 'loading' })
  const [phase, setPhase] = useState<LearnerPhase>('reading')
  const [learnerName, setLearnerName] = useState('')
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const submittingRef = useRef(false)

  useEffect(() => {
    let active = true
    async function load() {
      if (!shareToken) {
        setState({ status: 'invalidToken', message: '共有 URL が無効です。' })
        return
      }
      try {
        const drill = await api.getLearnerDrill(shareToken)
        if (active) {
          setState({ status: 'ready', drill })
          setAnswers(Object.fromEntries(drill.questions.map((question) => [question.id, ''])))
        }
      } catch (error) {
        if (!active) {
          return
        }
        if (error instanceof ApiClientError && error.error.code === 'invalid_share_token') {
          setState({ status: 'invalidToken', message: '共有 URL が無効です。' })
        } else {
          setState({ status: 'failed', message: 'ドリルの取得に失敗しました。' })
        }
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [shareToken])

  async function submit(drill: LearnerDrill) {
    if (submittingRef.current) {
      return
    }
    const validation = validateSubmission(learnerName, answers, drill)
    if (validation) {
      setState({ status: 'ready', drill, submitError: validation })
      return
    }
    submittingRef.current = true
    setState({ status: 'submitting', drill })
    try {
      const result = await api.submitAnswer(shareToken ?? '', {
        learnerName,
        answers: drill.questions.map((question) => ({
          questionId: question.id,
          answerText: answers[question.id],
        })),
      })
      setState({ status: 'submitted', result })
    } catch (error) {
      setState({ status: 'ready', drill, submitError: submitErrorMessage(error) })
    } finally {
      submittingRef.current = false
    }
  }

  if (state.status === 'loading') {
    return (
      <AppShell variant="learner">
        <main className="page page--narrow">
          <StatusBanner tone="info">ドリルを読み込んでいます。</StatusBanner>
        </main>
      </AppShell>
    )
  }

  if (state.status === 'invalidToken') {
    return (
      <AppShell variant="learner">
        <main className="page page--narrow">
          <StatusBanner tone="error">{state.message}</StatusBanner>
        </main>
      </AppShell>
    )
  }

  if (state.status === 'submitted') {
    return (
      <AppShell variant="learner">
        <main className="page page--narrow">
          <StatusBanner tone="success">提出が完了しました。</StatusBanner>
          <p className="learner-note">回答は教材改善の分析に使われます。</p>
          <section className="question-stack" aria-label="フィードバック">
            {state.result.feedback.map((feedback, index) => (
              <article className="card feedback-item" key={`${feedback}-${index}`}>
                {feedback}
              </article>
            ))}
          </section>
        </main>
      </AppShell>
    )
  }

  const drill = state.status === 'ready' || state.status === 'submitting' ? state.drill : null
  const isSubmitting = state.status === 'submitting'
  const submitError = state.status === 'ready' ? state.submitError : null
  const isReading = phase === 'reading' && Boolean(drill?.courseMarkdown)
  const answeredCount = drill
    ? drill.questions.filter((question) => answers[question.id]?.trim()).length
    : 0
  const totalCount = drill?.questions.length ?? 0

  return (
    <AppShell variant="learner">
      <main className="page page--narrow">
        <section className="learner-hero" aria-labelledby="learner-title">
          <p className="eyebrow">Learner</p>
          <h1 id="learner-title">確認ドリル</h1>
          <p>教材を読んでから回答してください。回答は教材改善の分析に匿名で利用されます。</p>
        </section>

        {state.status === 'failed' ? (
          <StatusBanner tone="error">{state.message}</StatusBanner>
        ) : null}
        {submitError ? <StatusBanner tone="error">{submitError}</StatusBanner> : null}

        {drill && isReading ? (
          <>
            <section className="card course-material" aria-label="教材">
              <div className="course-material__body">
                <div className="course-material__head">
                  <h2>{drill.courseTitle}</h2>
                  <span className="chip chip--muted">教材バージョン v{drill.courseVersion}</span>
                </div>
                <MarkdownView markdown={drill.courseMarkdown} />
              </div>
            </section>

            <div className="submit-row">
              <span className="submit-row__note">教材を読み終えたら回答へ進んでください</span>
              <button
                type="button"
                className="btn btn--primary btn--lg"
                onClick={() => setPhase('answering')}
              >
                回答に進む
              </button>
            </div>
          </>
        ) : null}

        {drill && !isReading ? (
          <>
            <div className="progress-line" aria-label="回答の進捗">
              <div className="progress-track">
                <div
                  className="progress-fill"
                  style={{ width: `${totalCount ? (answeredCount / totalCount) * 100 : 0}%` }}
                />
              </div>
              <span>
                {answeredCount} / {totalCount} 問 回答済み
              </span>
            </div>

            <div className="card">
              <div className="card__body">
                <label className="field">
                  <span className="field__label">お名前</span>
                  <input
                    value={learnerName}
                    disabled={isSubmitting}
                    onChange={(event) => setLearnerName(event.target.value)}
                  />
                </label>
              </div>
            </div>

            <section className="question-stack">
              {drill.questions.map((question) => {
                const answered = Boolean(answers[question.id]?.trim())
                return (
                  <article className="card lq" key={question.id}>
                    <div className="lq__head">
                      <span className="q-num">{question.id}</span>
                      {answered ? <span className="lq__done">✓ 回答済み</span> : null}
                    </div>
                    <label className="field">
                      <span className="lq__question">{question.question}</span>
                      <textarea
                        rows={3}
                        placeholder="回答を入力…"
                        value={answers[question.id] ?? ''}
                        disabled={isSubmitting}
                        onChange={(event) =>
                          setAnswers((current) => ({
                            ...current,
                            [question.id]: event.target.value,
                          }))
                        }
                      />
                    </label>
                  </article>
                )
              })}
            </section>

            <div className="submit-row">
              <span className="submit-row__note">
                {isSubmitting ? '提出完了までこの画面でお待ちください' : 'すべての設問への回答が必要です'}
              </span>
              {isSubmitting ? (
                <StatusBanner tone="info">回答を提出しています。</StatusBanner>
              ) : (
                <button
                  type="button"
                  className="btn btn--primary btn--lg"
                  onClick={() => void submit(drill)}
                >
                  回答を提出する
                </button>
              )}
            </div>
          </>
        ) : null}
      </main>
    </AppShell>
  )
}

function validateSubmission(
  learnerName: string,
  answers: Record<string, string>,
  drill: LearnerDrill,
): string | null {
  if (!learnerName.trim()) {
    return '受講者名が必要です。'
  }
  if (drill.questions.some((question) => !answers[question.id]?.trim())) {
    return 'すべての問題への回答が必要です。'
  }
  return null
}

function submitErrorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    return error.error.message
  }
  return '回答提出に失敗しました。再試行してください。'
}
