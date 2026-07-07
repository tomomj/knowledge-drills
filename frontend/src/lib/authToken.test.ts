import { afterEach, describe, expect, it, vi } from 'vitest'

import { getAuthToken, resetAuthTokenProvider, setAuthTokenProvider } from './authToken'

describe('authToken', () => {
  afterEach(() => {
    resetAuthTokenProvider()
  })

  it('returns null by default without connecting to Firebase', async () => {
    await expect(getAuthToken()).resolves.toBeNull()
  })

  it('allows tests to provide a mock ID token provider', async () => {
    const provider = vi.fn<() => Promise<string | null>>().mockResolvedValue('mock-id-token')

    setAuthTokenProvider(provider)

    await expect(getAuthToken()).resolves.toBe('mock-id-token')
    expect(provider).toHaveBeenCalledOnce()
  })

  it('can reset the provider between tests', async () => {
    setAuthTokenProvider(async () => 'stale-token')

    resetAuthTokenProvider()

    await expect(getAuthToken()).resolves.toBeNull()
  })
})
