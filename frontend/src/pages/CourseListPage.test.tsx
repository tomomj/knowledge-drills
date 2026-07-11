import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { CourseSummary } from '../api/types'
import { CourseListPage } from './CourseListPage'

const courses: CourseSummary[] = [
  {
    id: 'course-1',
    title: '情報セキュリティ入門',
    version: 3,
    updatedAt: '2026-07-04T09:32:00Z',
    drillStatus: 'ready',
    answerCount: 12,
    patchStatus: 'proposed',
    latestDrillRunId: 'drill-1',
    latestPatchId: 'patch-1',
    scoreTrend: [
      { courseVersion: 1, averageScore: 1.0, maxScore: 4 },
      { courseVersion: 2, averageScore: 0.8, maxScore: 4 },
    ],
    isDemo: true,
    needsAnalysis: false,
  },
  {
    id: 'course-2',
    title: '新人向け Git 運用ルール',
    version: 1,
    updatedAt: '2026-06-25T03:00:00Z',
    drillStatus: null,
    answerCount: 0,
    patchStatus: null,
    latestDrillRunId: null,
    latestPatchId: null,
    scoreTrend: [{ courseVersion: 1, averageScore: 4.0, maxScore: 4 }],
    isDemo: false,
    needsAnalysis: false,
  },
]

const mocks = vi.hoisted(() => ({
  listCourses: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: {
    listCourses: mocks.listCourses,
  },
  ApiClientError: class ApiClientError extends Error {},
}))

function renderList() {
  render(
    <MemoryRouter initialEntries={['/courses']}>
      <CourseListPage />
    </MemoryRouter>,
  )
}

describe('CourseListPage', () => {
  beforeEach(() => {
    mocks.listCourses.mockReset()
  })

  afterEach(() => {
    cleanup()
  })

  it('renders course rows with status chips and links', async () => {
    mocks.listCourses.mockResolvedValueOnce({ courses })

    renderList()

    await waitFor(() => expect(screen.getByText('情報セキュリティ入門')).toBeTruthy())
    expect(screen.getByText('パッチ提案あり')).toBeTruthy()
    expect(screen.getByText('デモ')).toBeTruthy()
    expect(screen.getByText('分析できます')).toBeTruthy()
    expect(screen.getByText('ドリル配布中')).toBeTruthy()
    expect(screen.getByText('ドリル未生成')).toBeTruthy()
    expect(screen.queryByText('低スコア回答が蓄積 — 分析推奨')).toBeNull()
    expect(screen.getByText(/回答 12 件/)).toBeTruthy()
    expect(screen.getByText('体験用デモ講座を開くと、採点済み回答の分析と改善履歴をすぐ確認できます。')).toBeTruthy()
    expect(screen.getByRole('img', { name: '平均点の推移 1.0 から 0.8' })).toBeTruthy()
    expect(screen.getByText('平均 1.0 → 0.8')).toBeTruthy()
    expect(screen.queryByRole('img', { name: '平均点の推移 4.0 から 4.0' })).toBeNull()

    const links = screen.getAllByRole('link')
    const rowLink = links.find((link) => link.textContent?.includes('情報セキュリティ入門'))
    expect(rowLink?.getAttribute('href')).toBe('/courses/course-1')
  })

  it('replaces the analysis chip with a warning while preserving other chips', async () => {
    mocks.listCourses.mockResolvedValueOnce({
      courses: [{ ...courses[0], needsAnalysis: true }],
    })

    renderList()

    const warning = await screen.findByText('低スコア回答が蓄積 — 分析推奨')
    expect(warning.classList.contains('chip--warning')).toBe(true)
    expect(screen.queryByText('分析できます')).toBeNull()
    expect(screen.getByText('パッチ提案あり')).toBeTruthy()
    expect(screen.getByText('デモ')).toBeTruthy()
    expect(screen.getByText('ドリル配布中')).toBeTruthy()
  })

  it('filters courses by title', async () => {
    const user = userEvent.setup()
    mocks.listCourses.mockResolvedValueOnce({ courses })

    renderList()

    await screen.findByText('情報セキュリティ入門')
    await user.type(screen.getByLabelText('講座名で検索'), 'Git')

    expect(screen.queryByText('情報セキュリティ入門')).toBeNull()
    expect(screen.getByText('新人向け Git 運用ルール')).toBeTruthy()
    expect(screen.getByText('1 件の講座')).toBeTruthy()
  })

  it('shows empty state when there are no courses', async () => {
    mocks.listCourses.mockResolvedValueOnce({ courses: [] })

    renderList()

    await waitFor(() =>
      expect(
        screen.getByText('まだ講座がありません。資料を登録して最初のドリルを作りましょう。'),
      ).toBeTruthy(),
    )
    expect(screen.getByRole('button', { name: '＋ 新しい講座を作成' })).toBeTruthy()
  })
})
