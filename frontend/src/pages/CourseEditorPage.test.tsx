import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CourseEditorPage } from './CourseEditorPage'

const mocks = vi.hoisted(() => ({
  createCourse: vi.fn(),
  getCourse: vi.fn(),
  getCourseMetrics: vi.fn(),
  updateCourse: vi.fn(),
  generateDrill: vi.fn(),
  deleteCourse: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: {
    createCourse: mocks.createCourse,
    getCourse: mocks.getCourse,
    getCourseMetrics: mocks.getCourseMetrics,
    updateCourse: mocks.updateCourse,
    generateDrill: mocks.generateDrill,
    deleteCourse: mocks.deleteCourse,
  },
  ApiClientError: class ApiClientError extends Error {},
}))

describe('CourseEditorPage', () => {
  beforeEach(() => {
    mocks.createCourse.mockReset()
    mocks.getCourse.mockReset()
    mocks.getCourseMetrics.mockReset()
    mocks.updateCourse.mockReset()
    mocks.generateDrill.mockReset()
    mocks.deleteCourse.mockReset()
    mocks.getCourseMetrics.mockResolvedValue({ courseId: 'course-1', runs: [] })
  })

  afterEach(() => {
    cleanup()
  })

  it('shows confidential material warning and validates empty title', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <CourseEditorPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('MVP 検証では本物の機密社内資料を入力しないでください。')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: '保存する' }))

    expect(screen.getByText('タイトルが必要です。')).toBeTruthy()
  })

  it('saves drill focus in the course payload', async () => {
    const user = userEvent.setup()
    mocks.createCourse.mockResolvedValueOnce({ courseId: 'course-1' })
    mocks.getCourse.mockResolvedValueOnce({
      id: 'course-1',
      title: '講座',
      markdown: '# Body',
      drillFocus: '例外条件を重点的に出す',
      version: 1,
      latestDrillRunId: null,
      latestPatchId: null,
    })
    render(
      <MemoryRouter>
        <CourseEditorPage />
      </MemoryRouter>,
    )

    await user.type(screen.getByLabelText('講座タイトル'), '講座')
    await user.type(screen.getByLabelText(/教材 Markdown/), '# Body')
    await user.type(screen.getByLabelText(/出題観点/), '例外条件を重点的に出す')
    await user.click(screen.getByRole('button', { name: '保存する' }))

    await waitFor(() =>
      expect(mocks.createCourse).toHaveBeenCalledWith({
        title: '講座',
        markdown: '# Body',
        drillFocus: '例外条件を重点的に出す',
      }),
    )
  })

  it('blocks saving when drill focus exceeds 500 characters', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <CourseEditorPage />
      </MemoryRouter>,
    )

    await user.type(screen.getByLabelText('講座タイトル'), '講座')
    await user.type(screen.getByLabelText(/教材 Markdown/), '# Body')
    await user.type(screen.getByLabelText(/出題観点/), 'あ'.repeat(501))
    await user.click(screen.getByRole('button', { name: '保存する' }))

    expect(screen.getByText('出題観点は 500 文字以内で入力してください。')).toBeTruthy()
    expect(mocks.createCourse).not.toHaveBeenCalled()
  })

  it('loads saved drill focus into the form', async () => {
    mocks.getCourse.mockResolvedValueOnce({
      id: 'course-1',
      title: '講座',
      markdown: '# Body',
      drillFocus: '業務上の判断基準',
      version: 2,
      latestDrillRunId: null,
      latestPatchId: null,
    })

    render(
      <MemoryRouter initialEntries={['/courses/course-1']}>
        <Routes>
          <Route path="/courses/:courseId" element={<CourseEditorPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      const field = screen.getByLabelText(/出題観点/) as HTMLTextAreaElement
      expect(field.value).toBe('業務上の判断基準')
    })
  })

  it('shows score progression for all scored runs using score-rate deltas', async () => {
    mocks.getCourse.mockResolvedValueOnce({
      id: 'course-1',
      title: '講座',
      markdown: '# Body',
      drillFocus: null,
      version: 3,
      latestDrillRunId: 'drill-3',
      latestPatchId: 'patch-1',
    })
    mocks.getCourseMetrics.mockResolvedValueOnce({
      courseId: 'course-1',
      runs: [
        {
          drillRunId: 'drill-3',
          courseVersion: 3,
          answerCount: 5,
          averageScore: 3,
          maxScore: 5,
        },
        {
          drillRunId: 'drill-1',
          courseVersion: 1,
          answerCount: 3,
          averageScore: 2,
          maxScore: 4,
        },
        {
          drillRunId: 'drill-2',
          courseVersion: 2,
          answerCount: 4,
          averageScore: 3,
          maxScore: 4,
        },
        {
          drillRunId: 'drill-4',
          courseVersion: 4,
          answerCount: 0,
          averageScore: null,
          maxScore: null,
        },
      ],
    })

    render(
      <MemoryRouter initialEntries={['/courses/course-1']}>
        <Routes>
          <Route path="/courses/:courseId" element={<CourseEditorPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByText('スコアの推移')
    const metricsCard = screen.getByLabelText('改善メトリクス')
    expect(within(metricsCard).getByRole('img', { name: 'バージョンごとのスコア率の推移' })).toBeTruthy()
    expect(within(metricsCard).getByText('v1')).toBeTruthy()
    expect(within(metricsCard).getByText('v2')).toBeTruthy()
    expect(within(metricsCard).getByText('v3')).toBeTruthy()
    expect(within(metricsCard).getByText('2.0 / 4 点')).toBeTruthy()
    expect(within(metricsCard).getByText('3.0 / 4 点')).toBeTruthy()
    expect(within(metricsCard).getByText('3.0 / 5 点')).toBeTruthy()
    expect(within(metricsCard).getByText('回答 3 件')).toBeTruthy()
    expect(within(metricsCard).getByText('+25.0 pp')).toBeTruthy()
    expect(within(metricsCard).getByText('-15.0 pp')).toBeTruthy()
    expect(within(metricsCard).getByText('+10.0 pp')).toBeTruthy()

    const cardText = metricsCard.textContent ?? ''
    expect(cardText.indexOf('v1')).toBeLessThan(cardText.indexOf('v2'))
    expect(cardText.indexOf('v2')).toBeLessThan(cardText.indexOf('v3'))
    expect(screen.getByRole('link', { name: 'レビュー →' }).getAttribute('href')).toBe(
      '/patches/patch-1',
    )
  })

  it('filters unscored and invalid runs out of score progression', async () => {
    mocks.getCourse.mockResolvedValueOnce({
      id: 'course-1',
      title: '講座',
      markdown: '# Body',
      drillFocus: null,
      version: 2,
      latestDrillRunId: 'drill-2',
      latestPatchId: null,
    })
    mocks.getCourseMetrics.mockResolvedValueOnce({
      courseId: 'course-1',
      runs: [
        {
          drillRunId: 'drill-1',
          courseVersion: 1,
          answerCount: 3,
          averageScore: 2.5,
          maxScore: 4,
        },
        {
          drillRunId: 'drill-2',
          courseVersion: 2,
          answerCount: 0,
          averageScore: null,
          maxScore: null,
        },
        {
          drillRunId: 'drill-3',
          courseVersion: 3,
          answerCount: 2,
          averageScore: null,
          maxScore: 4,
        },
        {
          drillRunId: 'drill-4',
          courseVersion: 4,
          answerCount: 2,
          averageScore: 2,
          maxScore: 0,
        },
        {
          drillRunId: 'drill-5',
          courseVersion: 5,
          answerCount: 2,
          averageScore: 3,
          maxScore: 4,
        },
      ],
    })

    render(
      <MemoryRouter initialEntries={['/courses/course-1']}>
        <Routes>
          <Route path="/courses/:courseId" element={<CourseEditorPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByText('スコアの推移')
    const metricsCard = screen.getByLabelText('改善メトリクス')
    expect(within(metricsCard).getByText('v1')).toBeTruthy()
    expect(within(metricsCard).getByText('v5')).toBeTruthy()
    expect(within(metricsCard).queryByText('v2')).toBeNull()
    expect(within(metricsCard).queryByText('v3')).toBeNull()
    expect(within(metricsCard).queryByText('v4')).toBeNull()
  })

  it('hides score progression when fewer than two eligible runs exist', async () => {
    mocks.getCourse.mockResolvedValueOnce({
      id: 'course-1',
      title: '講座',
      markdown: '# Body',
      drillFocus: null,
      version: 2,
      latestDrillRunId: 'drill-2',
      latestPatchId: null,
    })
    mocks.getCourseMetrics.mockResolvedValueOnce({
      courseId: 'course-1',
      runs: [
        {
          drillRunId: 'drill-1',
          courseVersion: 1,
          answerCount: 3,
          averageScore: 2.5,
          maxScore: 4,
        },
        {
          drillRunId: 'drill-2',
          courseVersion: 2,
          answerCount: 2,
          averageScore: 2,
          maxScore: 0,
        },
      ],
    })

    render(
      <MemoryRouter initialEntries={['/courses/course-1']}>
        <Routes>
          <Route path="/courses/:courseId" element={<CourseEditorPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      const field = screen.getByLabelText('講座タイトル') as HTMLInputElement
      expect(field.value).toBe('講座')
    })
    expect(screen.queryByText('スコアの推移')).toBeNull()
  })

  it('continues showing the editor when metrics loading fails', async () => {
    mocks.getCourse.mockResolvedValueOnce({
      id: 'course-1',
      title: '講座',
      markdown: '# Body',
      drillFocus: null,
      version: 2,
      latestDrillRunId: 'drill-2',
      latestPatchId: null,
    })
    mocks.getCourseMetrics.mockRejectedValueOnce(new Error('metrics failed'))

    render(
      <MemoryRouter initialEntries={['/courses/course-1']}>
        <Routes>
          <Route path="/courses/:courseId" element={<CourseEditorPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      const field = screen.getByLabelText('講座タイトル') as HTMLInputElement
      expect(field.value).toBe('講座')
    })
    expect(screen.queryByText('スコアの推移')).toBeNull()
  })

  it('uses warning tone when the total score rate goes down', async () => {
    mocks.getCourse.mockResolvedValueOnce({
      id: 'course-1',
      title: '講座',
      markdown: '# Body',
      drillFocus: null,
      version: 2,
      latestDrillRunId: 'drill-2',
      latestPatchId: null,
    })
    mocks.getCourseMetrics.mockResolvedValueOnce({
      courseId: 'course-1',
      runs: [
        {
          drillRunId: 'drill-1',
          courseVersion: 1,
          answerCount: 3,
          averageScore: 3,
          maxScore: 4,
        },
        {
          drillRunId: 'drill-2',
          courseVersion: 2,
          answerCount: 4,
          averageScore: 2,
          maxScore: 4,
        },
      ],
    })

    render(
      <MemoryRouter initialEntries={['/courses/course-1']}>
        <Routes>
          <Route path="/courses/:courseId" element={<CourseEditorPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByText('スコアの推移')
    const metricsCard = screen.getByLabelText('改善メトリクス')
    const totalDelta = metricsCard.querySelector('.card__head .chip')
    expect(totalDelta?.textContent).toBe('-25.0 pp')
    expect(totalDelta?.className).toContain('chip--warning')
  })

  it('deletes a course after two-step confirmation and navigates to course list', async () => {
    const user = userEvent.setup()
    mocks.getCourse.mockResolvedValueOnce({
      id: 'course-1',
      title: '講座',
      markdown: '# Body',
      drillFocus: null,
      version: 1,
      latestDrillRunId: null,
      latestPatchId: null,
    })
    mocks.deleteCourse.mockResolvedValueOnce(undefined)

    render(
      <MemoryRouter initialEntries={['/courses/course-1']}>
        <Routes>
          <Route path="/courses/:courseId" element={<CourseEditorPage />} />
          <Route path="/courses" element={<div>講座一覧へ戻りました</div>} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByDisplayValue('講座')
    await user.click(screen.getByRole('button', { name: '講座を削除' }))
    expect(mocks.deleteCourse).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: '本当に削除する' }))

    await waitFor(() => expect(mocks.deleteCourse).toHaveBeenCalledWith('course-1'))
    await screen.findByText('講座一覧へ戻りました')
  })

  it('shows an error banner when course deletion fails', async () => {
    const user = userEvent.setup()
    mocks.getCourse.mockResolvedValueOnce({
      id: 'course-1',
      title: '講座',
      markdown: '# Body',
      drillFocus: null,
      version: 1,
      latestDrillRunId: null,
      latestPatchId: null,
    })
    mocks.deleteCourse.mockRejectedValueOnce(new Error('delete failed'))

    render(
      <MemoryRouter initialEntries={['/courses/course-1']}>
        <Routes>
          <Route path="/courses/:courseId" element={<CourseEditorPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByDisplayValue('講座')
    await user.click(screen.getByRole('button', { name: '講座を削除' }))
    await user.click(screen.getByRole('button', { name: '本当に削除する' }))

    await screen.findByText('処理に失敗しました。')
  })
})
