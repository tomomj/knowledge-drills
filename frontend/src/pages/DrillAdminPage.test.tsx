import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    answerCount: 2,
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
        status: 'running',
        summary: '採点済み回答 1 件を分析しています。',
        evidence: ['受講者A: 3 / 4 点'],
        completedAt: null,
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

  it('shows share URL, answer count, rubric summary, score summary, focus, and analyze button', async () => {
    renderDrillAdmin()

    await waitFor(() => expect(screen.getByText('/drills/share-token')).toBeTruthy())
    expect(screen.getByText('回答数')).toBeTruthy()
    expect(screen.getAllByText('判断理由を書いてください。').length).toBeGreaterThan(0)
    expect(screen.getByText('根拠')).toBeTruthy()
    expect(screen.getByText('例外条件を重点的に確認')).toBeTruthy()
    expect(screen.getByText('採点済み回答')).toBeTruthy()
    expect(screen.getAllByText('3.0 / 4 点').length).toBeGreaterThan(0)
    expect(screen.getByText(/欠落: 例外条件/)).toBeTruthy()
    expect(screen.getByText(/タグ: 判断根拠不足/)).toBeTruthy()
    const button = screen.getByRole('button', { name: '回答を分析する' }) as HTMLButtonElement
    expect(button.disabled).toBe(false)

    // 資料バージョンと回答一覧（先頭の回答者が選択された状態）
    expect(screen.getByText('v2')).toBeTruthy()
    await waitFor(() => expect(screen.getAllByText('受講者A').length).toBeGreaterThan(0))
    expect(screen.getByText('2 / 2 件')).toBeTruthy()
    expect(screen.getByText('根拠を書きました')).toBeTruthy()
    expect(screen.getByText('例外条件も添えてください。')).toBeTruthy()
    expect(screen.getByText('採点済み')).toBeTruthy()
  })

  it('disables analysis and shows guidance when there are no graded answers', async () => {
    mocks.getDrill.mockResolvedValueOnce(noGradedDrill())

    renderDrillAdmin()

    await screen.findByText('採点済み回答がまだありません')
    expect(screen.getByText('未計測 / 4 点')).toBeTruthy()
    const button = screen.getByRole('button', { name: '回答を分析する' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
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

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(screen.getByText('回答を収集')).toBeTruthy()
    expect(screen.getByText('採点済み回答 1 件を分析しています。')).toBeTruthy()

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
    const callsAfterFailure = mocks.getDrill.mock.calls.length

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(callsAfterFailure)
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
