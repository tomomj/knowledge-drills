import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '../api/client'
import type { LearnerDrill, SubmitAnswerResponse } from '../api/types'
import { LearnerDrillPage } from './LearnerDrillPage'

const learnerDrill: LearnerDrill = {
  drillRunId: 'drill-1',
  courseId: 'course-1',
  courseTitle: '経費精算の判断基準',
  courseMarkdown: '# 経費精算\n\n## 基本方針\n業務に直接関係する支出を申請できます。',
  courseVersion: 2,
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

async function proceedToAnswering(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('button', { name: '教材を読んで始める' })
  await user.click(screen.getByRole('button', { name: '教材を読んで始める' }))
  await screen.findByRole('button', { name: '回答に進む' })
  await user.click(screen.getByRole('button', { name: '回答に進む' }))
}

describe('LearnerDrillPage', () => {
  beforeEach(() => {
    mocks.getLearnerDrill.mockReset()
    mocks.submitAnswer.mockReset()
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders learner questions without rubric or ideal answer', async () => {
    const user = userEvent.setup()
    mocks.getLearnerDrill.mockResolvedValueOnce(learnerDrill)

    renderLearner()

    await proceedToAnswering(user)
    await waitFor(() => expect(screen.getByLabelText(/判断理由を書いてください。/)).toBeTruthy())
    expect(screen.getAllByRole('textbox')).toHaveLength(4)
    expect(screen.queryByText('rubric')).toBeNull()
    expect(screen.queryByText('idealAnswer')).toBeNull()
  })

  it('starts with a one-page guide before showing the course material', async () => {
    const user = userEvent.setup()
    mocks.getLearnerDrill.mockResolvedValueOnce(learnerDrill)

    renderLearner()

    await screen.findByRole('button', { name: '教材を読んで始める' })
    expect(screen.getByRole('heading', { name: '経費精算の判断基準' })).toBeTruthy()
    expect(screen.getByText('約5分')).toBeTruthy()
    expect(screen.getByText('3問')).toBeTruthy()
    expect(screen.getByText('教材を読む')).toBeTruthy()
    expect(screen.getByText('3問に回答する')).toBeTruthy()
    expect(screen.getByText('回答を提出する')).toBeTruthy()
    expect(
      screen.getByText('お名前と回答内容は講座の管理者が確認し、教材改善のために利用します。'),
    ).toBeTruthy()
    expect(screen.queryByText('業務に直接関係する支出を申請できます。')).toBeNull()
    expect(screen.queryByLabelText('お名前')).toBeNull()

    await user.click(screen.getByRole('button', { name: '教材を読んで始める' }))

    await screen.findByRole('button', { name: '回答に進む' })
    expect(screen.getByRole('heading', { name: '経費精算の判断基準' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: '基本方針' })).toBeTruthy()
    expect(screen.getByText('業務に直接関係する支出を申請できます。')).toBeTruthy()
    expect(screen.getByText('教材バージョン v2')).toBeTruthy()
    expect(screen.getByText('経費精算の判断基準').closest('details')).toBeNull()

    expect(screen.queryByText('教材を確認する')).toBeNull()
    expect(screen.queryByLabelText('お名前')).toBeNull()
    expect(screen.queryByText(/判断理由を書いてください。/)).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: '回答を提出する' })).toBeNull()
  })

  it('shows questions after proceeding, without any material reference', async () => {
    const user = userEvent.setup()
    mocks.getLearnerDrill.mockResolvedValueOnce(learnerDrill)

    renderLearner()

    await proceedToAnswering(user)

    await screen.findByLabelText(/判断理由を書いてください。/)
    expect(screen.getByLabelText('お名前')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '回答に進む' })).toBeNull()

    expect(screen.queryByText('教材を確認する')).toBeNull()
    expect(screen.queryByText('教材バージョン v2')).toBeNull()
    expect(screen.queryByText('業務に直接関係する支出を申請できます。')).toBeNull()
  })

  it('scrolls to the top after proceeding to the answer form', async () => {
    const user = userEvent.setup()
    mocks.getLearnerDrill.mockResolvedValueOnce(learnerDrill)

    renderLearner()

    await proceedToAnswering(user)

    expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' })
  })

  it('skips the reading step when courseMarkdown is empty', async () => {
    const user = userEvent.setup()
    mocks.getLearnerDrill.mockResolvedValueOnce({ ...learnerDrill, courseMarkdown: '' })

    renderLearner()

    await screen.findByRole('button', { name: '回答を始める' })
    expect(screen.queryByText('教材を読む')).toBeNull()
    await user.click(screen.getByRole('button', { name: '回答を始める' }))

    await screen.findByLabelText(/判断理由を書いてください。/)
    expect(screen.getByLabelText('お名前')).toBeTruthy()
    expect(screen.getByRole('button', { name: '回答を提出する' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '回答に進む' })).toBeNull()
    expect(screen.queryByText('教材を確認する')).toBeNull()
  })

  it('does not render drill content for invalid token', async () => {
    mocks.getLearnerDrill.mockRejectedValueOnce(
      new ApiClientError(404, { code: 'invalid_share_token', message: 'invalid' }),
    )

    renderLearner('/drills/bad-token')

    await waitFor(() => expect(screen.getByText('共有 URL が無効です。')).toBeTruthy())
    expect(screen.queryByText('判断理由を書いてください。')).toBeNull()
  })

  it('shows an answer-collection-ended state for a closed share URL', async () => {
    mocks.getLearnerDrill.mockRejectedValueOnce(
      new ApiClientError(410, { code: 'share_closed', message: 'closed' }),
    )

    renderLearner()

    await screen.findByText('このドリルの回答受付は終了しました。')
    expect(screen.getByText('ご協力ありがとうございました。')).toBeTruthy()
    expect(screen.queryByText('判断理由を書いてください。')).toBeNull()
  })

  it('shows validation error for empty fields', async () => {
    const user = userEvent.setup()
    mocks.getLearnerDrill.mockResolvedValueOnce(learnerDrill)

    renderLearner()

    await proceedToAnswering(user)
    await screen.findByLabelText(/判断理由を書いてください。/)
    await user.click(screen.getByRole('button', { name: '回答を提出する' }))

    expect(screen.getByText('受講者名が必要です。')).toBeTruthy()
    expect(mocks.submitAnswer).not.toHaveBeenCalled()
  })

  it('limits learner name and each answer while showing character counts', async () => {
    const user = userEvent.setup()
    mocks.getLearnerDrill.mockResolvedValueOnce(learnerDrill)

    renderLearner()

    await proceedToAnswering(user)
    const nameInput = screen.getByLabelText('お名前') as HTMLInputElement
    const answerInput = screen.getByLabelText(/判断理由を書いてください。/) as HTMLTextAreaElement
    expect(nameInput.maxLength).toBe(50)
    expect(answerInput.maxLength).toBe(2_000)
    expect(screen.getByLabelText('お名前の文字数').textContent).toContain('0 / 50 文字')
    expect(screen.getByLabelText('q1 の回答文字数').textContent).toContain('0 / 2,000 文字')

    await user.type(nameInput, '受講者A')
    await user.type(answerInput, '根拠です')
    expect(screen.getByLabelText('お名前の文字数').textContent).toContain('4 / 50 文字')
    expect(screen.getByLabelText('q1 の回答文字数').textContent).toContain('4 / 2,000 文字')
  })

  it('blocks oversized text before calling the API', async () => {
    const user = userEvent.setup()
    mocks.getLearnerDrill.mockResolvedValueOnce(learnerDrill)

    renderLearner()

    await proceedToAnswering(user)
    fireEvent.change(screen.getByLabelText('お名前'), { target: { value: '名'.repeat(51) } })
    await user.click(screen.getByRole('button', { name: '回答を提出する' }))
    expect(screen.getByText('受講者名は 50 文字以内で入力してください。')).toBeTruthy()
    expect(mocks.submitAnswer).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('お名前'), { target: { value: '受講者' } })
    fireEvent.change(screen.getByLabelText(/判断理由を書いてください。/), {
      target: { value: '回'.repeat(2_001) },
    })
    await user.click(screen.getByRole('button', { name: '回答を提出する' }))
    expect(screen.getByText('回答は 1 問 2,000 文字以内で入力してください。')).toBeTruthy()
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

    await proceedToAnswering(user)
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
    expect(screen.getByText('回答は教材改善の分析に使われます。')).toBeTruthy()
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

    await proceedToAnswering(user)
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

  it('switches to the closed state when collection ends before submit', async () => {
    const user = userEvent.setup()
    mocks.getLearnerDrill.mockResolvedValueOnce(learnerDrill)
    mocks.submitAnswer.mockRejectedValueOnce(
      new ApiClientError(410, { code: 'share_closed', message: 'closed' }),
    )

    renderLearner()

    await proceedToAnswering(user)
    await user.type(screen.getByLabelText('お名前'), '受講者A')
    await user.type(screen.getByLabelText(/判断理由を書いてください。/), '根拠です')
    await user.type(screen.getByLabelText(/例外条件を書いてください。/), '例外です')
    await user.type(screen.getByLabelText(/次の対応を書いてください。/), '対応です')
    await user.click(screen.getByRole('button', { name: '回答を提出する' }))

    await screen.findByText('このドリルの回答受付は終了しました。')
    expect(screen.getByText('ご協力ありがとうございました。')).toBeTruthy()
  })
})
