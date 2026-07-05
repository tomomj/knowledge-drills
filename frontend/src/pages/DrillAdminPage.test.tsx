import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { DrillAdmin } from '../api/types'
import { DrillAdminPage } from './DrillAdminPage'

const drill: DrillAdmin = {
  id: 'drill-1',
  courseId: 'course-1',
  courseVersion: 2,
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
  answerCount: 1,
  canAnalyze: true,
  errorMessage: null,
}

vi.mock('../api/client', () => ({
  api: {
    getDrill: vi.fn(async () => drill),
    getDrillAnswers: vi.fn(async () => ({
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
              missingPoints: [],
              feedback: '例外条件も添えてください。',
              failureTags: [],
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
    })),
    analyzeDrill: vi.fn(),
  },
  ApiClientError: class ApiClientError extends Error {},
}))

describe('DrillAdminPage', () => {
  afterEach(() => {
    cleanup()
  })

  it('shows share URL, answer count, rubric summary, and analyze button', async () => {
    render(
      <MemoryRouter initialEntries={['/courses/course-1/drill-runs/drill-1']}>
        <Routes>
          <Route
            path="/courses/:courseId/drill-runs/:drillRunId"
            element={<DrillAdminPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('/drills/share-token')).toBeTruthy())
    expect(screen.getByText('回答数')).toBeTruthy()
    expect(screen.getAllByText('判断理由を書いてください。').length).toBeGreaterThan(0)
    expect(screen.getByText('根拠')).toBeTruthy()
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

  it('switches selected answer and filters by learner name', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/courses/course-1/drill-runs/drill-1']}>
        <Routes>
          <Route
            path="/courses/:courseId/drill-runs/:drillRunId"
            element={<DrillAdminPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByRole('button', { name: /受講者B/ })
    await user.click(screen.getByRole('button', { name: /受講者B/ }))

    expect(screen.getByText('採点待ちの回答です')).toBeTruthy()
    expect(screen.getAllByText('採点中').length).toBeGreaterThan(0)

    await user.type(screen.getByLabelText('回答者名で検索'), '受講者A')
    expect(screen.getByText('1 / 2 件')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /受講者B/ })).toBeNull()
  })
})
