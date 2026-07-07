export type AuthTokenProvider = () => Promise<string | null>

const defaultAuthTokenProvider: AuthTokenProvider = async () => null

let authTokenProvider = defaultAuthTokenProvider

export function setAuthTokenProvider(provider: AuthTokenProvider): void {
  authTokenProvider = provider
}

export function resetAuthTokenProvider(): void {
  authTokenProvider = defaultAuthTokenProvider
}

export async function getAuthToken(): Promise<string | null> {
  return authTokenProvider()
}
