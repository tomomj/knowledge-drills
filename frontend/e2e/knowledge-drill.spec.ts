import { expect, test, type APIRequestContext } from '@playwright/test'

const backendPort = process.env.E2E_BACKEND_PORT ?? '8000'
const apiBaseUrl = process.env.E2E_API_BASE_URL ?? `http://127.0.0.1:${backendPort}`

const courseMarkdown = `# Company Routing

## A事業部
新規契約、導入前相談、初回見積もりの問い合わせを担当する。

## B事業部
既存顧客の追加発注、契約更新、請求内容の確認を担当する。

## 例外
緊急障害は問い合わせ種別に関係なくサポート窓口へ送る。`

type CourseDetail = {
  id: string
  title: string
  markdown: string
  version: number
  latestDrillRunId: string | null
  latestPatchId: string | null
}

type DrillRunSeed = {
  courseId: string
  drillRunId: string
  shareToken: string
  shareUrl: string
}

type LearnerDrill = {
  drillRunId: string
  questions: Array<{
    id: string
    question: string
  }>
}

type PatchSeed = DrillRunSeed & {
  patchId: string
}

type CourseSummary = {
  id: string
  title: string
  latestDrillRunId: string | null
  isDemo: boolean
}

type CourseListResponse = {
  courses: CourseSummary[]
}

type AdminDrill = {
  shareUrl: string | null
  shareStatus: 'open' | 'closed' | 'superseded' | 'unavailable'
}

