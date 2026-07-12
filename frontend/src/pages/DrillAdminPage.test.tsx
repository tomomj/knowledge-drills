import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
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
  shareStatus: 'open',
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
  analysisOrigin: 'manual',
  latestPatchId: null,
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
    closeDrillSharing: vi.fn(),
    reopenDrillSharing: vi.fn(),
    ApiClientError,
  }
})

vi.mock('../api/client', () => ({
  api: {
    getDrill: mocks.getDrill,
    getDrillAnswers: mocks.getDrillAnswers,
    analyzeDrill: mocks.analyzeDrill,
    closeDrillSharing: mocks.closeDrillSharing,
    reopenDrillSharing: mocks.reopenDrillSharing,
  },
  ApiClientError: mocks.ApiClientError,
}))

function DrillAdminTestRoutes({
  withRouteSwitch = false,
  withUnmountControl = false,
}: {
  withRouteSwitch?: boolean
  withUnmountControl?: boolean
}) {
  const navigate = useNavigate()
  const [adminMounted, setAdminMounted] = useState(true)
  return (
    <>
      {withRouteSwitch ? (
        <button
          type="button"
          onClick={() => navigate('/courses/course-2/drill-runs/drill-2')}
        >
          別のドリルへ移動
        </button>
      ) : null}
      {withUnmountControl ? (
        <button type="button" onClick={() => setAdminMounted(false)}>
          Drill Adminをunmount
        </button>
      ) : null}
      <Routes>
        <Route
          path="/courses/:courseId/drill-runs/:drillRunId"
          element={adminMounted ? <DrillAdminPage /> : <div>Drill Admin Unmounted</div>}
        />
        <Route
          path="/courses/:courseId/drill-runs/:drillRunId/analysis"
          element={<div>Patch Review</div>}
        />
        <Route path="/patches/patch-auto" element={<div>Automatic Patch Review</div>} />
      </Routes>
    </>
  )
}

function renderDrillAdmin({
  withRouteSwitch = false,
  withUnmountControl = false,
  initialEntry = '/courses/course-1/drill-runs/drill-1',
}: {
  withRouteSwitch?: boolean
  withUnmountControl?: boolean
  initialEntry?: string
} = {}) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <DrillAdminTestRoutes
        withRouteSwitch={withRouteSwitch}
        withUnmountControl={withUnmountControl}
      />
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

