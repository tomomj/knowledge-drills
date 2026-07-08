import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AnalysisTimeline, type AnalysisTimelineItemView } from './AnalysisTimeline'

const items: AnalysisTimelineItemView[] = [
  {
    id: 'collect_answers',
    title: '回答を収集',
    status: 'pending',
    summary: '採点済み回答を待っています。',
    evidence: ['回答 0 件'],
    completedAt: null,
  },
  {
    id: 'detect_failure_patterns',
    title: 'つまずき傾向を検出',
    status: 'running',
    summary: '採点結果から共通傾向を抽出しています。',
    evidence: ['設問 q1', '設問 q2'],
    completedAt: null,
  },
  {
    id: 'propose_document_patch',
    title: '改善案を作成',
    status: 'completed',
    summary: '判断基準の追記候補を作成しました。',
    evidence: ['根拠 1', '根拠 2', '根拠 3', '根拠 4'],
    completedAt: '2026-07-08T10:00:00Z',
  },
  {
    id: 'save_patch',
    title: 'パッチを保存',
    status: 'failed',
    summary: '分析結果の保存に失敗しました。',
    evidence: ['保存エラー'],
    completedAt: null,
  },
  {
    id: 'notify_owner',
    title: '通知を準備',
    status: 'skipped',
    summary: null,
    evidence: [],
    completedAt: null,
  },
]

describe('AnalysisTimeline', () => {
  it('renders status chips, titles, summaries, and up to three evidence entries', () => {
    render(<AnalysisTimeline title="分析タイムライン" items={items} />)

    expect(screen.getByRole('heading', { name: '分析タイムライン' })).toBeTruthy()
    expect(screen.getByText('未開始')).toBeTruthy()
    expect(screen.getByText('実行中')).toBeTruthy()
    expect(screen.getByText('完了')).toBeTruthy()
    expect(screen.getByText('失敗')).toBeTruthy()
    expect(screen.getByText('スキップ')).toBeTruthy()
    expect(screen.getByText('判断基準の追記候補を作成しました。')).toBeTruthy()
    expect(screen.getByText('根拠 1')).toBeTruthy()
    expect(screen.getByText('根拠 2')).toBeTruthy()
    expect(screen.getByText('根拠 3')).toBeTruthy()
    expect(screen.queryByText('根拠 4')).toBeNull()
  })
})
