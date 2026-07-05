import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { api, ApiClientError } from '../api/client'
import type { CourseDetail } from '../api/types'
import { AppShell } from '../components/common/AppShell'
import { Breadcrumbs } from '../components/common/Breadcrumbs'
import { StatusBanner } from '../components/common/StatusBanner'

const MARKDOWN_LIMIT = 20_000

type PageState =
  | { status: 'idle' }
  | { status: 'saving' }
  | { status: 'generating' }
  | { status: 'ready'; message: string }
  | { status: 'failed'; message: string }

export function CourseEditorPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { courseId } = useParams()
  const [title, setTitle] = useState('')
  const [markdown, setMarkdown] = useState('')
  const [course, setCourse] = useState<CourseDetail | null>(null)
  const [state, setState] = useState<PageState>({ status: 'idle' })

  useEffect(() => {
    let active = true
    async function loadCourse() {
      if (!courseId) {
        setCourse(null)
        setTitle('')
        setMarkdown('')
        setState({ status: 'idle' })
        return
      }
      setState({ status: 'saving' })
      try {
        const loaded = await api.getCourse(courseId)
        if (active) {
          setCourse(loaded)
          setTitle(loaded.title)
          setMarkdown(loaded.markdown)
          const saveMessage = saveMessageFromLocationState(location.state)
          setState(saveMessage ? { status: 'ready', message: saveMessage } : { status: 'idle' })
        }
      } catch (error) {
        if (active) {
          setState({ status: 'failed', message: errorMessage(error) })
        }
      }
    }
    void loadCourse()
    return () => {
      active = false
    }
  }, [courseId, location.state])

  const validationError = validateCourse(title, markdown)

  async function saveCourse() {
    if (validationError) {
      setState({ status: 'failed', message: validationError })
      return
    }
    setState({ status: 'saving' })
    try {
      const saved = course
        ? await api.updateCourse(course.id, { title, markdown })
        : await api.createCourse({ title, markdown }).then((created) =>
            api.getCourse(created.courseId),
          )
      setCourse(saved)
      setTitle(saved.title)
      setMarkdown(saved.markdown)
      setState({ status: 'ready', message: '保存しました。' })
      if (!course) {
        navigate(`/courses/${saved.id}`, {
          replace: true,
          state: { saveMessage: '保存しました。' },
        })
      }
    } catch (error) {
      setState({ status: 'failed', message: errorMessage(error) })
    }
  }

  async function generateDrill() {
    if (!course) {
      setState({ status: 'failed', message: '先に講座を保存してください。' })
      return
    }
    setState({ status: 'generating' })
    try {
      const drill = await api.generateDrill(course.id)
      setCourse({ ...course, latestDrillRunId: drill.drillRunId })
      setState({ status: 'ready', message: 'ドリルを生成しました。' })
      navigate(`/courses/${course.id}/drill-runs/${drill.drillRunId}`)
    } catch (error) {
      setState({ status: 'failed', message: errorMessage(error) })
    }
  }

  return (
    <AppShell>
      <main className="page">
        <section className="page-head" aria-labelledby="course-editor-title">
          <div>
            <Breadcrumbs
              items={[
                { label: '講座一覧', to: '/courses' },
                { label: course ? course.title : '新しい講座' },
              ]}
            />
            <h1 id="course-editor-title">講座管理</h1>
            <p className="page-head__sub">社内資料を登録すると、AI が確認ドリルを生成します。</p>
          </div>
          <div className="toolbar">
            <button
              type="button"
              className="btn btn--secondary"
              onClick={generateDrill}
              disabled={!course || state.status === 'generating'}
            >
              ドリルを生成
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={saveCourse}
              disabled={state.status === 'saving'}
            >
              保存する
            </button>
          </div>
        </section>

        <StatusBanner tone="warning">
          MVP 検証では本物の機密社内資料を入力しないでください。
        </StatusBanner>

        {state.status === 'saving' ? <StatusBanner tone="info">保存中です。</StatusBanner> : null}
        {state.status === 'generating' ? (
          <StatusBanner tone="info">ドリルを生成中です。</StatusBanner>
        ) : null}
        {state.status === 'ready' ? (
          <StatusBanner tone="success">{state.message}</StatusBanner>
        ) : null}
        {state.status === 'failed' ? (
          <StatusBanner tone="error">{state.message}</StatusBanner>
        ) : null}

        <section className="editor-grid">
          <div className="card">
            <div className="card__body" style={{ display: 'grid', gap: 18 }}>
              <label className="field">
                <span className="field__label">講座タイトル</span>
                <input value={title} onChange={(event) => setTitle(event.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">
                  教材 Markdown
                  <span className="field__hint">
                    {markdown.length.toLocaleString()} / {MARKDOWN_LIMIT.toLocaleString()} 文字
                  </span>
                </span>
                <textarea
                  className="editor-md"
                  value={markdown}
                  onChange={(event) => setMarkdown(event.target.value)}
                />
              </label>
            </div>
          </div>

          <aside className="editor-side" aria-label="講座の状態">
            <div className="card">
              <div className="card__head">
                <h2>講座の状態</h2>
                {course ? (
                  <span className="chip chip--success">保存済み</span>
                ) : (
                  <span className="chip chip--muted">未保存</span>
                )}
              </div>
              <div className="card__body" style={{ paddingTop: 8, paddingBottom: 8 }}>
                <dl className="side-list">
                  <div>
                    <dt>バージョン</dt>
                    <dd>{course ? `v${course.version}` : '-'}</dd>
                  </div>
                  <div>
                    <dt>更新履歴</dt>
                    <dd>
                      {course ? (
                        <Link className="side-link" to={`/courses/${course.id}/history`}>
                          差分を見る →
                        </Link>
                      ) : (
                        '-'
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>最新ドリル</dt>
                    <dd>
                      {course?.latestDrillRunId ? (
                        <Link
                          className="side-link"
                          to={`/courses/${course.id}/drill-runs/${course.latestDrillRunId}`}
                        >
                          確認する →
                        </Link>
                      ) : (
                        '-'
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>最新パッチ</dt>
                    <dd>
                      {course?.latestPatchId ? (
                        <Link className="side-link" to={`/patches/${course.latestPatchId}`}>
                          レビュー →
                        </Link>
                      ) : (
                        '-'
                      )}
                    </dd>
                  </div>
                </dl>
              </div>
            </div>
            <div className="next-step">
              <b>次のステップ</b>
              資料を保存したら「ドリルを生成」で確認テストを作成し、共有 URL を受講者に配布します。
            </div>
          </aside>
        </section>
      </main>
    </AppShell>
  )
}

function saveMessageFromLocationState(state: unknown): string | null {
  if (
    typeof state === 'object' &&
    state !== null &&
    'saveMessage' in state &&
    typeof state.saveMessage === 'string'
  ) {
    return state.saveMessage
  }
  return null
}

function validateCourse(title: string, markdown: string): string | null {
  if (!title.trim()) {
    return 'タイトルが必要です。'
  }
  if (!markdown.trim()) {
    return 'Markdown 本文が必要です。'
  }
  if (markdown.length > MARKDOWN_LIMIT) {
    return 'Markdown 本文が MVP の文字数上限を超えています。'
  }
  return null
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    return error.error.message
  }
  return '処理に失敗しました。'
}
