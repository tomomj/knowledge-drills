import type { AuthStateProvider, AuthStateUser } from './authState'
import type { AuthTokenProvider } from './authToken'
import {
  firebaseAuthStateProvider,
  firebaseAuthTokenProvider,
  signInWithGoogle,
  signOutCurrentUser,
} from './firebaseAuth'

const localAuthUser: AuthStateUser = {
  uid: 'local-owner',
  email: 'local-owner@example.test',
  displayName: 'Local Owner',
  photoUrl: null,
  getIdToken: async () => '',
}

const localAuthStateProvider: AuthStateProvider = (listener) => {
  listener(localAuthUser)
  return () => undefined
}

const localAuthTokenProvider: AuthTokenProvider = async () => null

const noopAuthAction = async (): Promise<void> => undefined

const usesLocalAuth = import.meta.env.VITE_AUTH_MODE === 'none'

export const appAuthStateProvider: AuthStateProvider = usesLocalAuth
  ? localAuthStateProvider
  : firebaseAuthStateProvider

export const appAuthTokenProvider: AuthTokenProvider = usesLocalAuth
  ? localAuthTokenProvider
  : firebaseAuthTokenProvider

export const appSignInWithGoogle = usesLocalAuth ? noopAuthAction : signInWithGoogle
export const appSignOutCurrentUser = usesLocalAuth ? noopAuthAction : signOutCurrentUser
