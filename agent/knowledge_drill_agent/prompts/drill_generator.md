提供された講座 Markdown から、実務シナリオ型の自由記述ドリルを必ず3問生成してください。

各設問では、受講者に実務上の判断とその理由を説明させてください。
単純な用語定義や暗記確認の設問にはしないでください。

各設問では次の field を返してください。
- id
- question
- intent
- rubric
- idealAnswer
- sourceEvidence
- maxScore

ルール:
- 必ず3問だけ生成してください。
- すべての設問で maxScore は4にしてください。
- すべての設問で rubric の points 合計を必ず4にしてください。
- すべての設問に、提供された講座 Markdown から取得した sectionHeading と excerpt を持つ sourceEvidence を1件以上含めてください。
- 講座 Markdown に根拠がない内容を問わないでください。
- deployment details、Firestore path、secret、share token を出力しないでください。
- 受講者に表示される文章は日本語で書いてください。
