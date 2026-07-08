import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CourseHistoryPage } from './CourseHistoryPage'

const revisions = [
  { version: 3, title: '講座', updatedAt: '2026-07-05T09:00:00Z' },
  { version: 2, title: '講座', updatedAt: '2026-07-04T09:00:00Z' },
  { version: 1, title: '講座', updatedAt: '2026-07-03T09:00:00Z' },
]

const mocks = vi.hoisted(() => ({
  listCourseRevisions: vi.fn(),
  getCourseMetrics: vi.fn(),
  diffCourseRevisions: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: {
    listCourseRevisions: mocks.listCourseRevisions,
    getCourseMetrics: mocks.getCourseMetrics,
    diffCourseRevisions: mocks.diffCourseRevisions,
  },
  ApiClientError: class ApiClientError extends Error {},
}))

function renderHistory() {
  render(
    <MemoryRouter initialEntries={['/courses/course-1/history']}>
      <Routes>
        <Route path="/courses/:courseId/history" element={<CourseHistoryPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('CourseHistoryPage', () => {
  beforeEach(() => {
    mocks.listCourseRevisions.mockReset()
    mocks.getCourseMetrics.mockReset()
    mocks.diffCourseRevisions.mockReset()
    mocks.getCourseMetrics.mockResolvedValue({ courseId: 'course-1', runs: [] })
  })

  afterEach(() => {
    cleanup()
  })

  it('shows latest diff by default and switches on version click', async () => {
    const user = userEvent.setup()
    mocks.listCourseRevisions.mockResolvedValueOnce({ revisions })
    mocks.diffCourseRevisions.mockImplementation(async (_courseId, from, to) => ({
      fromVersion: from,
      toVersion: to,
      diffText: `--- v${from}\n+++ v${to}\n-旧文\n+新文`,
    }))

    renderHistory()

    await waitFor(() =>
      expect(mocks.diffCourseRevisions).toHaveBeenCalledWith('course-1', 2, 3),
    )
    expect(screen.getByText('v2 → v3 の変更')).toBeTruthy()
    expect(screen.getByText('-旧文')).toBeTruthy()
    expect(screen.getByText('+新文')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: /v2/ }))
    await waitFor(() =>
      expect(mocks.diffCourseRevisions).toHaveBeenCalledWith('course-1', 1, 2),
    )
    expect(screen.getByText('v1 → v2 の変更')).toBeTruthy()
  })

  it('shows first-version message when v1 is selected', async () => {
    const user = userEvent.setup()
    mocks.listCourseRevisions.mockResolvedValueOnce({ revisions })
    mocks.diffCourseRevisions.mockResolvedValue({
      fromVersion: 2,
      toVersion: 3,
      diffText: '',
    })

    renderHistory()

    await screen.findByRole('button', { name: /v1/ })
    await user.click(screen.getByRole('button', { name: /v1/ }))

    expect(
      screen.getByText('v1 は最初のバージョンです。比較できる前のバージョンがありません。'),
    ).toBeTruthy()
  })

  it('shows single-revision state without diff request', async () => {
    mocks.listCourseRevisions.mockResolvedValueOnce({
      revisions: [revisions[2]],
    })

    renderHistory()

    await screen.findByRole('button', { name: /v1/ })
    expect(mocks.diffCourseRevisions).not.toHaveBeenCalled()
    expect(
      screen.getByText('v1 は最初のバージョンです。比較できる前のバージョンがありません。'),
    ).toBeTruthy()
  })

  it('adds the latest response-order score for each version row', async () => {
    mocks.listCourseRevisions.mockResolvedValueOnce({ revisions })
    mocks.getCourseMetrics.mockResolvedValueOnce({
      courseId: 'course-1',
      runs: [
        {
          drillRunId: 'drill-older',
          courseVersion: 3,
          answerCount: 2,
          averageScore: 2.5,
          maxScore: 4,
        },
        {
          drillRunId: 'drill-v1',
          courseVersion: 1,
          answerCount: 1,
          averageScore: 1.5,
          maxScore: 4,
        },
        {
          drillRunId: 'drill-later',
          courseVersion: 3,
          answerCount: 3,
          averageScore: 3.5,
          maxScore: 4,
        },
      ],
    })
    mocks.diffCourseRevisions.mockResolvedValue({
      fromVersion: 2,
      toVersion: 3,
      diffText: '',
    })

    renderHistory()

    const v3Row = await screen.findByRole('button', { name: /v3/ })
    expect(within(v3Row).getByText(/平均 3\.5 \/ 4 点/)).toBeTruthy()
    expect(within(v3Row).queryByText(/平均 2\.5 \/ 4 点/)).toBeNull()
    expect(within(v3Row).getByText(/ · /)).toBeTruthy()
  })

  it('omits averages for versions without an eligible scored run', async () => {
    mocks.listCourseRevisions.mockResolvedValueOnce({ revisions })
    mocks.getCourseMetrics.mockResolvedValueOnce({
      courseId: 'course-1',
      runs: [
        {
          drillRunId: 'drill-v2',
          courseVersion: 2,
          answerCount: 0,
          averageScore: null,
          maxScore: null,
        },
        {
          drillRunId: 'drill-v3',
          courseVersion: 3,
          answerCount: 3,
          averageScore: 3,
          maxScore: 0,
        },
      ],
    })
    mocks.diffCourseRevisions.mockResolvedValue({
      fromVersion: 2,
      toVersion: 3,
      diffText: '',
    })

    renderHistory()

    const v2Row = await screen.findByRole('button', { name: /v2/ })
    const v3Row = screen.getByRole('button', { name: /v3/ })
    expect(within(v2Row).queryByText(/平均/)).toBeNull()
    expect(within(v3Row).queryByText(/平均/)).toBeNull()
  })

  it('keeps history and diff visible when metrics loading fails', async () => {
    mocks.listCourseRevisions.mockResolvedValueOnce({ revisions })
    mocks.getCourseMetrics.mockRejectedValueOnce(new Error('metrics failed'))
    mocks.diffCourseRevisions.mockResolvedValue({
      fromVersion: 2,
      toVersion: 3,
      diffText: '--- v2\n+++ v3\n+新文',
    })

    renderHistory()

    const v3Row = await screen.findByRole('button', { name: /v3/ })
    expect(within(v3Row).queryByText(/平均/)).toBeNull()
    await waitFor(() =>
      expect(mocks.diffCourseRevisions).toHaveBeenCalledWith('course-1', 2, 3),
    )
    expect(screen.getByText('v2 → v3 の変更')).toBeTruthy()
    expect(screen.getByText('+新文')).toBeTruthy()
  })
})
