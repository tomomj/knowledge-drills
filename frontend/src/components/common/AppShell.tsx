import { useContext } from 'react'
import { Link } from 'react-router-dom'

import { AuthContext } from '../../auth/AuthContext'

type AppShellProps = {
  variant?: 'owner' | 'learner'
  children: React.ReactNode
}

export function AppShell({ variant = 'owner', children }: AppShellProps) {
  const auth = useContext(AuthContext)

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
        {auth?.state === 'signedIn' ? (
          <div className="topbar__actions">
            {auth.currentUser.email ? (
              <span className="topbar__user">{auth.currentUser.email}</span>
            ) : null}
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => void auth.signOut()}
            >
              ログアウト
            </button>
          </div>
        ) : null}
      </header>
      {children}
    </>
  )
}
