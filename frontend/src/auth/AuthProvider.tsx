import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import type { CurrentUser } from '../api/types'
import { addAuthUnauthorizedListener } from '../lib/authEvents'
import type { AuthStateProvider, AuthStateUser } from '../lib/authState'
import {
  appAuthStateProvider,
  appSignInWithGoogle,
  appSignOutCurrentUser,
} from '../lib/runtimeAuth'
import { AuthContext, type AuthContextValue, type AuthStatus, useAuth } from './AuthContext'

const UNAUTHORIZED_MESSAGE = 'ログインの有効期限が切れました。再ログインしてください。'

export type AuthProviderProps = {
  children: React.ReactNode
  authStateProvider?: AuthStateProvider
  confirmCurrentUser?: () => Promise<CurrentUser>
  signInWithGoogleAction?: () => Promise<void>
  signOutAction?: () => Promise<void>
}

export function AuthProvider({
  children,
  authStateProvider = appAuthStateProvider,
  confirmCurrentUser = api.getCurrentUser,
  signInWithGoogleAction = appSignInWithGoogle,
  signOutAction = appSignOutCurrentUser,
}: AuthProviderProps) {
  const [status, setStatus] = useState<AuthStatus>({ state: 'checking' })
  const [latestFirebaseUser, setLatestFirebaseUser] = useState<AuthStateUser | null>(null)

  const confirm = useCallback(async (user: AuthStateUser): Promise<void> => {
    setStatus({ state: 'checking' })
    try {
      const currentUser = await confirmCurrentUser()
      setStatus({ state: 'signedIn', firebaseUser: user, currentUser })
    } catch {
      setStatus({
        state: 'failed',
        firebaseUser: user,
        message: 'ログインを確認できませんでした。',
      })
    }
  }, [confirmCurrentUser])

  useEffect(() => {
    let active = true
    try {
      return authStateProvider((user) => {
        if (!active) {
          return
        }
        setLatestFirebaseUser(user)
        if (user === null) {
          setStatus({ state: 'signedOut' })
          return
        }
        void confirm(user)
      })
    } catch {
      const failureTimer = window.setTimeout(() => {
        setStatus({
          state: 'failed',
          firebaseUser: null,
          message: 'ログイン設定を確認できませんでした。',
        })
      }, 0)
      return () => {
        active = false
        window.clearTimeout(failureTimer)
      }
    }
  }, [authStateProvider, confirm])

  useEffect(
    () =>
      addAuthUnauthorizedListener(() => {
        setStatus({
          state: 'failed',
          firebaseUser: latestFirebaseUser,
          message: UNAUTHORIZED_MESSAGE,
        })
      }),
    [latestFirebaseUser],
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      ...status,
      signIn: async () => {
        setStatus({ state: 'checking' })
        try {
          await signInWithGoogleAction()
        } catch {
          setStatus({
            state: 'failed',
            firebaseUser: latestFirebaseUser,
            message: 'Google ログインを開始できませんでした。',
          })
        }
      },
      signOut: async () => {
        setStatus({ state: 'checking' })
        await signOutAction()
      },
      retry: async () => {
        if (latestFirebaseUser === null) {
          setStatus({ state: 'signedOut' })
          return
        }
        await confirm(latestFirebaseUser)
      },
    }),
    [status, latestFirebaseUser, signInWithGoogleAction, signOutAction, confirm],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const auth = useAuth()
  if (auth.state === 'signedIn') {
    return children
  }
  return <LoginStateView auth={auth} />
}

function LoginStateView({ auth }: { auth: AuthContextValue }) {
  if (auth.state === 'checking') {
    return (
      <main className="auth-page">
        <div className="auth-panel" aria-live="polite">
          ログイン状態を確認しています。
        </div>
      </main>
    )
  }

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-label="ログイン">
        <div>
          <p className="eyebrow">Owner Login</p>
          <h1>Knowledge Drills</h1>
        </div>
        {auth.state === 'failed' ? <p className="auth-error">{auth.message}</p> : null}
        <div className="toolbar">
          <button className="btn btn--primary" type="button" onClick={() => void auth.signIn()}>
            Google でログイン
          </button>
          {auth.state === 'failed' ? (
            <button className="btn btn--secondary" type="button" onClick={() => void auth.retry()}>
              再試行
            </button>
          ) : null}
        </div>
      </section>
    </main>
  )
}
