#!/bin/bash
# Gemini TTS (Vertex AI) で日本語ナレーションを生成する。スタイルを日本語で指示できる。
#
# 事前準備:
#   export GOOGLE_CLOUD_PROJECT=<your-project>
#   gcloud auth application-default login
#
# 使い方:
#   ./tts-gemini.sh "読み上げるテキスト" 出力ファイル.wav [ボイス名] [スタイル指示]
#
# 例:
#   ./tts-gemini.sh "こんにちは" hello.wav
#   ./tts-gemini.sh "こんにちは" hello.wav Charon "熱意のあるプレゼンターとして"
#
# ボイス: Kore, Aoede, Leda, Zephyr(女性) / Charon, Puck, Fenrir(男性) など

set -euo pipefail

TEXT="${1:?テキストを指定してください}"
OUT="${2:?出力ファイル名(.wav)を指定してください}"
VOICE="${3:-Charon}"
STYLE="${4:-落ち着いたプロダクト紹介のナレーターとして、自然なイントネーションで読んでください}"
PROJECT="${GOOGLE_CLOUD_PROJECT:?GOOGLE_CLOUD_PROJECT を設定してください}"

TOKEN=$(gcloud auth application-default print-access-token)
REQUEST_FILE=$(mktemp)
RAW_FILE=$(mktemp)
trap 'rm -f "$REQUEST_FILE" "$RAW_FILE"' EXIT

python3 - "$STYLE: $TEXT" "$VOICE" <<'EOF' > "$REQUEST_FILE"
import json, sys
print(json.dumps({
    "contents": [{"role": "user", "parts": [{"text": sys.argv[1]}]}],
    "generationConfig": {
        "responseModalities": ["AUDIO"],
        "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": sys.argv[2]}}},
    },
}))
EOF

curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @"$REQUEST_FILE" \
  "https://aiplatform.googleapis.com/v1/projects/$PROJECT/locations/global/publishers/google/models/gemini-2.5-flash-preview-tts:generateContent" \
  | python3 -c "
import json, sys, base64
d = json.load(sys.stdin)
parts = d['candidates'][0]['content']['parts']
for p in parts:
    if 'inlineData' in p:
        sys.stdout.buffer.write(base64.b64decode(p['inlineData']['data']))
" > "$RAW_FILE"

ffmpeg -v error -y -f s16le -ar 24000 -ac 1 -i "$RAW_FILE" -ar 48000 "$OUT"

if command -v ffprobe >/dev/null 2>&1; then
  DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")
  printf "%s  (%.1f秒, voice=%s)\n" "$OUT" "$DUR" "$VOICE"
else
  echo "$OUT (voice=$VOICE)"
fi
