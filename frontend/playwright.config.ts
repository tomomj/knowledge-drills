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
const backendCorsAllowedOrigins =
  process.env.KNOWLEDGE_DRILLS_CORS_ALLOWED_ORIGINS ?? frontendBaseUrl
const localBrowserChannel =
  process.env.PLAYWRIGHT_BROWSER_CHANNEL ?? (process.platform === 'darwin' ? 'chrome' : undefined)
const runsLlmE2E = process.env.E2E_LLM === '1'
const backendEnv: Record<string, string> = Object.fromEntries(
  Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined),
)
Object.assign(backendEnv, {
  KNOWLEDGE_DRILLS_AGENT_MODE: runsLlmE2E ? 'adk' : 'local',
  KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS: runsLlmE2E
    ? (process.env.KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS ?? '120')
    : process.env.KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS,
  KNOWLEDGE_DRILLS_CORS_ALLOWED_ORIGINS: backendCorsAllowedOrigins,
})
if (runsLlmE2E) {
  backendEnv.KNOWLEDGE_DRILL_AGENT_ANALYSIS_MODE = 'single'
}
if (backendEnv.KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS === undefined) {
  delete backendEnv.KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS
}

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
      command: `uv run --native-tls --frozen uvicorn app.main:app --host 127.0.0.1 --port ${backendPort}`,
      cwd: backendDir,
      env: backendEnv,
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
