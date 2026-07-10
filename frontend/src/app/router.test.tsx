import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { CurrentUser, LearnerDrill } from '../api/types'
import type { AuthStateProvider, AuthStateUser } from '../lib/authState'
import { AppRouter } from './router'

const currentUser: CurrentUser = {
  uid: 'owner-1',
  email: 'owner@example.test',
  displayName: 'Owner',
  photoUrl: null,
  createdAt: '2026-07-07T00:00:00+00:00',
  lastLoginAt: '2026-07-07T00:00:00+00:00',
  demoSeededAt: null,
}

const firebaseUser: AuthStateUser = {
  uid: 'owner-1',
  email: 'owner@example.test',
  displayName: 'Owner',
  photoUrl: null,
  getIdToken: async () => 'id-token',
}

const learnerDrill: LearnerDrill = {
  drillRunId: 'drill-1',
  courseId: 'course-1',
  courseTitle: '教材タイトル',
  courseMarkdown: '# 教材\n\n## 方針\n根拠を確認します。',
  courseVersion: 1,
  questions: [
    { id: 'q1', question: '判断理由を書いてください。', maxScore: 4 },
    { id: 'q2', question: '例外条件を書いてください。', maxScore: 4 },
    { id: 'q3', question: '次の対応を書いてください。', maxScore: 4 },
  ],
}

const mocks = vi.hoisted(() => ({
  listCourses: vi.fn(),
  getLearnerDrill: vi.fn(),
  submitAnswer: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: {
    listCourses: mocks.listCourses,
    getLearnerDrill: mocks.getLearnerDrill,
    submitAnswer: mocks.submitAnswer,
  },
  ApiClientError: class ApiClientError extends Error {
    status = 500
    error = { code: 'error', message: 'error' }
  },
}))

function authStateProvider(user: AuthStateUser | null): AuthStateProvider {
  return (listener) => {
    listener(user)
    return () => undefined
  }
}

function renderRoute(path: string, user: AuthStateUser | null) {
  window.history.pushState({}, '', path)
  const confirmCurrentUser = vi.fn<() => Promise<CurrentUser>>().mockResolvedValue(currentUser)
  const signOutAction = vi.fn().mockResolvedValue(undefined)
  render(
    <AppRouter
      ownerAuth={{
        authStateProvider: authStateProvider(user),
        confirmCurrentUser,
        signInWithGoogleAction: vi.fn().mockResolvedValue(undefined),
        signOutAction,
      }}
    />,
  )
  return { confirmCurrentUser, signOutAction }
}

describe('AppRouter auth boundaries', () => {
  beforeEach(() => {
    mocks.listCourses.mockReset()
    mocks.getLearnerDrill.mockReset()
    mocks.submitAnswer.mockReset()
  })

  afterEach(() => {
    cleanup()
    window.history.pushState({}, '', '/')
  })

  it('shows login UI instead of management routes when signed out', async () => {
    const { confirmCurrentUser } = renderRoute('/courses', null)

    expect(await screen.findByRole('button', { name: 'Google でログイン' })).toBeTruthy()
    expect(screen.queryByText('講座一覧')).toBeNull()
    expect(confirmCurrentUser).not.toHaveBeenCalled()
    expect(mocks.listCourses).not.toHaveBeenCalled()
  })

  it('keeps learner share routes public', async () => {
    mocks.getLearnerDrill.mockResolvedValueOnce(learnerDrill)
    const { confirmCurrentUser } = renderRoute('/drills/share-token', null)

    await waitFor(() => expect(screen.getByLabelText(/判断理由を書いてください。/)).toBeTruthy())

    expect(screen.queryByRole('button', { name: 'Google でログイン' })).toBeNull()
    expect(confirmCurrentUser).not.toHaveBeenCalled()
  })

  it('shows logout on owner routes', async () => {
    const user = userEvent.setup()
    mocks.listCourses.mockResolvedValueOnce({ courses: [] })
    const { signOutAction } = renderRoute('/courses', firebaseUser)

    await user.click(await screen.findByRole('button', { name: 'ログアウト' }))

    expect(signOutAction).toHaveBeenCalledOnce()
  })
})
