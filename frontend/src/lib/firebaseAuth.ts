import { getApp, getApps, initializeApp } from 'firebase/app'
import {
  getAuth,
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  signOut,
  type Auth,
} from 'firebase/auth'

import type { AuthStateProvider, AuthStateUser } from './authState'
import type { AuthTokenProvider } from './authToken'

type FirebaseConfig = {
  apiKey: string
  authDomain: string
  projectId: string
  appId: string
}

export const firebaseAuthStateProvider: AuthStateProvider = (listener) => {
  const auth = getConfiguredAuth()
  if (auth === null) {
    listener(null)
    return () => undefined
  }
  return onAuthStateChanged(auth, (user) => {
    listener(user === null ? null : toAuthStateUser(user))
  })
}

export const firebaseAuthTokenProvider: AuthTokenProvider = async () => {
  const auth = getConfiguredAuth()
  if (auth?.currentUser == null) {
    return null
  }
  return auth.currentUser.getIdToken()
}

export async function signInWithGoogle(): Promise<void> {
  const auth = getConfiguredAuth()
  if (auth === null) {
    throw new Error('Firebase Authentication is not configured.')
  }
  await signInWithPopup(auth, new GoogleAuthProvider())
}

export async function signOutCurrentUser(): Promise<void> {
  const auth = getConfiguredAuth()
  if (auth !== null) {
    await signOut(auth)
  }
}

function getConfiguredAuth(): Auth | null {
  const config = getFirebaseConfig()
  if (config === null) {
    return null
  }
  const app = getApps().length > 0 ? getApp() : initializeApp(config)
  return getAuth(app)
}

function getFirebaseConfig(): FirebaseConfig | null {
  const apiKey = import.meta.env.VITE_FIREBASE_API_KEY
  const authDomain = import.meta.env.VITE_FIREBASE_AUTH_DOMAIN
  const projectId = import.meta.env.VITE_FIREBASE_PROJECT_ID
  const appId = import.meta.env.VITE_FIREBASE_APP_ID
  if (!apiKey || !authDomain || !projectId || !appId) {
    return null
  }
  return { apiKey, authDomain, projectId, appId }
}

function toAuthStateUser(user: {
  uid: string
  email: string | null
  displayName: string | null
  photoURL: string | null
  getIdToken: () => Promise<string>
}): AuthStateUser {
  return {
    uid: user.uid,
    email: user.email,
    displayName: user.displayName,
    photoUrl: user.photoURL,
    getIdToken: () => user.getIdToken(),
  }
}
