import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { api, ApiClientError } from '../api/client'
import type { LearnerDrill, SubmitAnswerResponse } from '../api/types'
import { AppShell } from '../components/common/AppShell'
import { StatusBanner } from '../components/common/StatusBanner'

type PageState =
  | { status: 'loading' }
  | { status: 'ready'; drill: LearnerDrill }
  | { status: 'submitted'; result: SubmitAnswerResponse }
  | { status: 'invalidToken'; message: string }
  | { status: 'failed'; message: string }

export function LearnerDrillPage() {
  const { shareToken } = useParams()
  const [state, setState] = useState<PageState>({ status: 'loading' })
  const [learnerName, setLearnerName] = useState('')
  const [answers, setAnswers] = useState<Record<string, string>>({})

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
    const validation = validateSubmission(learnerName, answers, drill)
    if (validation) {
      setState({ status: 'failed', message: validation })
      return
    }
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
      setState({ status: 'failed', message: submitErrorMessage(error) })
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

  const drill = state.status === 'ready' ? state.drill : null
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
          <p>資料の理解度を確認する {totalCount} 問です。自分の言葉で回答してください。</p>
        </section>

        {state.status === 'failed' ? (
          <StatusBanner tone="error">{state.message}</StatusBanner>
        ) : null}

        {drill ? (
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
              <span className="submit-row__note">すべての設問への回答が必要です</span>
              <button
                type="button"
                className="btn btn--primary btn--lg"
                onClick={() => void submit(drill)}
              >
                回答を提出する
              </button>
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
