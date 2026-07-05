import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api, ApiClientError } from '../api/client'
import type { CourseSummary } from '../api/types'
import { AppShell } from '../components/common/AppShell'
import { StatusBanner } from '../components/common/StatusBanner'

type PageState =
  | { status: 'loading' }
  | { status: 'ready'; courses: CourseSummary[] }
  | { status: 'failed'; message: string }

export function CourseListPage() {
  const navigate = useNavigate()
  const [state, setState] = useState<PageState>({ status: 'loading' })
  const [query, setQuery] = useState('')

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const response = await api.listCourses()
        if (active) {
          setState({ status: 'ready', courses: response.courses })
        }
      } catch (error) {
        if (active) {
          setState({ status: 'failed', message: errorMessage(error) })
        }
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [])

  const courses = state.status === 'ready' ? state.courses : []
  const trimmedQuery = query.trim()
  const filtered = trimmedQuery
    ? courses.filter((course) => course.title.includes(trimmedQuery))
    : courses

  return (
    <AppShell>
      <main className="page">
        <section className="page-head" aria-labelledby="course-list-title">
          <div>
            <p className="eyebrow">Owner</p>
            <h1 id="course-list-title">講座一覧</h1>
            <p className="page-head__sub">
              資料を登録した講座と、ドリル・修正案の状況が一覧できます。
            </p>
          </div>
          <div className="toolbar">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => navigate('/courses/new')}
            >
              ＋ 新しい講座を作成
            </button>
          </div>
        </section>

        {state.status === 'loading' ? (
          <StatusBanner tone="info">講座を読み込んでいます。</StatusBanner>
        ) : null}
        {state.status === 'failed' ? (
          <StatusBanner tone="error">{state.message}</StatusBanner>
        ) : null}

        {state.status === 'ready' ? (
          courses.length === 0 ? (
            <StatusBanner tone="info">
              まだ講座がありません。資料を登録して最初のドリルを作りましょう。
            </StatusBanner>
          ) : (
            <>
              <div className="list-toolbar">
                <input
                  type="search"
                  placeholder="講座名で検索…"
                  aria-label="講座名で検索"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
                <span className="list-count">{filtered.length} 件の講座</span>
              </div>

              {filtered.length === 0 ? (
                <StatusBanner tone="info">
                  「{query.trim()}」に一致する講座はありません。
                </StatusBanner>
              ) : (
                <div className="card course-list">
                  {filtered.map((course) => (
                    <Link className="course-row" to={`/courses/${course.id}`} key={course.id}>
                      <div>
                        <div className="course-row__title">{course.title}</div>
                        <div className="course-row__meta">{metaLine(course)}</div>
                      </div>
                      <div className="course-row__chips">
                        {statusChips(course).map((chip) => (
                          <span className={`chip chip--${chip.tone}`} key={chip.label}>
                            {chip.label}
                          </span>
                        ))}
                      </div>
                      <span className="course-row__arrow" aria-hidden="true">
                        ›
                      </span>
                    </Link>
                  ))}
                </div>
              )}
            </>
          )
        ) : null}
      </main>
    </AppShell>
  )
}

type Chip = { label: string; tone: string }

function statusChips(course: CourseSummary): Chip[] {
  const chips: Chip[] = []
  if (course.patchStatus === 'proposed') {
    chips.push({ label: 'パッチ提案あり', tone: 'warning' })
  } else if (course.patchStatus === 'applied') {
    chips.push({ label: '修正適用済み', tone: 'accent' })
  }
  switch (course.drillStatus) {
    case 'ready':
    case 'analyzing':
    case 'analyzed':
      chips.push({ label: 'ドリル配布中', tone: 'success' })
      break
    case 'generating':
      chips.push({ label: 'ドリル生成中', tone: 'muted' })
      break
    case 'failed':
      chips.push({ label: 'ドリル生成失敗', tone: 'error' })
      break
    default:
      chips.push({ label: 'ドリル未生成', tone: 'muted' })
  }
  return chips
}

function metaLine(course: CourseSummary): string {
  const parts = [`v${course.version}`]
  if (course.updatedAt) {
    parts.push(`更新 ${formatDate(course.updatedAt)}`)
  }
  if (course.answerCount > 0) {
    parts.push(`回答 ${course.answerCount} 件`)
  }
  return parts.join(' · ')
}

function formatDate(isoString: string): string {
  const date = new Date(isoString)
  if (Number.isNaN(date.getTime())) {
    return isoString
  }
  return date.toLocaleDateString('ja-JP', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    return error.error.message
  }
  return '講座一覧の取得に失敗しました。'
}
