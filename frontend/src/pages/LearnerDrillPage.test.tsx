import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '../api/client'
import type { LearnerDrill, SubmitAnswerResponse } from '../api/types'
import { LearnerDrillPage } from './LearnerDrillPage'

const learnerDrill: LearnerDrill = {
  drillRunId: 'drill-1',
  courseId: 'course-1',
  questions: [
    { id: 'q1', question: '判断理由を書いてください。', maxScore: 4 },
    { id: 'q2', question: '例外条件を書いてください。', maxScore: 4 },
    { id: 'q3', question: '次の対応を書いてください。', maxScore: 4 },
  ],
}

const mocks = vi.hoisted(() => ({
  getLearnerDrill: vi.fn(),
  submitAnswer: vi.fn(),
  ApiClientError: class ApiClientError extends Error {
    error: { code: string; message: string }
    status: number

    constructor(status: number, error: { code: string; message: string }) {
      super(error.message)
      this.status = status
      this.error = error
    }
  },
}))

vi.mock('../api/client', () => ({
  api: {
    getLearnerDrill: mocks.getLearnerDrill,
    submitAnswer: mocks.submitAnswer,
  },
  ApiClientError: mocks.ApiClientError,
}))

function renderLearner(path = '/drills/share-token') {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/drills/:shareToken" element={<LearnerDrillPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('LearnerDrillPage', () => {
  beforeEach(() => {
    mocks.getLearnerDrill.mockReset()
    mocks.submitAnswer.mockReset()
  })

  afterEach(() => {
    cleanup()
  })

  it('renders learner questions without rubric or ideal answer', async () => {
    mocks.getLearnerDrill.mockResolvedValueOnce(learnerDrill)

    renderLearner()

    await waitFor(() => expect(screen.getByLabelText(/判断理由を書いてください。/)).toBeTruthy())
    expect(screen.getAllByRole('textbox')).toHaveLength(4)
    expect(screen.queryByText('rubric')).toBeNull()
    expect(screen.queryByText('idealAnswer')).toBeNull()
  })

  it('does not render drill content for invalid token', async () => {
    mocks.getLearnerDrill.mockRejectedValueOnce(
      new ApiClientError(404, { code: 'invalid_share_token', message: 'invalid' }),
    )

    renderLearner('/drills/bad-token')

    await waitFor(() => expect(screen.getByText('共有 URL が無効です。')).toBeTruthy())
    expect(screen.queryByText('判断理由を書いてください。')).toBeNull()
  })

  it('shows validation error for empty fields', async () => {
    const user = userEvent.setup()
    mocks.getLearnerDrill.mockResolvedValueOnce(learnerDrill)

    renderLearner()

    await screen.findByLabelText(/判断理由を書いてください。/)
    await user.click(screen.getByRole('button', { name: '回答を提出する' }))

    expect(screen.getByText('受講者名が必要です。')).toBeTruthy()
    expect(mocks.submitAnswer).not.toHaveBeenCalled()
  })

  it('submits valid answer and renders minimal feedback', async () => {
    const user = userEvent.setup()
    mocks.getLearnerDrill.mockResolvedValueOnce(learnerDrill)
    mocks.submitAnswer.mockResolvedValueOnce({
      answerId: 'answer-1',
      status: 'graded',
      feedback: ['根拠が明確です。'],
    })

    renderLearner()

    await screen.findByLabelText(/判断理由を書いてください。/)
    await user.type(screen.getByLabelText('お名前'), '受講者A')
    await user.type(screen.getByLabelText(/判断理由を書いてください。/), '根拠です')
    await user.type(screen.getByLabelText(/例外条件を書いてください。/), '例外です')
    await user.type(screen.getByLabelText(/次の対応を書いてください。/), '対応です')
    await user.click(screen.getByRole('button', { name: '回答を提出する' }))

    expect(mocks.submitAnswer).toHaveBeenCalledWith('share-token', {
      learnerName: '受講者A',
      answers: [
        { questionId: 'q1', answerText: '根拠です' },
        { questionId: 'q2', answerText: '例外です' },
        { questionId: 'q3', answerText: '対応です' },
      ],
    })
    await waitFor(() => expect(screen.getByText('提出が完了しました。')).toBeTruthy())
    expect(screen.getByText('根拠が明確です。')).toBeTruthy()
    expect(screen.queryByText('idealAnswer')).toBeNull()
  })

  it('hides the submit button and locks fields while submission is pending', async () => {
    const user = userEvent.setup()
    let resolveSubmit: (value: SubmitAnswerResponse) => void = () => {}
    mocks.getLearnerDrill.mockResolvedValueOnce(learnerDrill)
    mocks.submitAnswer.mockReturnValueOnce(
      new Promise<SubmitAnswerResponse>((resolve) => {
        resolveSubmit = resolve
      }),
    )

    renderLearner()

    await screen.findByLabelText(/判断理由を書いてください。/)
    await user.type(screen.getByLabelText('お名前'), '受講者A')
    await user.type(screen.getByLabelText(/判断理由を書いてください。/), '根拠です')
    await user.type(screen.getByLabelText(/例外条件を書いてください。/), '例外です')
    await user.type(screen.getByLabelText(/次の対応を書いてください。/), '対応です')
    await user.click(screen.getByRole('button', { name: '回答を提出する' }))

    expect(mocks.submitAnswer).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('button', { name: '回答を提出する' })).toBeNull()
    expect(screen.getByText('回答を提出しています。')).toBeTruthy()
    expect((screen.getByLabelText('お名前') as HTMLInputElement).disabled).toBe(true)

    resolveSubmit({
      answerId: 'answer-1',
      status: 'graded',
      feedback: ['受付しました。'],
    })
    await waitFor(() => expect(screen.getByText('提出が完了しました。')).toBeTruthy())
  })
})