test.describe('Knowledge Drill E2E', () => {
  test('講座作成からドリル生成まで UI で実行できる', async ({ page }) => {
    await page.goto('/courses')

    await expect(page.getByRole('heading', { name: '講座一覧' })).toBeVisible()
    await page.getByRole('button', { name: '＋ 新しい講座を作成' }).click()

    await expect(page).toHaveURL(/\/courses\/new$/)
    await expect(page.getByRole('heading', { name: '講座管理' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'ドリルを生成' })).toBeDisabled()

    await page.getByLabel('講座タイトル').fill(`E2E Course ${Date.now()}`)
    await page.getByLabel(/教材 Markdown/).fill(courseMarkdown)
    await page.getByRole('button', { name: '保存する' }).click()

    await expect(page.getByText('保存しました。')).toBeVisible()
    await expect(page).toHaveURL(/\/courses\/[0-9a-f]+$/)
    await expect(page.getByRole('button', { name: 'ドリルを生成' })).toBeEnabled()

    await page.getByRole('button', { name: 'ドリルを生成' }).click()

    await expect(page).toHaveURL(/\/courses\/[0-9a-f]+\/drill-runs\/[0-9a-f]+$/)
    await expect(page.getByRole('heading', { name: 'ドリル確認' })).toBeVisible()
    await expect(page.locator('.share-card code')).toContainText('/drills/')
    await expect(page.getByText('回答数')).toBeVisible()
    await expect(page.getByRole('button', { name: '回答を分析する' })).toBeDisabled()
    await expect(page.locator('.q-card h2')).toHaveCount(3)
    await expect(page.getByText('4 pts')).toHaveCount(3)
  })

  test('受講者回答後に feedback が表示され、admin の回答数が増える', async ({
    page,
    request,
  }) => {
    const seed = await createDrillRun(request)

    await page.goto(seed.shareUrl)

    await expect(page.getByRole('heading', { name: '確認ドリル' })).toBeVisible()
    await expect(
      page.getByText('教材を読んでから回答してください。回答は教材改善の分析に匿名で利用されます。'),
    ).toBeVisible()
    await expect(page.getByText('教材バージョン v1')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'A事業部' })).toBeVisible()
    await expect(
      page.getByText('緊急障害は問い合わせ種別に関係なくサポート窓口へ送る。'),
    ).toBeVisible()
    await expect(page.getByRole('textbox', { name: 'お名前', exact: true })).toHaveCount(0)
    await expect(page.locator('textarea')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '回答を提出する' })).toHaveCount(0)
    await expect(page.getByText('4 pts')).toHaveCount(0)
    await expect(page.getByText('業務判断の根拠を確認する')).toHaveCount(0)

    await page.getByRole('button', { name: '回答に進む' }).click()

    await expect.poll(() => page.evaluate('window.scrollY')).toBe(0)
    await expect(page.getByText('教材を確認する')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '回答に進む' })).toHaveCount(0)

    await page.getByRole('textbox', { name: 'お名前', exact: true }).fill('E2E Learner')
    const drill = await getLearnerDrill(request, seed.shareToken)
    for (const question of drill.questions) {
      await page
        .getByLabel(question.question)
        .fill(`${question.id} の回答。根拠と例外条件を説明します。`)
    }

    await page.getByRole('button', { name: '回答を提出する' }).click()

    await expect(page.getByText('提出が完了しました。')).toBeVisible()
    await expect(page.getByText('回答は教材改善の分析に使われます。')).toBeVisible()
    await expect(page.getByText('判断理由は示せています。例外条件も添えてください。')).toHaveCount(
      3,
    )

    await page.goto(`/courses/${seed.courseId}/drill-runs/${seed.drillRunId}`)
    await expect(page.getByRole('button', { name: '回答を分析する' })).toBeEnabled()
    await expect(page.getByText('E2E Learner').first()).toBeVisible()
    await expect(page.getByText('採点済み', { exact: true })).toBeVisible()
  })

  test('回答分析から patch proposed を確認し、Apply で applied にできる', async ({
    page,
    request,
  }) => {
    const seed = await createAnsweredDrillRun(request)

    await page.goto(`/courses/${seed.courseId}/drill-runs/${seed.drillRunId}`)
    await page.getByRole('button', { name: '回答を分析する' }).click()

    await expect(page).toHaveURL(/\/analysis\?patchId=[0-9a-f]+$/)
    await expect(page.getByRole('heading', { name: '資料修正案のレビュー' })).toBeVisible()
    await expect(page.getByText('提案中')).toBeVisible()
    await expect(page.getByText(/要約：/)).toBeVisible()
    await expect(page.getByRole('heading', { name: '例外条件の説明不足' })).toBeVisible()
    await expect(page.getByText('リスクと注意点')).toBeVisible()
    await expect(page.getByLabel('Diff')).toContainText('### 例外条件')

    await page.getByLabel(/オーナーコメント/).fill('E2E で適用確認')
    await page.getByRole('button', { name: '修正を適用する' }).click()

    await expect(page.getByText('パッチを適用しました。')).toBeVisible()
    await expect(page.getByText('適用済み')).toBeVisible()
    await expect(page.getByRole('button', { name: '修正を適用する' })).toBeDisabled()
    await expect(page.getByRole('button', { name: '却下する' })).toBeDisabled()

    const course = await getCourse(request, seed.courseId)
    expect(course.version).toBe(2)
    expect(course.markdown).toContain('### 例外条件')
    expect(course.latestPatchId).toMatch(/^[0-9a-f]+$/)
  })

  test('無効な share token ではドリル内容を表示しない', async ({ page }) => {
    await page.goto('/drills/invalid-token')

    await expect(page.getByText('共有 URL が無効です。')).toBeVisible()
    await expect(page.getByRole('button', { name: '回答を提出する' })).toHaveCount(0)
    await expect(page.getByText('q1 の業務判断')).toHaveCount(0)
    await expect(page.getByText('4 pts')).toHaveCount(0)
  })

  test('削除した講座の共有 URL は無効になる', async ({ page, request }) => {
    const seed = await createDrillRun(request)

    const deleted = await request.delete(`${apiBaseUrl}/api/courses/${seed.courseId}`)
    expect(deleted.status()).toBe(204)

    await page.goto(seed.shareUrl)

    await expect(page.getByText('共有 URL が無効です。')).toBeVisible()
    await expect(page.getByRole('button', { name: '回答を提出する' })).toHaveCount(0)
  })

  test('新版は固定共有 URL を引き継ぎ、受付を停止・再開できる', async ({
    page,
    request,
  }) => {
    const first = await createDrillRun(request)
    const generated = await request.post(
      `${apiBaseUrl}/api/courses/${first.courseId}/drill-runs`,
    )
    expect(generated.ok()).toBeTruthy()
    const second = (await generated.json()) as { drillRunId: string; shareUrl: string }

    expect(second.shareUrl).toBe(first.shareUrl)
    const oldAdmin = await getAdminDrill(request, first.courseId, first.drillRunId)
    expect(oldAdmin.shareStatus).toBe('superseded')
    const learner = await getLearnerDrill(request, first.shareToken)
    expect(learner.drillRunId).toBe(second.drillRunId)

    await page.goto(`/courses/${first.courseId}/drill-runs/${second.drillRunId}`)
    await page.getByRole('button', { name: '回答受付を終了' }).click()
    await expect(page.getByText('受付停止中')).toBeVisible()

    await page.goto(first.shareUrl)
    await expect(page.getByText('このドリルの回答受付は終了しました。')).toBeVisible()

    await page.goto(`/courses/${first.courseId}/drill-runs/${second.drillRunId}`)
    await page.getByRole('button', { name: '回答受付を再開' }).click()
    await expect(page.getByText('回答受付中')).toBeVisible()
    const reopened = await request.get(`${apiBaseUrl}/api/drills/${first.shareToken}`)
    expect(reopened.ok()).toBeTruthy()
    const reopenedPage = await page.context().newPage()
    await reopenedPage.goto(first.shareUrl)
    await expect(reopenedPage.getByRole('heading', { name: '確認ドリル' })).toBeVisible()
    await reopenedPage.close()
  })

  test('デモ講座の受講者画面でも rubric と ideal answer は表示しない', async ({
    page,
    request,
  }) => {
    const demo = await getDemoCourse(request, 'DevOps x AI Agent Hackathon 2026 参加ガイド')
    expect(demo.latestDrillRunId).toBeTruthy()
    const adminDrill = await getAdminDrill(request, demo.id, demo.latestDrillRunId ?? '')
    expect(adminDrill.shareUrl).toBeTruthy()

    await page.goto(adminDrill.shareUrl ?? '')

    await expect(page.getByRole('heading', { name: '確認ドリル' })).toBeVisible()
    await expect(page.getByText('教材バージョン v1')).toBeVisible()
    await expect(page.getByText('ルーブリック')).toHaveCount(0)
    await expect(page.getByText('模範解答')).toHaveCount(0)
    await expect(page.getByText(/idealAnswer/i)).toHaveCount(0)

    await page.getByRole('button', { name: '回答に進む' }).click()

    await expect(page.getByText('教材を確認する')).toHaveCount(0)
    await expect(page.getByText('ルーブリック')).toHaveCount(0)
    await expect(page.getByText('模範解答')).toHaveCount(0)
    await expect(page.getByText(/idealAnswer/i)).toHaveCount(0)
  })

  test('stale patch は Apply できない', async ({ page, request }) => {
    const seed = await createPatch(request)

    await updateCourse(request, seed.courseId, {
      title: 'E2E Stale Patch Updated',
      markdown: `${courseMarkdown}\n\n## 追記\nPatch 作成後の手動更新。`,
    })

    await page.goto(`/courses/${seed.courseId}/drill-runs/${seed.drillRunId}/analysis?patchId=${seed.patchId}`)

    await expect(page.getByText('このパッチは古くなっています。再分析が必要です。')).toBeVisible()
    await expect(page.getByText('要再分析')).toBeVisible()
    await expect(page.getByRole('button', { name: '修正を適用する' })).toBeDisabled()
    await expect(page.getByRole('button', { name: '却下する' })).toBeDisabled()
  })
})

