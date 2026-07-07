import { createContext, useContext } from 'react'

import type { CurrentUser } from '../api/types'
import type { AuthStateUser } from '../lib/authState'

export type AuthStatus =
  | { state: 'checking' }
  | { state: 'signedOut' }
  | { state: 'signedIn'; firebaseUser: AuthStateUser; currentUser: CurrentUser }
  | { state: 'failed'; firebaseUser: AuthStateUser | null; message: string }

export type AuthContextValue = AuthStatus & {
  signIn: () => Promise<void>
  signOut: () => Promise<void>
  retry: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (value === null) {
    throw new Error('useAuth must be used inside AuthProvider.')
  }
  return value
}
