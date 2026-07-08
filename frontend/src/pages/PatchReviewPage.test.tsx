import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '../api/client'
import type { DocumentPatch } from '../api/types'
import { PatchReviewPage } from './PatchReviewPage'

const patch: DocumentPatch = {
  id: 'patch-1',
  courseId: 'course-1',
  drillRunId: 'drill-1',
  status: 'proposed',
  baseMarkdown: '# Before',
  patchedMarkdown: '# After',
  patchSummary: '判断基準を追記',
  riskNotes: ['既存運用との整合を確認'],
  diffText: '--- base.md\n+++ patched.md\n-# Before\n+# After',
  ownerFeedback: null,
  analysisTimeline: [],
  failureSignals: [
    {
      id: 'fs_test_001',
      title: '根拠不足',
      severity: 'medium',
      evidence: ['q1 で根拠不足が多い'],
      likelyCause: '判断基準の記載が薄い',
      suspectedDocumentGap: '例外条件が不足',
      targetSections: ['## 判断基準'],
      recommendedChange: '例外条件を追記',
      sampleSize: 2,
      confidenceNote: '少数回答の傾向です。',
    },
  ],
}

const mocks = vi.hoisted(() => ({
  getPatch: vi.fn(),
  applyPatch: vi.fn(),
  rejectPatch: vi.fn(),
  ApiClientError: class ApiClientError extends Error {
    error: { code: string; message: string; currentStatus?: string }
    status: number

    constructor(
      status: number,
      error: { code: string; message: string; currentStatus?: string },
    ) {
      super(error.message)
      this.status = status
      this.error = error
    }
  },
}))

vi.mock('../api/client', () => ({
  api: {
    getPatch: mocks.getPatch,
    applyPatch: mocks.applyPatch,
    rejectPatch: mocks.rejectPatch,
  },
  ApiClientError: mocks.ApiClientError,
}))

function renderPatch() {
  render(
    <MemoryRouter initialEntries={['/patches/patch-1']}>
      <Routes>
        <Route path="/patches/:patchId" element={<PatchReviewPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('PatchReviewPage', () => {
  beforeEach(() => {
    mocks.getPatch.mockReset()
    mocks.applyPatch.mockReset()
    mocks.rejectPatch.mockReset()
  })

  afterEach(() => {
    cleanup()
  })

  it('renders failure signals, confidence note, risk notes, and diff', async () => {
    mocks.getPatch.mockResolvedValueOnce(patch)

    renderPatch()

    await waitFor(() => expect(screen.getByText('提案中')).toBeTruthy())
    expect(screen.getByText('回答サンプル 2 件')).toBeTruthy()
    expect(screen.getByText(/少数回答の傾向です。/)).toBeTruthy()
    expect(screen.getByText('既存運用との整合を確認')).toBeTruthy()
    expect(screen.getByText(/--- base.md/)).toBeTruthy()
    expect(screen.queryByText('分析タイムライン')).toBeNull()
  })

  it('renders analysis timeline between patch summary and failure signals', async () => {
    mocks.getPatch.mockResolvedValueOnce({
      ...patch,
      analysisTimeline: [
        {
          id: 'collect_answers',
          title: '回答を収集',
          status: 'completed',
          summary: '採点済み回答 2 件を確認しました。',
          evidence: ['受講者A: 根拠不足', '受講者B: 例外条件不足'],
          completedAt: '2026-07-08T10:00:00Z',
        },
      ],
    })

    renderPatch()

    await screen.findByText('回答を収集')
    expect(screen.getByText('分析タイムライン')).toBeTruthy()
    expect(screen.getByText('採点済み回答 2 件を確認しました。')).toBeTruthy()
    expect(screen.getByText('受講者A: 根拠不足')).toBeTruthy()

    const summary = screen.getByText(/要約：判断基準を追記/)
    const timeline = screen.getByText('分析タイムライン')
    const signal = screen.getByText('根拠不足')
    expect(summary.compareDocumentPosition(timeline) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(timeline.compareDocumentPosition(signal) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('disables apply for stale patch', async () => {
    mocks.getPatch.mockResolvedValueOnce({ ...patch, status: 'stale' })

    renderPatch()

    await waitFor(() => expect(screen.getByText('このパッチは古くなっています。再分析が必要です。')).toBeTruthy())
    const applyButton = screen.getByRole('button', { name: '修正を適用する' }) as HTMLButtonElement
    expect(applyButton.disabled).toBe(true)
  })

  it('applies patch with owner feedback', async () => {
    const user = userEvent.setup()
    mocks.getPatch.mockResolvedValueOnce(patch)
    mocks.applyPatch.mockResolvedValueOnce({
      ...patch,
      status: 'applied',
      ownerFeedback: '反映します',
    })

    renderPatch()

    await screen.findByText('提案中')
    await user.type(screen.getByLabelText(/オーナーコメント/), '反映します')
    await user.click(screen.getByRole('button', { name: '修正を適用する' }))

    expect(mocks.applyPatch).toHaveBeenCalledWith('patch-1', { ownerFeedback: '反映します' })
    await waitFor(() => expect(screen.getByText('パッチを適用しました。')).toBeTruthy())
  })

  it('rejects patch with owner feedback', async () => {
    const user = userEvent.setup()
    mocks.getPatch.mockResolvedValueOnce(patch)
    mocks.rejectPatch.mockResolvedValueOnce({
      ...patch,
      status: 'rejected',
      ownerFeedback: '不要です',
    })

    renderPatch()

    await screen.findByText('提案中')
    await user.type(screen.getByLabelText(/オーナーコメント/), '不要です')
    await user.click(screen.getByRole('button', { name: '却下する' }))

    expect(mocks.rejectPatch).toHaveBeenCalledWith('patch-1', { ownerFeedback: '不要です' })
    await waitFor(() => expect(screen.getByText('パッチを却下しました。')).toBeTruthy())
  })

  it('shows current status when backend returns patch conflict', async () => {
    const user = userEvent.setup()
    mocks.getPatch.mockResolvedValueOnce(patch)
    mocks.applyPatch.mockRejectedValueOnce(
      new ApiClientError(409, {
        code: 'patch_not_proposed',
        message: 'conflict',
        currentStatus: 'applied',
      }),
    )

    renderPatch()

    await screen.findByText('提案中')
    await user.click(screen.getByRole('button', { name: '修正を適用する' }))

    await waitFor(() => expect(screen.getByText('Patch status: applied')).toBeTruthy())
  })
})
