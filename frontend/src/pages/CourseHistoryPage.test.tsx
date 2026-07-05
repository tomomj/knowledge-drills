import { cleanup, render, screen, waitFor } from '@testing-library/react'
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
  diffCourseRevisions: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: {
    listCourseRevisions: mocks.listCourseRevisions,
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
    mocks.diffCourseRevisions.mockReset()
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
})
