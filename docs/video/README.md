# デモ動画の制作アセット

デモ動画(3分)の素材は、すべてこのディレクトリのコードとテキストから再現できます。
教材を Markdown とバージョンで管理するのと同じ発想で、動画素材もコードで管理しています。

制作は Claude Code との共同作業で行いました(台本の構成・カードのデザイン・
ナレーションの読み調整・各テイクのフレームレビュー)。

## 構成

| パス | 内容 |
|---|---|
| [`narration.md`](narration.md) | ナレーション全17クリップの台本・尺・対応する画面 |
| [`tts-gemini.sh`](tts-gemini.sh) | Gemini TTS(Vertex AI)でナレーション音声を生成するスクリプト |
| [`cards/card.html`](cards/card.html) | セクション切り替えカードのテンプレート |
| [`cards/render.mjs`](cards/render.mjs) | カードを PNG(3420×1894)にレンダリングするスクリプト |
| `cards/*.png` | レンダリング済みのカード一式 |

## ナレーションの再生成

Cloud Text-to-Speech / Vertex AI が使える GCP プロジェクトで:

```bash
export GOOGLE_CLOUD_PROJECT=<your-project>
gcloud auth application-default login
./tts-gemini.sh "読み上げるテキスト" out.wav Charon "落ち着いたナレーターとして"
```

- ボイスは Gemini TTS のプリセット(採用: `Charon`)。スタイルは日本語で指示できる
- 誤読はテキスト側で直す(例: 「腐っていく→くさっていく」「Knowledge Drills→ナレッジドリルズ」「DevOps→デブオプス」)。実際の入力は `narration.md` の「TTS 入力」列を参照

## カードの再生成

```bash
cd frontend   # playwright を利用するため
node ../docs/video/cards/render.mjs
```

文言は `render.mjs` の `cards` 配列を編集する。出力先は `~/Desktop/kd-video-cards/`。
