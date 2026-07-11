import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AnalysisStartResponse, DrillAdmin, DrillAnswersResponse } from '../api/types'
import { DrillAdminPage } from './DrillAdminPage'

const drill: DrillAdmin = {
  id: 'drill-1',
  courseId: 'course-1',
  courseVersion: 2,
  drillFocus: '例外条件を重点的に確認',
  status: 'ready',
  questions: [
    {
      id: 'q1',
      question: '判断理由を書いてください。',
      intent: '判断を見る',
      rubric: [{ criterion: '根拠', points: 4, required: true }],
      idealAnswer: '根拠に基づき判断する。',
      sourceEvidence: [{ sectionHeading: '方針', excerpt: '## 方針' }],
      maxScore: 4,
    },
  ],
  rubricSummary: ['q1: 根拠'],
  shareUrl: '/drills/share-token',
  answerCount: 2,
  scoreSummary: {
    gradedAnswerCount: 1,
    averageScore: 3,
    maxScore: 4,
    questions: [
      {
        questionId: 'q1',
        averageScore: 3,
        maxScore: 4,
        gradedAnswerCount: 1,
        commonMissingPoints: ['例外条件'],
        failureTags: ['判断根拠不足'],
      },
    ],
  },
  analysisTimeline: [],
  canAnalyze: true,
  errorMessage: null,
  needsAnalysis: false,
}

const answersResponse: DrillAnswersResponse = {
  courseVersion: 2,
  answers: [
    {
      id: 'answer-1',
      learnerName: '受講者A',
      status: 'graded',
      totalScore: 3,
      maxScore: 4,
      answers: { q1: '根拠を書きました' },
      gradingResults: [
        {
          questionId: 'q1',
          score: 3,
          maxScore: 4,
          correctPoints: [],
          missingPoints: ['例外条件'],
          feedback: '例外条件も添えてください。',
          failureTags: ['判断根拠不足'],
        },
      ],
    },
    {
      id: 'answer-2',
      learnerName: '受講者B',
      status: 'grading',
      totalScore: null,
      maxScore: null,
      answers: { q1: '採点待ちの回答です' },
      gradingResults: [],
    },
  ],
}

const mocks = vi.hoisted(() => {
  class ApiClientError extends Error {
    error: { code: string; message: string }
    status: number

    constructor(status: number, error: { code: string; message: string }) {
      super(error.message)
      this.status = status
      this.error = error
    }
  }

  return {
    getDrill: vi.fn(),
    getDrillAnswers: vi.fn(),
    analyzeDrill: vi.fn(),
    ApiClientError,
  }
})

vi.mock('../api/client', () => ({
  api: {
    getDrill: mocks.getDrill,
    getDrillAnswers: mocks.getDrillAnswers,
    analyzeDrill: mocks.analyzeDrill,
  },
  ApiClientError: mocks.ApiClientError,
}))

function renderDrillAdmin() {
  render(
    <MemoryRouter initialEntries={['/courses/course-1/drill-runs/drill-1']}>
      <Routes>
        <Route path="/courses/:courseId/drill-runs/:drillRunId" element={<DrillAdminPage />} />
        <Route
          path="/courses/:courseId/drill-runs/:drillRunId/analysis"
          element={<div>Patch Review</div>}
        />
      </Routes>
    </MemoryRouter>,
  )
}

function noGradedDrill(): DrillAdmin {
  return {
    ...drill,
    answerCount: 0,
    scoreSummary: {
      gradedAnswerCount: 0,
      averageScore: null,
      maxScore: 4,
      questions: [
        {
          questionId: 'q1',
          averageScore: null,
          maxScore: 4,
          gradedAnswerCount: 0,
          commonMissingPoints: [],
          failureTags: [],
        },
      ],
    },
    canAnalyze: false,
  }
}