function automaticRunningDrill(): DrillAdmin {
  return {
    ...runningDrill(),
    analysisOrigin: 'automatic',
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
    mocks.closeDrillSharing.mockReset()
    mocks.reopenDrillSharing.mockReset()
    mocks.getDrill.mockResolvedValue(drill)
    mocks.getDrillAnswers.mockResolvedValue(answersResponse)
    mocks.analyzeDrill.mockResolvedValue({ patchId: 'patch-1' })
    mocks.closeDrillSharing.mockResolvedValue({ ...drill, shareStatus: 'closed' })
    mocks.reopenDrillSharing.mockResolvedValue(drill)
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

  it('closes and reopens answer collection while keeping the stable URL', async () => {
    const user = userEvent.setup()
    renderDrillAdmin()

    await user.click(await screen.findByRole('button', { name: '回答受付を終了' }))

    await waitFor(() =>
      expect(mocks.closeDrillSharing).toHaveBeenCalledWith('course-1', 'drill-1'),
    )
    expect(screen.getByText('受付停止中')).toBeTruthy()
    expect(screen.getByText('/drills/share-token')).toBeTruthy()
    expect(
      screen.getByText('過去の回答は保持したまま、新しい回答を停止しています。'),
    ).toBeTruthy()

    await user.click(screen.getByRole('button', { name: '回答受付を再開' }))

    await waitFor(() =>
      expect(mocks.reopenDrillSharing).toHaveBeenCalledWith('course-1', 'drill-1'),
    )
    expect(screen.getByText('回答受付中')).toBeTruthy()
  })

  it('marks a superseded drill as history without a public URL action', async () => {
    mocks.getDrill.mockResolvedValueOnce({
      ...drill,
      shareUrl: null,
      shareStatus: 'superseded',
    })

    renderDrillAdmin()

    await screen.findByText('旧バージョン')
    expect(
      screen.getByText('このドリルは旧バージョンです。最新版のみ回答できます。'),
    ).toBeTruthy()
    expect(screen.queryByRole('button', { name: '回答受付を終了' })).toBeNull()
    expect(screen.queryByRole('button', { name: '回答受付を再開' })).toBeNull()
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

  it('polls an automatic analyzing drill every second and marks its timeline as automatic', async () => {
    const automaticDrill = automaticRunningDrill()
    mocks.getDrill.mockResolvedValue(automaticDrill)
    vi.useFakeTimers()

    renderDrillAdmin()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByText('AI 自動分析')).toBeTruthy()
    const analyzeButton = screen.getByRole('button', {
      name: '回答を分析する',
    }) as HTMLButtonElement
    expect(analyzeButton.disabled).toBe(true)
    fireEvent.click(analyzeButton)
    expect(mocks.analyzeDrill).not.toHaveBeenCalled()
    expect(mocks.getDrill).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(3)
  })

  it('does not start automatic polling for a manual analyzing drill', async () => {
    mocks.getDrill.mockResolvedValue(runningDrill())
    vi.useFakeTimers()

    renderDrillAdmin()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByText('回答を収集')).toBeTruthy()
    expect(screen.queryByText('AI 自動分析')).toBeNull()
    expect(mocks.getDrill).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(1)
  })

  it('does not start automatic polling before the automatic analysis is analyzing', async () => {
    mocks.getDrill.mockResolvedValue({ ...drill, analysisOrigin: 'automatic' })
    vi.useFakeTimers()

    renderDrillAdmin()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(1)
  })

  it('keeps an analyzed automatic drill visible when drill view is explicitly requested', async () => {
    mocks.getDrill.mockResolvedValue({
      ...automaticRunningDrill(),
      status: 'analyzed',
      latestPatchId: 'patch-auto',
    })

    renderDrillAdmin({ initialEntry: '/courses/course-1/drill-runs/drill-1?view=drill' })

    expect(await screen.findByRole('heading', { name: 'ドリル確認' })).toBeTruthy()
    expect(screen.getByText('/drills/share-token')).toBeTruthy()
    expect(screen.queryByText('Automatic Patch Review')).toBeNull()
  })

  it('stops automatic polling and navigates with the drill latest patch id', async () => {
    const analyzedDrill: DrillAdmin = {
      ...automaticRunningDrill(),
      status: 'analyzed',
      latestPatchId: 'patch-auto',
    }
    mocks.getDrill
      .mockResolvedValueOnce(automaticRunningDrill())
      .mockResolvedValue(analyzedDrill)
    vi.useFakeTimers()

    renderDrillAdmin()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByText('AI 自動分析')).toBeTruthy()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })

    expect(screen.getByText('Automatic Patch Review')).toBeTruthy()
    expect(mocks.getDrill).toHaveBeenCalledTimes(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(2)
  })

  it('stops automatic polling and shows completion when no patch was proposed', async () => {
    const analyzedDrill: DrillAdmin = {
      ...automaticRunningDrill(),
      status: 'analyzed',
      latestPatchId: null,
    }
    mocks.getDrill
      .mockResolvedValueOnce(automaticRunningDrill())
      .mockResolvedValue(analyzedDrill)
    vi.useFakeTimers()

    renderDrillAdmin()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByText('AI 自動分析')).toBeTruthy()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })

    expect(
      screen.getByText(
        '自動分析は完了しました。承認された所見がなかったため、パッチ提案は見送られました。',
      ),
    ).toBeTruthy()
    expect(mocks.getDrill).toHaveBeenCalledTimes(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(2)
  })

  it('stops automatic polling on a failed timeline and enables manual retry', async () => {
    const failedDrill: DrillAdmin = {
      ...automaticRunningDrill(),
      status: 'ready',
      canAnalyze: true,
      analysisTimeline: [
        ...automaticRunningDrill().analysisTimeline,
        {
          id: 'analyze_failures',
          title: '失敗傾向を分析',
          status: 'failed',
          summary: '分析 Agent の実行に失敗しました。',
          evidence: [],
          completedAt: '2026-07-08T10:00:02Z',
        },
      ],
    }
    mocks.getDrill
      .mockResolvedValueOnce(automaticRunningDrill())
      .mockResolvedValue(failedDrill)
    vi.useFakeTimers()

    renderDrillAdmin()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })

    expect(screen.getByText('自動分析に失敗しました。手動で再実行できます。')).toBeTruthy()
    expect(screen.getByText('分析 Agent の実行に失敗しました。')).toBeTruthy()
    expect(
      (screen.getByRole('button', { name: '回答を分析する' }) as HTMLButtonElement).disabled,
    ).toBe(false)
    expect(mocks.getDrill).toHaveBeenCalledTimes(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(2)
  })

  it('keeps the last successful timeline and continues polling after a temporary failure', async () => {
    mocks.getDrill
      .mockResolvedValueOnce(automaticRunningDrill())
      .mockRejectedValueOnce(new Error('temporary network failure'))
      .mockResolvedValue(automaticRunningDrill())
    vi.useFakeTimers()

    renderDrillAdmin()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByText('採点済み回答 1 件を収集しました。')).toBeTruthy()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(screen.getByText('採点済み回答 1 件を収集しました。')).toBeTruthy()
    expect(mocks.getDrill).toHaveBeenCalledTimes(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(3)
    expect(screen.getByText('採点済み回答 1 件を収集しました。')).toBeTruthy()
  })

  it('times out after 180 polls, prevents the 181st poll, and can explicitly reload', async () => {
    const automaticDrill = automaticRunningDrill()
    const reload = deferred<DrillAdmin>()
    const analyzedWithoutPatch: DrillAdmin = {
      ...automaticDrill,
      status: 'analyzed',
      latestPatchId: null,
    }
    mocks.getDrill.mockImplementation(() =>
      mocks.getDrill.mock.calls.length <= 181 ? Promise.resolve(automaticDrill) : reload.promise,
    )
    vi.useFakeTimers()

    renderDrillAdmin()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    for (let attempt = 0; attempt < 180; attempt += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000)
      })
    }

    expect(screen.getByText('状態確認がタイムアウトしました。')).toBeTruthy()
    expect(screen.getByRole('button', { name: '状態を再読み込み' })).toBeTruthy()
    expect(screen.getByText('採点済み回答 1 件を収集しました。')).toBeTruthy()
    expect(mocks.getDrill).toHaveBeenCalledTimes(181)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(181)

    const reloadButton = screen.getByRole('button', {
      name: '状態を再読み込み',
    }) as HTMLButtonElement
    const analyzeButton = screen.getByRole('button', {
      name: '回答を分析する',
    }) as HTMLButtonElement
    expect(analyzeButton.disabled).toBe(true)

    fireEvent.click(analyzeButton)
    fireEvent.click(reloadButton)
    fireEvent.click(reloadButton)

    expect(mocks.getDrill).toHaveBeenCalledTimes(182)
    expect(reloadButton.disabled).toBe(true)
    expect(mocks.analyzeDrill).not.toHaveBeenCalled()

    await act(async () => {
      reload.resolve(analyzedWithoutPatch)
      await reload.promise
    })

    expect(mocks.getDrill).toHaveBeenCalledTimes(182)
    expect(
      screen.getByText(
        '自動分析は完了しました。承認された所見がなかったため、パッチ提案は見送られました。',
      ),
    ).toBeTruthy()
    expect(screen.queryByText('状態確認がタイムアウトしました。')).toBeNull()
  })

  it('restarts automatic polling from a timed-out explicit reload when analysis is still running', async () => {
    const automaticDrill = automaticRunningDrill()
    const reload = deferred<DrillAdmin>()
    const analyzedWithoutPatch: DrillAdmin = {
      ...automaticDrill,
      status: 'analyzed',
      latestPatchId: null,
    }
    mocks.getDrill.mockImplementation(() => {
      const callCount = mocks.getDrill.mock.calls.length
      if (callCount <= 181) {
        return Promise.resolve(automaticDrill)
      }
      if (callCount === 182) {
        return reload.promise
      }
      return Promise.resolve(analyzedWithoutPatch)
    })
    vi.useFakeTimers()

    renderDrillAdmin()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    for (let attempt = 0; attempt < 180; attempt += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000)
      })
    }

    fireEvent.click(screen.getByRole('button', { name: '状態を再読み込み' }))
    await act(async () => {
      reload.resolve(automaticDrill)
      await reload.promise
    })
    expect(screen.queryByText('状態確認がタイムアウトしました。')).toBeNull()
    expect(
      (screen.getByRole('button', { name: '回答を分析する' }) as HTMLButtonElement).disabled,
    ).toBe(true)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })

    expect(mocks.getDrill).toHaveBeenCalledTimes(183)
    expect(
      screen.getByText(
        '自動分析は完了しました。承認された所見がなかったため、パッチ提案は見送られました。',
      ),
    ).toBeTruthy()
  })

  it('ignores an obsolete timed-out reload response after route params change', async () => {
    const automaticDrill = automaticRunningDrill()
    const reload = deferred<DrillAdmin>()
    const nextRouteDrill: DrillAdmin = {
      ...drill,
      id: 'drill-2',
      courseId: 'course-2',
      shareUrl: '/drills/next-route',
    }
    const oldRoutePatch: DrillAdmin = {
      ...automaticDrill,
      status: 'analyzed',
      latestPatchId: 'patch-auto',
    }
    mocks.getDrill.mockImplementation(() => {
      const callCount = mocks.getDrill.mock.calls.length
      if (callCount <= 181) {
        return Promise.resolve(automaticDrill)
      }
      if (callCount === 182) {
        return reload.promise
      }
      return Promise.resolve(nextRouteDrill)
    })
    vi.useFakeTimers()

    renderDrillAdmin({ withRouteSwitch: true })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    for (let attempt = 0; attempt < 180; attempt += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000)
      })
    }

    fireEvent.click(screen.getByRole('button', { name: '状態を再読み込み' }))
    fireEvent.click(screen.getByRole('button', { name: '別のドリルへ移動' }))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByText('/drills/next-route')).toBeTruthy()

    await act(async () => {
      reload.resolve(oldRoutePatch)
      await reload.promise
    })

    expect(screen.getByText('/drills/next-route')).toBeTruthy()
    expect(screen.queryByText('Automatic Patch Review')).toBeNull()
  })

  it('ignores a timed-out reload response after unmount', async () => {
    const automaticDrill = automaticRunningDrill()
    const reload = deferred<DrillAdmin>()
    const analyzedWithPatch: DrillAdmin = {
      ...automaticDrill,
      status: 'analyzed',
      latestPatchId: 'patch-auto',
    }
    mocks.getDrill.mockImplementation(() =>
      mocks.getDrill.mock.calls.length <= 181 ? Promise.resolve(automaticDrill) : reload.promise,
    )
    vi.useFakeTimers()

    renderDrillAdmin({ withUnmountControl: true })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    for (let attempt = 0; attempt < 180; attempt += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000)
      })
    }

    fireEvent.click(screen.getByRole('button', { name: '状態を再読み込み' }))
    expect(mocks.getDrill).toHaveBeenCalledTimes(182)
    fireEvent.click(screen.getByRole('button', { name: 'Drill Adminをunmount' }))
    expect(screen.getByText('Drill Admin Unmounted')).toBeTruthy()

    await act(async () => {
      reload.resolve(analyzedWithPatch)
      await reload.promise
      await vi.advanceTimersByTimeAsync(10_000)
    })

    expect(mocks.getDrill).toHaveBeenCalledTimes(182)
    expect(screen.getByText('Drill Admin Unmounted')).toBeTruthy()
    expect(screen.queryByText('Automatic Patch Review')).toBeNull()
  })

  it('clears the pending automatic poll when unmounted', async () => {
    mocks.getDrill.mockResolvedValue(automaticRunningDrill())
    vi.useFakeTimers()

    const { unmount } = renderDrillAdmin()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(mocks.getDrill).toHaveBeenCalledTimes(1)

    unmount()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })

    expect(mocks.getDrill).toHaveBeenCalledTimes(1)
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
