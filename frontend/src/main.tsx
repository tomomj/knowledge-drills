import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './app/App'
import { firebaseAuthTokenProvider } from './lib/firebaseAuth'
import { setAuthTokenProvider } from './lib/authToken'

setAuthTokenProvider(firebaseAuthTokenProvider)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
