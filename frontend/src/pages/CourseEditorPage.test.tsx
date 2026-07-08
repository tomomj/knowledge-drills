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
}))

vi.mock('../api/client', () => ({
  api: {
    createCourse: mocks.createCourse,
    getCourse: mocks.getCourse,
    getCourseMetrics: mocks.getCourseMetrics,
    updateCourse: mocks.updateCourse,
    generateDrill: mocks.generateDrill,
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

  it('shows before after metrics when at least two scored runs exist', async () => {
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
          answerCount: 4,
          averageScore: 3.5,
          maxScore: 4,
        },
        {
          drillRunId: 'drill-3',
          courseVersion: 3,
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

    await screen.findByText('Before / After')
    const metricsCard = screen.getByLabelText('改善メトリクス')
    expect(within(metricsCard).getByText('v1')).toBeTruthy()
    expect(within(metricsCard).getByText('v2')).toBeTruthy()
    expect(within(metricsCard).getByText('2.5 / 4 点')).toBeTruthy()
    expect(within(metricsCard).getByText('3.5 / 4 点')).toBeTruthy()
    expect(within(metricsCard).getByText('+1.0 点')).toBeTruthy()
  })

  it('hides before after metrics when fewer than two scored runs exist', async () => {
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
    expect(screen.queryByText('Before / After')).toBeNull()
  })
})
