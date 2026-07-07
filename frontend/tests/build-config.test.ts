import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const firebaseEnvVars = [
  'VITE_FIREBASE_API_KEY',
  'VITE_FIREBASE_AUTH_DOMAIN',
  'VITE_FIREBASE_PROJECT_ID',
  'VITE_FIREBASE_APP_ID',
]

const configRoot = process.env.FRONTEND_CONFIG_ROOT ?? process.cwd()

const packageJsonText = readFileSync(resolve(configRoot, 'package.json'), 'utf8')
const packageLockText = readFileSync(resolve(configRoot, 'package-lock.json'), 'utf8')
const dockerfile = readFileSync(resolve(configRoot, 'Dockerfile'), 'utf8')
const forbiddenCredentialTokens = [
  ['FIREBASE', 'ADMIN'].join('_'),
  ['GOOGLE', 'APPLICATION', 'CREDENTIALS'].join('_'),
  ['SERVICE', 'ACCOUNT'].join('_'),
  ['PRIVATE', 'KEY'].join('_'),
  ['CLIENT', 'EMAIL'].join('_'),
  ['KNOWLEDGE', 'DRILLS', ''].join('_'),
]

const packageJson = JSON.parse(packageJsonText) as {
  dependencies?: Record<string, string>
}

const packageLock = JSON.parse(packageLockText) as {
  packages?: Record<string, { dependencies?: Record<string, string> }>
}

describe('frontend Firebase build config', () => {
  it('declares Firebase client SDK as a locked runtime dependency', () => {
    expect(packageJson.dependencies?.firebase).toMatch(/^\^12\./)
    expect(packageLock.packages?.['']?.dependencies?.firebase).toBe(
      packageJson.dependencies?.firebase,
    )
    expect(packageLock.packages?.['node_modules/firebase']).toBeDefined()
  })

  it('passes only public Firebase Vite vars through Docker build env', () => {
    for (const envVar of firebaseEnvVars) {
      expect(dockerfile).toContain(`ARG ${envVar}`)
      expect(dockerfile).toContain(`ENV ${envVar}=\${${envVar}}`)
    }

    expect(dockerfile).toContain('ARG VITE_API_BASE_URL')
    expect(dockerfile).toContain('ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}')
  })

  it('keeps backend and Admin credential names out of frontend build config', () => {
    const publicBuildConfig = `${packageJsonText}\n${dockerfile}`

    for (const token of forbiddenCredentialTokens) {
      expect(publicBuildConfig.toUpperCase()).not.toContain(token)
    }
  })
})
