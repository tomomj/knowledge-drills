import { expect, test, type Page } from '@playwright/test'

// 審査員の初回導線を一周する回帰テスト。
// UX_AUDIT_SHOT_DIR を指定すると各ステップのスクリーンショットを保存する
// (README / ProtoPedia 用素材の一括撮影を兼ねる)。未指定なら純粋なテストとして動く。
const backendPort = process.env.E2E_BACKEND_PORT ?? '8000'
const apiBaseUrl = process.env.E2E_API_BASE_URL ?? `http://127.0.0.1:${backendPort}`
const shotDir = process.env.UX_AUDIT_SHOT_DIR

type CourseSummary = {
  id: string
  title: string
  latestDrillRunId: string | null
  isDemo: boolean
  answerCount: number
  patchStatus: string | null
}

async function shot(page: Page, name: string) {
  if (shotDir) {
    await page.screenshot({ path: `${shotDir}/${name}.png`, fullPage: true })
  }
}

test.describe('デモ導線: 審査員の改善ループ一周', () => {
  test('シード → 回答 → 分析 → 適用 → スコア確認まで導線が切れない', async ({
    page,
    request,
  }) => {
    test.setTimeout(180_000)

    // 1. 講座一覧(初回アクセスでデモ講座がシードされる)
    await page.goto('/')
    await expect(page.getByText('体験用デモ講座を開くと', { exact: false })).toBeVisible()
    const needsAnalysisWarning = '低スコア回答が蓄積 — 分析推奨'
    const hackathonRow = page.locator('.course-row').filter({
      hasText: 'DevOps x AI Agent Hackathon 2026 参加ガイド(デモ)',
    })
    const expenseRow = page.locator('.course-row').filter({
      hasText: '経費精算の判断基準(デモ・改善 3 周済み)',
    })
    await expect(hackathonRow).toHaveCount(1)
    await expect(hackathonRow.getByText(needsAnalysisWarning, { exact: true })).toBeVisible()
    await expect(expenseRow).toHaveCount(1)
    await expect(expenseRow.getByText(needsAnalysisWarning, { exact: true })).toHaveCount(0)
    await shot(page, '01-course-list')

    const listResponse = await request.get(`${apiBaseUrl}/api/courses`)
    const list = (await listResponse.json()) as { courses: CourseSummary[] }
    const demoCourses = list.courses.filter((course) => course.isDemo)
    const playable = demoCourses.find((course) => course.answerCount > 0 && !course.patchStatus)
    const finished = demoCourses.find((course) => course.patchStatus === 'applied')
    expect(playable, '体験用デモ講座(回答済み・パッチ未提案)がシードされる').toBeTruthy()
    expect(finished, '結果閲覧用デモ講座(改善済み)がシードされる').toBeTruthy()

    // 2. デモ講座①の講座管理とドリル確認
    await page.goto(`/courses/${playable!.id}`)
    await expect(page.getByRole('heading', { name: '講座管理' })).toBeVisible()
    await shot(page, '02-course-editor-demo1')

    await page.goto(`/courses/${playable!.id}/drill-runs/${playable!.latestDrillRunId}`)
    await expect(page.getByRole('button', { name: '回答を分析する' })).toBeEnabled()
    await shot(page, '03-drill-admin')

    // 3. 受講者として share URL から回答し、その場で採点される
    const shareText = await page.locator('text=/drills\\//').first().textContent()
    const shareUrl = shareText?.match(/\/drills\/[\w-]+/)?.[0]
    expect(shareUrl, '共有 URL がドリル確認に表示される').toBeTruthy()

    const learnerPage = await page.context().newPage()
    await learnerPage.goto(shareUrl!)
    await expect(learnerPage.getByRole('heading', { name: '確認ドリル' })).toBeVisible()
    await shot(learnerPage, '04-learner-drill')

    await learnerPage.getByRole('button', { name: '回答に進む' }).click()
    await learnerPage.getByLabel('お名前').fill('審査員E')
    const answerBoxes = learnerPage.locator('textarea')
    const answerCount = await answerBoxes.count()
    for (let index = 0; index < answerCount; index += 1) {
      await answerBoxes.nth(index).fill('agent と人間の役割分担を決めて短い改善サイクルで回す。')
    }
    await learnerPage.getByRole('button', { name: '回答を提出する' }).click()
    await expect(learnerPage.getByText('提出が完了しました。')).toBeVisible({ timeout: 30_000 })
    await shot(learnerPage, '05-learner-graded')
    await learnerPage.close()

    // 4. 分析実行 → 資料修正案レビューへ自動遷移
    await page.reload()
    const analyzeButton = page.getByRole('button', { name: '回答を分析する' })
    await expect(analyzeButton).toBeEnabled()
    await analyzeButton.click()
    await expect(page.getByRole('heading', { name: '資料修正案のレビュー' })).toBeVisible({
      timeout: 90_000,
    })
    await expect(page.getByText('分析タイムライン')).toBeVisible()
    await shot(page, '06-patch-review-proposed')

    // 5. 適用 → 行き止まりにならず、スコアの推移への導線が出る
    await page.getByRole('button', { name: '修正を適用する' }).click()
    const scoreLink = page.getByRole('link', { name: '講座管理でスコアの推移を確認 →' })
    await expect(scoreLink).toBeVisible()
    await shot(page, '07-patch-review-applied')

    await scoreLink.click()
    await expect(page.getByRole('heading', { name: '講座管理' })).toBeVisible()
    await shot(page, '08-course-editor-after-apply')

    // 6. デモ講座②で改善の証拠(スコアの推移・バージョン別平均点)が見える
    await page.goto(`/courses/${finished!.id}`)
    await expect(page.getByText('スコアの推移')).toBeVisible()
    await shot(page, '09-course-editor-demo2-score')

    await page.goto(`/courses/${finished!.id}/history`)
    await expect(page.getByText(/平均 [\d.]+ \/ \d+ 点/).first()).toBeVisible()
    await shot(page, '10-course-history-demo2')

    if (finished!.latestDrillRunId) {
      await page.goto(`/courses/${finished!.id}/drill-runs/${finished!.latestDrillRunId}`)
      await expect(page.getByRole('heading', { name: 'ドリル確認' })).toBeVisible()
      await shot(page, '11-drill-admin-demo2')
    }
  })
})
