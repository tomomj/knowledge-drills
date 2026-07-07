export type AuthUnauthorizedListener = () => void

const unauthorizedListeners = new Set<AuthUnauthorizedListener>()

export function addAuthUnauthorizedListener(listener: AuthUnauthorizedListener): () => void {
  unauthorizedListeners.add(listener)
  return () => {
    unauthorizedListeners.delete(listener)
  }
}

export function clearAuthUnauthorizedListeners(): void {
  unauthorizedListeners.clear()
}

export function notifyAuthUnauthorized(): void {
  for (const listener of Array.from(unauthorizedListeners)) {
    listener()
  }
}
