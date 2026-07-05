import { Link } from 'react-router-dom'

type AppShellProps = {
  variant?: 'owner' | 'learner'
  children: React.ReactNode
}

export function AppShell({ variant = 'owner', children }: AppShellProps) {
  if (variant === 'learner') {
    return (
      <>
        <header className="topbar topbar--learner">
          <span className="brand">
            <span className="brand__mark">K</span>
            Knowledge Drills
          </span>
        </header>
        {children}
      </>
    )
  }

  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand__mark">K</span>
          Knowledge Drills
        </Link>
      </header>
      {children}
    </>
  )
}
