type StatusBannerTone = 'info' | 'success' | 'warning' | 'review' | 'error'

type StatusBannerProps = {
  tone: StatusBannerTone
  children: React.ReactNode
}

const ICON_PATHS: Record<StatusBannerTone, string> = {
  info: 'M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm0 3a1 1 0 1 1 0 2 1 1 0 0 1 0-2Zm1.25 8h-2.5a.75.75 0 0 1 0-1.5h.5V8.75H7a.75.75 0 0 1 0-1.5h1.5a.75.75 0 0 1 .75.75v2.5h.5a.75.75 0 0 1 0 1.5Z',
  success:
    'M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm3.28 5.28-4 4a.75.75 0 0 1-1.06 0l-1.5-1.5a.75.75 0 1 1 1.06-1.06l.97.97 3.47-3.47a.75.75 0 1 1 1.06 1.06Z',
  warning:
    'M8 1.5 15 14H1L8 1.5Zm0 4a.75.75 0 0 0-.75.75v3a.75.75 0 0 0 1.5 0v-3A.75.75 0 0 0 8 5.5Zm0 6a1 1 0 1 0 0 2 1 1 0 0 0 0-2Z',
  review:
    'M8 1.25 9.5 5.5 13.75 7 9.5 8.5 8 12.75 6.5 8.5 2.25 7 6.5 5.5 8 1.25Z',
  error:
    'M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm2.78 8.72a.75.75 0 1 1-1.06 1.06L8 9.06l-1.72 1.72a.75.75 0 0 1-1.06-1.06L6.94 8 5.22 6.28a.75.75 0 0 1 1.06-1.06L8 6.94l1.72-1.72a.75.75 0 1 1 1.06 1.06L9.06 8l1.72 1.72Z',
}

export function StatusBanner({ tone, children }: StatusBannerProps) {
  return (
    <div className={`status-banner status-banner--${tone}`} role="status">
      <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
        <path d={ICON_PATHS[tone]} />
      </svg>
      <span>{children}</span>
    </div>
  )
}
