import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CurrentUser } from '../api/types'
import type { AuthStateProvider, AuthStateUser } from '../lib/authState'
import { AuthGate, AuthProvider } from './AuthProvider'

const firebaseUser: AuthStateUser = {
  uid: 'owner-1',
  email: 'owner@example.test',
  displayName: 'Owner',
  photoUrl: 'https://example.test/owner.png',
  getIdToken: async () => 'id-token',
}

const currentUser: CurrentUser = {
  uid: 'owner-1',
  email: 'owner@example.test',
  displayName: 'Owner',
  photoUrl: 'https://example.test/owner.png',
  createdAt: '2026-07-07T00:00:00+00:00',
  lastLoginAt: '2026-07-07T00:00:00+00:00',
}

function authStateProvider(user: AuthStateUser | null): AuthStateProvider {
  return (listener) => {
    listener(user)
    return () => undefined
  }
}

function renderGate({
  user,
  confirmCurrentUser = vi.fn().mockResolvedValue(currentUser),
  signInWithGoogleAction = vi.fn().mockResolvedValue(undefined),
}: {
  user: AuthStateUser | null
  confirmCurrentUser?: () => Promise<CurrentUser>
  signInWithGoogleAction?: () => Promise<void>
}) {
  render(
    <AuthProvider
      authStateProvider={authStateProvider(user)}
      confirmCurrentUser={confirmCurrentUser}
      signInWithGoogleAction={signInWithGoogleAction}
    >
      <AuthGate>
        <div>管理画面</div>
      </AuthGate>
    </AuthProvider>,
  )
}

describe('AuthProvider', () => {
  afterEach(() => {
    cleanup()
  })

  it('shows the Google login action when signed out', async () => {
    const signInWithGoogleAction = vi.fn().mockResolvedValue(undefined)
    renderGate({ user: null, signInWithGoogleAction })

    await userEvent.click(screen.getByRole('button', { name: 'Google でログイン' }))

    expect(screen.queryByText('管理画面')).toBeNull()
    expect(signInWithGoogleAction).toHaveBeenCalledOnce()
  })

  it('confirms the backend current user before showing children', async () => {
    const confirmCurrentUser = vi.fn().mockResolvedValue(currentUser)

    renderGate({ user: firebaseUser, confirmCurrentUser })

    expect(await screen.findByText('管理画面')).toBeTruthy()
    expect(confirmCurrentUser).toHaveBeenCalledOnce()
  })

  it('keeps children hidden when backend confirmation fails and can retry', async () => {
    const confirmCurrentUser = vi
      .fn<() => Promise<CurrentUser>>()
      .mockRejectedValueOnce(new Error('backend failed'))
      .mockResolvedValueOnce(currentUser)

    renderGate({ user: firebaseUser, confirmCurrentUser })

    expect(await screen.findByText('ログインを確認できませんでした。')).toBeTruthy()
    expect(screen.queryByText('管理画面')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: '再試行' }))

    expect(await screen.findByText('管理画面')).toBeTruthy()
    expect(confirmCurrentUser).toHaveBeenCalledTimes(2)
  })
})
