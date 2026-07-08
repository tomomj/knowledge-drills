import { act, cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CurrentUser } from '../api/types'
import { clearAuthUnauthorizedListeners, notifyAuthUnauthorized } from '../lib/authEvents'
import type { AuthStateProvider, AuthStateUser } from '../lib/authState'
import { useAuth } from './AuthContext'
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
  demoSeededAt: null,
}

function authStateProvider(user: AuthStateUser | null): AuthStateProvider {
  return (listener) => {
    listener(user)
    return () => undefined
  }
}

function controllableAuthStateProvider(initialUser: AuthStateUser | null) {
  let listener: ((user: AuthStateUser | null) => void) | null = null
  const provider: AuthStateProvider = (next) => {
    listener = next
    next(initialUser)
    return () => {
      listener = null
    }
  }
  return {
    provider,
    emit: (user: AuthStateUser | null) => {
      listener?.(user)
    },
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

function LogoutButton() {
  const auth = useAuth()
  return (
    <button type="button" onClick={() => void auth.signOut()}>
      ログアウト
    </button>
  )
}

describe('AuthProvider', () => {
  afterEach(() => {
    clearAuthUnauthorizedListeners()
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

  it('signs out and returns to the login action', async () => {
    const authState = controllableAuthStateProvider(firebaseUser)
    const signOutAction = vi.fn(async () => {
      authState.emit(null)
    })
    render(
      <AuthProvider
        authStateProvider={authState.provider}
        confirmCurrentUser={vi.fn().mockResolvedValue(currentUser)}
        signOutAction={signOutAction}
      >
        <AuthGate>
          <LogoutButton />
        </AuthGate>
      </AuthProvider>,
    )

    await userEvent.click(await screen.findByRole('button', { name: 'ログアウト' }))

    expect(signOutAction).toHaveBeenCalledOnce()
    expect(screen.queryByRole('button', { name: 'ログアウト' })).toBeNull()
    expect(await screen.findByRole('button', { name: 'Google でログイン' })).toBeTruthy()
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

  it('returns to a re-login state when an authenticated request returns 401', async () => {
    renderGate({ user: firebaseUser })

    expect(await screen.findByText('管理画面')).toBeTruthy()

    act(() => {
      notifyAuthUnauthorized()
    })

    expect(screen.queryByText('管理画面')).toBeNull()
    expect(screen.getByText('ログインの有効期限が切れました。再ログインしてください。')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Google でログイン' })).toBeTruthy()
  })
})