function runningDrill(): DrillAdmin {
  return {
    ...drill,
    status: 'analyzing',
    analysisTimeline: [
      {
        id: 'collect_answers',
        title: '回答を収集',
        status: 'completed',
        summary: '採点済み回答 1 件を収集しました。',
        evidence: ['受講者A: 3 / 4 点'],
        completedAt: '2026-07-08T10:00:00Z',
      },
      {
        id: 'decide_patch_strategy',
        title: '改善方針を判断',
        status: 'completed',
        summary: '教材修正方針を選定しました。',
        evidence: ['採用レビュー: finding-1 のみ採用 (approvedFindingIds: finding-1)'],
        completedAt: '2026-07-08T10:00:01Z',
      },
    ],
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
}

describe('DrillAdminPage', () => {
  beforeEach(() => {
    mocks.getDrill.mockReset()
    mocks.getDrillAnswers.mockReset()
    mocks.analyzeDrill.mockReset()
    mocks.getDrill.mockResolvedValue(drill)
    mocks.getDrillAnswers.mockResolvedValue(answersResponse)
    mocks.analyzeDrill.mockResolvedValue({ patchId: 'patch-1' })
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('shows share URL, status, score summary, collapsed questions, and analyze button in side-first DOM order', async () => {
    const user = userEvent.setup()
    renderDrillAdmin()

    await waitFor(() => expect(screen.getByText('/drills/share-token')).toBeTruthy())
    const side = screen.getByLabelText('ドリル補助情報')
    const main = screen.getByLabelText('ドリル主内容')
    expect(
      side.compareDocumentPosition(main) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(screen.queryByText('Status')).toBeNull()
    expect(screen.queryByText('実行可能')).toBeNull()
    expect(screen.getByText('ドリルの状態')).toBeTruthy()
    expect(screen.getByText('例外条件を重点的に確認')).toBeTruthy()
    expect(screen.getByText('採点済み回答')).toBeTruthy()
    expect(screen.getAllByText('3.0 / 4 点')).toHaveLength(1)
    expect(screen.getByText(/欠落: 例外条件/)).toBeTruthy()
    expect(screen.getByText(/タグ: 判断根拠不足/)).toBeTruthy()
    expect(screen.getAllByText('2 件')).toHaveLength(1)
    expect(screen.getAllByText('判断理由を書いてください。').length).toBeGreaterThan(0)
    const questionDetails = screen.getByText('設問詳細を表示').closest('details')
    expect(questionDetails?.hasAttribute('open')).toBe(false)
    await user.click(within(questionDetails as HTMLElement).getByText('設問詳細を表示'))
    expect(questionDetails?.hasAttribute('open')).toBe(true)
    expect(within(questionDetails as HTMLElement).getByText('模範解答')).toBeTruthy()
    expect(within(questionDetails as HTMLElement).getByText('根拠に基づき判断する。')).toBeTruthy()
    expect(within(questionDetails as HTMLElement).getByText('教材の根拠')).toBeTruthy()
    expect(within(questionDetails as HTMLElement).getByText('## 方針')).toBeTruthy()
    const button = screen.getByRole('button', { name: '回答を分析する' }) as HTMLButtonElement
    expect(button.disabled).toBe(false)
    expect(screen.queryByText('低スコア回答を検知しました — 分析を推奨')).toBeNull()

    // 資料バージョンと回答一覧（先頭の回答者が選択された状態）
    expect(screen.getByText('v2')).toBeTruthy()
    await waitFor(() => expect(screen.getAllByText('受講者A').length).toBeGreaterThan(0))
    expect(screen.getByText('2 / 2 件')).toBeTruthy()
    expect(screen.getByText('根拠を書きました')).toBeTruthy()
    expect(screen.getByText('例外条件も添えてください。')).toBeTruthy()
    expect(screen.getByText('採点済み')).toBeTruthy()
  })

  it('shows a non-chip warning banner immediately before the analyze button', async () => {
    mocks.getDrill.mockResolvedValueOnce({ ...drill, needsAnalysis: true })

    renderDrillAdmin()

    const message = await screen.findByText('低スコア回答を検知しました — 分析を推奨')
    const banner = message.closest('.status-banner')
    const button = screen.getByRole('button', { name: '回答を分析する' }) as HTMLButtonElement
    expect(banner).not.toBeNull()
    expect(banner?.classList.contains('status-banner--warning')).toBe(true)
    expect(banner?.classList.contains('chip')).toBe(false)
    expect(banner?.parentElement?.classList.contains('toolbar')).toBe(true)
    expect(banner?.nextElementSibling).toBe(button)
    expect(button.disabled).toBe(false)
  })

  it('hides the needs-analysis banner when there are no graded answers', async () => {
    mocks.getDrill.mockResolvedValueOnce({ ...noGradedDrill(), needsAnalysis: true })
    mocks.getDrillAnswers.mockResolvedValueOnce({ ...answersResponse, answers: [] })

    renderDrillAdmin()

    await screen.findByRole('button', { name: '回答を分析する' })
    expect(screen.queryByText('低スコア回答を検知しました — 分析を推奨')).toBeNull()
    const button = screen.getByRole('button', { name: '回答を分析する' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
  })

  it('disables analysis and shows guidance when there are no graded answers', async () => {
    mocks.getDrill.mockResolvedValueOnce(noGradedDrill())
    mocks.getDrillAnswers.mockResolvedValueOnce({ ...answersResponse, answers: [] })

    renderDrillAdmin()

    await screen.findByText('共有 URL を受講者に配布しましょう。')
    expect(screen.getByText('未計測 / 4 点')).toBeTruthy()
    expect(screen.queryByText('採点済み回答がまだありません')).toBeNull()
    expect(screen.queryByText('まだ回答がありません。共有 URL を受講者に配布しましょう。')).toBeNull()
    const button = screen.getByRole('button', { name: '回答を分析する' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
  })

  it('shows a friendly message for generation failure without exposing internal text', async () => {
    mocks.getDrill.mockResolvedValueOnce({
      ...drill,
      status: 'failed',
      questions: [],
      rubricSummary: [],
      shareUrl: '/drills/failed-token',
      canAnalyze: false,
      errorMessage: 'drill generation failed',
    })

    renderDrillAdmin()

    await screen.findByText(/教材の根拠を確認できませんでした。/)
    expect(screen.queryByText(/drill generation failed/)).toBeNull()
  })

  it('polls the timeline while analysis is pending and stops after navigating to patch review', async () => {
    const analysis = deferred<AnalysisStartResponse>()
    mocks.analyzeDrill.mockReturnValueOnce(analysis.promise)
    mocks.getDrill.mockResolvedValueOnce(drill).mockResolvedValue(runningDrill())

    renderDrillAdmin()

    await screen.findByText('/drills/share-token')
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: '回答を分析する' }))
    expect(screen.getByText('回答を分析中です。')).toBeTruthy()
    expect((screen.getByLabelText('設問一覧') as HTMLDetailsElement).open).toBe(false)
    expect((screen.getByLabelText('回答一覧') as HTMLDetailsElement).open).toBe(false)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(screen.getByText('回答を収集')).toBeTruthy()
    expect(screen.getByText('採点済み回答 1 件を収集しました。')).toBeTruthy()
    expect(screen.getByText('採用レビュー: finding-1 のみ採用 (approvedFindingIds: finding-1)')).toBeTruthy()

    await act(async () => {
      analysis.resolve({ patchId: 'patch-1' })
      await analysis.promise
    })
    expect(screen.getByText('Patch Review')).toBeTruthy()
    const callsAfterNavigation = mocks.getDrill.mock.calls.length

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(callsAfterNavigation)
  })

  it('shows an error banner and stops polling when analysis fails', async () => {
    const analysis = deferred<AnalysisStartResponse>()
    mocks.analyzeDrill.mockReturnValueOnce(analysis.promise)
    mocks.getDrill.mockResolvedValueOnce(drill).mockResolvedValue(runningDrill())

    renderDrillAdmin()

    await screen.findByText('/drills/share-token')
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: '回答を分析する' }))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(screen.getByText('回答を収集')).toBeTruthy()
    expect((screen.getByLabelText('設問一覧') as HTMLDetailsElement).open).toBe(false)

    await act(async () => {
      analysis.reject(
        new mocks.ApiClientError(500, {
          code: 'analysis_failed',
          message: '分析サービスが停止しています。',
        }),
      )
      await analysis.promise.catch(() => undefined)
    })

    expect(screen.getByText('分析サービスが停止しています。')).toBeTruthy()
    expect((screen.getByLabelText('設問一覧') as HTMLDetailsElement).open).toBe(true)
    expect((screen.getByLabelText('回答一覧') as HTMLDetailsElement).open).toBe(true)
    const callsAfterFailure = mocks.getDrill.mock.calls.length

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(callsAfterFailure)
  })

  it('shows a skip banner and stays on the page when analysis completes without a patch', async () => {
    mocks.analyzeDrill.mockResolvedValueOnce({ patchId: null })
    const skippedDrill: DrillAdmin = {
      ...drill,
      status: 'analyzed',
      analysisTimeline: [
        {
          id: 'create_patch',
          title: '修正案を作成',
          status: 'skipped',
          summary: '承認された Failure Signal がないため patch 提案を見送りました',
          evidence: [],
          completedAt: null,
        },
      ],
    }
    mocks.getDrill.mockResolvedValueOnce(drill).mockResolvedValue(skippedDrill)

    renderDrillAdmin()

    await screen.findByText('/drills/share-token')
    fireEvent.click(screen.getByRole('button', { name: '回答を分析する' }))

    await screen.findByText(
      '分析は完了しました。承認された所見がなかったため、パッチ提案は見送られました。',
    )
    expect(screen.queryByText('Patch Review')).toBeNull()
    await waitFor(() =>
      expect(
        screen.getByText('承認された Failure Signal がないため patch 提案を見送りました'),
      ).toBeTruthy(),
    )
    expect((screen.getByLabelText('設問一覧') as HTMLDetailsElement).open).toBe(true)
    expect((screen.getByLabelText('回答一覧') as HTMLDetailsElement).open).toBe(true)
  })

  it('maps agent invocation failure to a retryable Japanese message', async () => {
    mocks.analyzeDrill.mockRejectedValueOnce(
      new mocks.ApiClientError(502, {
        code: 'agent_invocation_failed',
        message: 'Agent invocation failed.',
      }),
    )

    renderDrillAdmin()

    await screen.findByText('/drills/share-token')
    fireEvent.click(screen.getByRole('button', { name: '回答を分析する' }))

    await waitFor(() =>
      expect(
        screen.getByText(
          '分析 Agent の実行に失敗しました。少し待ってからもう一度お試しください。',
        ),
      ).toBeTruthy(),
    )
  })

  it('switches selected answer and filters by learner name', async () => {
    const user = userEvent.setup()
    renderDrillAdmin()

    await screen.findByRole('button', { name: /受講者B/ })
    await user.click(screen.getByRole('button', { name: /受講者B/ }))

    expect(screen.getByText('採点待ちの回答です')).toBeTruthy()
    expect(screen.getAllByText('採点中').length).toBeGreaterThan(0)

    await user.type(screen.getByLabelText('回答者名で検索'), '受講者A')
    expect(screen.getByText('1 / 2 件')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /受講者B/ })).toBeNull()
  })
})
