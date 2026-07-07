import { defineConfig, devices } from '@playwright/test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const configDir = dirname(fileURLToPath(import.meta.url))
const backendDir = resolve(configDir, '../backend')

const frontendPort = Number(process.env.E2E_FRONTEND_PORT ?? 5173)
const backendPort = Number(process.env.E2E_BACKEND_PORT ?? 8000)
const frontendBaseUrl =
  process.env.E2E_FRONTEND_BASE_URL ?? `http://127.0.0.1:${frontendPort}`
const apiBaseUrl = process.env.E2E_API_BASE_URL ?? `http://127.0.0.1:${backendPort}`
const localBrowserChannel =
  process.env.PLAYWRIGHT_BROWSER_CHANNEL ?? (process.platform === 'darwin' ? 'chrome' : undefined)

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  expect: {
    timeout: 10_000,
  },
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: frontendBaseUrl,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port ${backendPort}`,
      cwd: backendDir,
      url: `${apiBaseUrl}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      env: {
        VITE_API_BASE_URL: apiBaseUrl,
        VITE_AUTH_MODE: 'none',
      },
      url: frontendBaseUrl,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        channel: localBrowserChannel,
      },
    },
  ],
})
