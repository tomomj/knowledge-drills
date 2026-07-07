export type AuthStateUser = {
  uid: string
  email: string | null
  displayName: string | null
  photoUrl: string | null
  getIdToken: () => Promise<string>
}

export type AuthStateListener = (user: AuthStateUser | null) => void
export type AuthStateUnsubscribe = () => void
export type AuthStateProvider = (listener: AuthStateListener) => AuthStateUnsubscribe

const defaultAuthStateProvider: AuthStateProvider = () => () => undefined

let authStateProvider = defaultAuthStateProvider

export function setAuthStateProvider(provider: AuthStateProvider): void {
  authStateProvider = provider
}

export function resetAuthStateProvider(): void {
  authStateProvider = defaultAuthStateProvider
}

export function observeAuthState(listener: AuthStateListener): AuthStateUnsubscribe {
  return authStateProvider(listener)
}
