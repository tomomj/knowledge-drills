import { expect, test, type APIRequestContext } from '@playwright/test'

const backendPort = process.env.E2E_BACKEND_PORT ?? '8000'
const apiBaseUrl = process.env.E2E_API_BASE_URL ?? `http://127.0.0.1:${backendPort}`
const runsLlmE2E = process.env.E2E_LLM === '1'

const llmCourseMarkdown = `# 問い合わせ一次対応

## 判断基準
緊急度が高い問い合わせは、受信から15分以内に担当リーダーへエスカレーションします。

## 通常対応
緊急度が低い問い合わせは、受付内容を記録し、翌営業日までに一次回答を送ります。

## 例外条件
個人情報を含む問い合わせは、内容を転記せず、専用フォームの受付番号だけを共有します。`

type DrillGenerationStartResponse = {
  drillRunId: string
  shareUrl: string
}

type AdminDrill = {
  status: string
  questions: Array<{
    id: string
    question: string
    sourceEvidence: Array<{
      excerpt: string
    }>
  }>
  errorMessage: string | null
}

type SubmitAnswerResponse = {
  status: string
}

type DocumentPatch = {
  status: string
}

test.describe('LLM Agent E2E', () => {
  test.skip(!runsLlmE2E, 'Set E2E_LLM=1 to run the opt-in real LLM E2E.')

  test('実 LLM でドリル生成、採点、分析、patch 提案まで通る', async ({ page, request }) => {
    test.setTimeout(180_000)

    const courseId = await createCourse(request)
    const generated = await generateDrill(request, courseId)
    const adminDrill = await getAdminDrill(request, courseId, generated.drillRunId)

    expect(adminDrill.status).toBe('ready')
    expect(adminDrill.errorMessage).toBeNull()
    expect(adminDrill.questions).toHaveLength(3)
    for (const question of adminDrill.questions) {
      expect(question.sourceEvidence.length).toBeGreaterThan(0)
      for (const evidence of question.sourceEvidence) {
        expect(llmCourseMarkdown).toContain(evidence.excerpt)
      }
    }

    await page.goto(`/courses/${courseId}/drill-runs/${generated.drillRunId}`)
    await expect(page.getByRole('heading', { name: 'ドリル確認' })).toBeVisible()
    await expect(page.locator('.q-card h2')).toHaveCount(3)
    await expect(page.locator('.share-row code')).toContainText('/drills/')

    const shareToken = generated.shareUrl.split('/').at(-1) ?? ''
    const submitted = await submitAnswers(request, shareToken, adminDrill)
    expect(submitted.status).toBe('graded')

    await page.reload()
    await expect(page.getByRole('button', { name: '回答を分析する' })).toBeEnabled()
    await page.getByRole('button', { name: '回答を分析する' }).click()

    await expect(page).toHaveURL(/\/analysis\?patchId=[0-9a-f]+$/, { timeout: 120_000 })
    await expect(page.getByRole('heading', { name: '教材改善案のレビュー' })).toBeVisible()
    await expect(page.getByText('人の確認待ち')).toBeVisible()

    const patchId = new URL(page.url()).searchParams.get('patchId')
    expect(patchId).toMatch(/^[0-9a-f]+$/)
    const patch = await getPatch(request, patchId ?? '')
    expect(patch.status).toBe('proposed')
  })
})

async function createCourse(request: APIRequestContext): Promise<string> {
  const response = await request.post(`${apiBaseUrl}/api/courses`, {
    data: {
      title: `LLM E2E Course ${Date.now()}`,
      markdown: llmCourseMarkdown,
    },
  })
  expect(response.ok()).toBeTruthy()
  const payload = (await response.json()) as { courseId: string }
  return payload.courseId
}

async function generateDrill(
  request: APIRequestContext,
  courseId: string,
): Promise<DrillGenerationStartResponse> {
  const response = await request.post(`${apiBaseUrl}/api/courses/${courseId}/drill-runs`)
  expect(response.ok()).toBeTruthy()
  return (await response.json()) as DrillGenerationStartResponse
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

async function submitAnswers(
  request: APIRequestContext,
  shareToken: string,
  drill: AdminDrill,
): Promise<SubmitAnswerResponse> {
  const response = await request.post(`${apiBaseUrl}/api/drills/${shareToken}/answers`, {
    data: {
      learnerName: 'LLM E2E Learner',
      answers: drill.questions.map((question) => ({
        questionId: question.id,
        answerText: `${question.question} 教材の該当箇所に従って判断し、理由も説明します。`,
      })),
    },
  })
  expect(response.ok()).toBeTruthy()
  return (await response.json()) as SubmitAnswerResponse
}

async function getPatch(request: APIRequestContext, patchId: string): Promise<DocumentPatch> {
  const response = await request.get(`${apiBaseUrl}/api/patches/${patchId}`)
  expect(response.ok()).toBeTruthy()
  return (await response.json()) as DocumentPatch
}