async function createDrillRun(request: APIRequestContext): Promise<DrillRunSeed> {
  const created = await request.post(`${apiBaseUrl}/api/courses`, {
    data: {
      title: `E2E Course ${Date.now()}`,
      markdown: courseMarkdown,
    },
  })
  expect(created.ok()).toBeTruthy()
  const { courseId } = (await created.json()) as { courseId: string }

  const generated = await request.post(`${apiBaseUrl}/api/courses/${courseId}/drill-runs`)
  expect(generated.ok()).toBeTruthy()
  const { drillRunId, shareUrl } = (await generated.json()) as {
    drillRunId: string
    shareUrl: string
  }

  return {
    courseId,
    drillRunId,
    shareUrl,
    shareToken: shareUrl.split('/').at(-1) ?? '',
  }
}

async function createAnsweredDrillRun(request: APIRequestContext): Promise<DrillRunSeed> {
  const seed = await createDrillRun(request)
  const drill = await getLearnerDrill(request, seed.shareToken)

  const submitted = await request.post(`${apiBaseUrl}/api/drills/${seed.shareToken}/answers`, {
    data: {
      learnerName: 'E2E Learner',
      answers: drill.questions.map((question) => ({
        questionId: question.id,
        answerText: `${question.id} の回答。根拠と例外条件を説明します。`,
      })),
    },
  })
  expect(submitted.ok()).toBeTruthy()

  return seed
}

async function createPatch(request: APIRequestContext): Promise<PatchSeed> {
  const seed = await createAnsweredDrillRun(request)
  const analyzed = await request.post(
    `${apiBaseUrl}/api/courses/${seed.courseId}/drill-runs/${seed.drillRunId}/analyze`,
  )
  expect(analyzed.ok()).toBeTruthy()
  const { patchId } = (await analyzed.json()) as { patchId: string }
  return { ...seed, patchId }
}

async function getLearnerDrill(
  request: APIRequestContext,
  shareToken: string,
): Promise<LearnerDrill> {
  const response = await request.get(`${apiBaseUrl}/api/drills/${shareToken}`)
  expect(response.ok()).toBeTruthy()
  return (await response.json()) as LearnerDrill
}

async function getCourse(request: APIRequestContext, courseId: string): Promise<CourseDetail> {
  const response = await request.get(`${apiBaseUrl}/api/courses/${courseId}`)
  expect(response.ok()).toBeTruthy()
  return (await response.json()) as CourseDetail
}

async function getDemoCourse(
  request: APIRequestContext,
  titlePart: string,
): Promise<CourseSummary> {
  const response = await request.get(`${apiBaseUrl}/api/courses`)
  expect(response.ok()).toBeTruthy()
  const payload = (await response.json()) as CourseListResponse
  const demo = payload.courses.find(
    (course) => course.isDemo && course.title.includes(titlePart),
  )
  expect(demo).toBeTruthy()
  return demo as CourseSummary
}

async function getAdminDrill(
  request: APIRequestContext,
  courseId: string,
  drillRunId: string,
): Promise<AdminDrill> {
  const response = await request.get(
    `${apiBaseUrl}/api/courses/${courseId}/drill-runs/${drillRunId}`,
  )
  expect(response.ok()).toBeTruthy()
  return (await response.json()) as AdminDrill
}

async function updateCourse(
  request: APIRequestContext,
  courseId: string,
  payload: { title: string; markdown: string },
): Promise<CourseDetail> {
  const response = await request.put(`${apiBaseUrl}/api/courses/${courseId}`, {
    data: payload,
  })
  expect(response.ok()).toBeTruthy()
  return (await response.json()) as CourseDetail
}
