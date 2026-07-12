// セクション切り替えカードを PNG(3420×1894)にレンダリングする。
// playwright を解決するため frontend ディレクトリから実行する:
//   cd frontend && node ../docs/video/cards/render.mjs
import { pathToFileURL } from 'node:url'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { homedir } from 'node:os'
import { mkdirSync } from 'node:fs'

const { chromium } = await import(
  pathToFileURL(join(process.cwd(), 'node_modules/playwright/index.mjs')).href
)

const cardHtml = pathToFileURL(join(dirname(fileURLToPath(import.meta.url)), 'card.html')).href
const OUT = join(homedir(), 'Desktop', 'kd-video-cards')
mkdirSync(OUT, { recursive: true })

const cards = [
  {
    file: '00-title',
    step: '',
    title: '書いた瞬間から\n腐っていくドキュメントに、\nDevOps を。',
    sub: '',
    footer: 'Knowledge Drills — ナレッジの CI/CD',
  },
  {
    file: '00b-problem',
    step: '課題',
    title: 'コードには、DevOps がある。\nドキュメントには、<span class="accent">ない。</span>',
    sub: 'テストが落ちればコードは直せる。でも「読者がどこでつまずいたか」は、作者に届かない。',
    footer: '',
  },
  {
    file: '01-register',
    step: 'STEP 1 — つくる',
    title: 'ドキュメントを登録する',
    sub: 'AI が教材から、根拠付きの確認ドリルを生成します。',
    footer: '',
  },
  {
    file: '02-share',
    step: 'STEP 2 — とどける',
    title: '公開 URL を配る',
    sub: '受講者はログイン不要で回答。\nその回答が、ドキュメントのテレメトリになります。',
    footer: '',
  },
  {
    file: '03-auto',
    step: 'STEP 3 — まわす',
    title: '回答が 3 件たまると、\n<span class="accent">誰も押していないのに</span>\n分析が始まる',
    sub: 'つまずきの特定 → 教材根拠の照合 → 改善判断 → 修正案の作成。',
    footer: '',
  },
  {
    file: '04-gate',
    step: 'STEP 4 — 人間のゲート',
    title: '起案は AI、判断は人間。',
    sub: '差分とリスクを確認して、承認された変更だけが教材に反映されます。',
    footer: '',
  },
  {
    file: '05-score',
    step: 'STEP 5 — 効果を確かめる',
    title: '改善が、数字で証明された。',
    sub: '教材バージョンごとに平均スコアを再観測します。',
    footer: '',
  },
  {
    file: '06-always-on',
    step: 'STEP 6 — 見張り続ける',
    title: 'ドキュメントは使われる限り、\nまた腐る。',
    sub: '新しいつまずきが増えれば、エージェントはまた自分で動き出します。',
    footer: '',
  },
  {
    file: '07-closing',
    step: '',
    title: 'つくる、まわす、とどける —\n<span class="accent">ナレッジにも。</span>',
    sub: 'Gemini × Google ADK × Cloud Run\ngithub.com/tomomj/knowledge-drills',
    footer: '',
  },
]

const browser = await chromium.launch({ channel: 'chrome' })
const page = await browser.newPage({
  viewport: { width: 1710, height: 947 },
  deviceScaleFactor: 2,
})

for (const card of cards) {
  await page.goto(cardHtml)
  await page.evaluate((c) => {
    document.getElementById('step').textContent = c.step
    document.getElementById('title').innerHTML = c.title.replaceAll('\n', '<br>')
    document.getElementById('sub').textContent = c.sub
    document.getElementById('footer').textContent = c.footer
  }, card)
  await page.waitForTimeout(150)
  await page.screenshot({ path: join(OUT, `${card.file}.png`) })
  console.log(`rendered ${card.file}`)
}

await browser.close()
