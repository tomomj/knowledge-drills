import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  observeAuthState,
  resetAuthStateProvider,
  setAuthStateProvider,
  type AuthStateUser,
} from './authState'

describe('authState', () => {
  afterEach(() => {
    resetAuthStateProvider()
  })

  it('does not connect to Firebase or emit a user by default', () => {
    const listener = vi.fn()
    const unsubscribe = observeAuthState(listener)

    expect(listener).not.toHaveBeenCalled()
    expect(() => unsubscribe()).not.toThrow()
  })

  it('allows tests to emit a mock signed-in user', () => {
    const user: AuthStateUser = {
      uid: 'fake-owner',
      email: 'fake-owner@example.test',
      displayName: 'Fake Owner',
      photoUrl: 'https://example.test/avatar.png',
      getIdToken: vi.fn<() => Promise<string>>().mockResolvedValue('mock-id-token'),
    }
    const unsubscribe = vi.fn()
    const listener = vi.fn()

    setAuthStateProvider((authStateListener) => {
      authStateListener(user)
      return unsubscribe
    })

    const returnedUnsubscribe = observeAuthState(listener)
    returnedUnsubscribe()

    expect(listener).toHaveBeenCalledWith(user)
    expect(unsubscribe).toHaveBeenCalledOnce()
  })

  it('allows tests to emit signed-out state', () => {
    const listener = vi.fn()

    setAuthStateProvider((authStateListener) => {
      authStateListener(null)
      return () => undefined
    })

    observeAuthState(listener)

    expect(listener).toHaveBeenCalledWith(null)
  })
})
