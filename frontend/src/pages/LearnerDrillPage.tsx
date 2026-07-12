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
  | { status: 'closed'; message: string }
  | { status: 'invalidToken'; message: string }
  | { status: 'failed'; message: string }

type LearnerPhase = 'intro' | 'reading' | 'answering'

const MAX_LEARNER_NAME_LENGTH = 50
const MAX_ANSWER_TEXT_LENGTH = 2_000

export function LearnerDrillPage() {
  const { shareToken } = useParams()
  const [state, setState] = useState<PageState>({ status: 'loading' })
  const [phase, setPhase] = useState<LearnerPhase>('intro')
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
        if (error instanceof ApiClientError && error.error.code === 'share_closed') {
          setState({ status: 'closed', message: 'このドリルの回答受付は終了しました。' })
        } else if (error instanceof ApiClientError && error.error.code === 'invalid_share_token') {
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

  useEffect(() => {
    if (phase === 'answering') {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }, [phase])

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
      if (error instanceof ApiClientError && error.error.code === 'share_closed') {
        setState({ status: 'closed', message: 'このドリルの回答受付は終了しました。' })
      } else {
        setState({ status: 'ready', drill, submitError: submitErrorMessage(error) })
      }
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

  if (state.status === 'closed') {
    return (
      <AppShell variant="learner">
        <main className="page page--narrow">
          <StatusBanner tone="info">{state.message}</StatusBanner>
          <p className="learner-note">ご協力ありがとうございました。</p>
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
  const hasCourseMaterial = Boolean(drill?.courseMarkdown)
  const isIntro = phase === 'intro' && Boolean(drill)
  const isReading = phase === 'reading' && hasCourseMaterial
  const answeredCount = drill
    ? drill.questions.filter((question) => answers[question.id]?.trim()).length
    : 0
  const totalCount = drill?.questions.length ?? 0

  return (
    <AppShell variant="learner">
      <main className="page page--narrow">
        {drill && isIntro ? (
          <section className="card learner-intro" aria-labelledby="learner-intro-title">
            <div className="learner-intro__head">
              <p className="eyebrow">確認ドリルのご案内</p>
              <h1 id="learner-intro-title">{drill.courseTitle}</h1>
              <p>
                教材の理解度を確認するための短いドリルです。
                {hasCourseMaterial ? '教材を読んでから、' : ''}
                自分の言葉で回答してください。
              </p>
            </div>

            <dl className="learner-intro__meta" aria-label="ドリルの概要">
              <div>
                <dt>所要時間</dt>
                <dd>約5分</dd>
              </div>
              <div>
                <dt>問題数</dt>
                <dd>{drill.questions.length}問</dd>
              </div>
            </dl>

            <ol className="learner-intro__steps" aria-label="回答までの流れ">
              {hasCourseMaterial ? (
                <li>
                  <span className="learner-intro__step-number">1</span>
                  <div>
                    <strong>教材を読む</strong>
                    <p>まずは教材の内容を確認します。</p>
                  </div>
                </li>
              ) : null}
              <li>
                <span className="learner-intro__step-number">{hasCourseMaterial ? 2 : 1}</span>
                <div>
                  <strong>{drill.questions.length}問に回答する</strong>
                  <p>正解を調べず、理解した内容を書いてください。</p>
                </div>
              </li>
              <li>
                <span className="learner-intro__step-number">{hasCourseMaterial ? 3 : 2}</span>
                <div>
                  <strong>回答を提出する</strong>
                  <p>提出後、その場でフィードバックを確認できます。</p>
                </div>
              </li>
            </ol>

            <aside className="learner-intro__privacy" aria-label="回答の取り扱い">
              <strong>回答について</strong>
              <p>お名前と回答内容は講座の管理者が確認し、教材改善のために利用します。</p>
            </aside>

            <div className="learner-intro__action">
              <button
                type="button"
                className="btn btn--primary btn--lg"
                onClick={() => setPhase(hasCourseMaterial ? 'reading' : 'answering')}
              >
                {hasCourseMaterial ? '教材を読んで始める' : '回答を始める'}
              </button>
              <span>途中でページを閉じると、入力内容は保存されません</span>
            </div>
          </section>
        ) : (
          <section className="learner-hero" aria-labelledby="learner-title">
            <p className="eyebrow">Learner</p>
            <h1 id="learner-title">確認ドリル</h1>
            <p>教材を読んでから回答してください。回答は教材改善のために利用されます。</p>
          </section>
        )}

        {state.status === 'failed' ? (
          <StatusBanner tone="error">{state.message}</StatusBanner>
        ) : null}
        {submitError ? <StatusBanner tone="error">{submitError}</StatusBanner> : null}

        {drill && !isIntro && isReading ? (
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

        {drill && !isIntro && !isReading ? (
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
                <div className="field">
                  <label className="field__label" htmlFor="learner-name">
                    お名前
                  </label>
                  <input
                    id="learner-name"
                    value={learnerName}
                    maxLength={MAX_LEARNER_NAME_LENGTH}
                    disabled={isSubmitting}
                    onChange={(event) => setLearnerName(event.target.value)}
                  />
                  <span className="field__hint" aria-label="お名前の文字数">
                    {learnerName.length} / {MAX_LEARNER_NAME_LENGTH} 文字
                  </span>
                </div>
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
                    <div className="field">
                      <label className="lq__question" htmlFor={`answer-${question.id}`}>
                        {question.question}
                      </label>
                      <textarea
                        id={`answer-${question.id}`}
                        rows={3}
                        placeholder="回答を入力…"
                        value={answers[question.id] ?? ''}
                        maxLength={MAX_ANSWER_TEXT_LENGTH}
                        disabled={isSubmitting}
                        onChange={(event) =>
                          setAnswers((current) => ({
                            ...current,
                            [question.id]: event.target.value,
                          }))
                        }
                      />
                      <span className="field__hint" aria-label={`${question.id} の回答文字数`}>
                        {(answers[question.id] ?? '').length} /{' '}
                        {MAX_ANSWER_TEXT_LENGTH.toLocaleString('ja-JP')} 文字
                      </span>
                    </div>
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
  if (learnerName.length > MAX_LEARNER_NAME_LENGTH) {
    return `受講者名は ${MAX_LEARNER_NAME_LENGTH} 文字以内で入力してください。`
  }
  if (drill.questions.some((question) => answers[question.id]?.length > MAX_ANSWER_TEXT_LENGTH)) {
    return `回答は 1 問 ${MAX_ANSWER_TEXT_LENGTH.toLocaleString('ja-JP')} 文字以内で入力してください。`
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
