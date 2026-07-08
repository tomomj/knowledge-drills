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
    id: 'match_course_evidence',
    title: '教材根拠を照合',
    status: 'completed',
    summary: '教材本文にある根拠を確認しました。',
    evidence: ['## 判断基準'],
    completedAt: '2026-07-08T09:58:00Z',
  },
  {
    id: 'create_patch',
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
  it('renders grouped categories, status chips, titles, summaries, and evidence entries', () => {
    render(<AnalysisTimeline title="分析タイムライン" items={items} />)

    expect(screen.getByRole('heading', { name: '分析タイムライン' })).toBeTruthy()
    expect(screen.getByText('入力確認')).toBeTruthy()
    expect(screen.getByText('採点済み回答を集め、分析に使う材料を確認します。')).toBeTruthy()
    expect(screen.getByText('つまずき分析')).toBeTruthy()
    expect(
      screen.getByText('回答と採点結果から、繰り返し出ている理解不足を抽出します。'),
    ).toBeTruthy()
    expect(screen.getByText('根拠レビュー')).toBeTruthy()
    expect(screen.getByText('教材本文と照合し、根拠の弱い所見を修正案から外します。')).toBeTruthy()
    expect(screen.getByText('修正判断')).toBeTruthy()
    expect(screen.getByText('採用する所見を選び、資料への変更案と注意点をまとめます。')).toBeTruthy()
    expect(screen.getByText('その他')).toBeTruthy()
    expect(screen.getByText('未開始')).toBeTruthy()
    expect(screen.getByText('実行中')).toBeTruthy()
    expect(screen.getAllByText('完了').length).toBeGreaterThan(0)
    expect(screen.getByText('失敗')).toBeTruthy()
    expect(screen.getByText('スキップ')).toBeTruthy()
    expect(screen.getByText('判断基準の追記候補を作成しました。')).toBeTruthy()
    expect(screen.getByText('根拠 1')).toBeTruthy()
    expect(screen.getByText('根拠 2')).toBeTruthy()
    expect(screen.getByText('根拠 3')).toBeTruthy()
    expect(screen.getByText('根拠 4')).toBeTruthy()
  })

  it('renders review-derived evidence text in timeline items', () => {
    render(
      <AnalysisTimeline
        title="分析タイムライン"
        items={[
          {
            id: 'decide_patch_strategy',
            title: '改善方針を判断',
            status: 'completed',
            summary: '教材修正方針を選定しました',
            evidence: [
              '採用レビュー: finding-1 のみ採用 (approvedFindingIds: finding-1)',
              '最終化: 未承認所見は採用しない',
            ],
            completedAt: '2026-07-08T10:00:00Z',
          },
        ]}
      />,
    )

    expect(screen.getByText('改善方針を判断')).toBeTruthy()
    expect(screen.getByText('採用レビュー: finding-1 のみ採用 (approvedFindingIds: finding-1)')).toBeTruthy()
    expect(screen.getByText('最終化: 未承認所見は採用しない')).toBeTruthy()
  })
})
