提供された講座 Markdown から、実務シナリオ型の自由記述ドリルを必ず3問生成してください。

入力に drillFocus（出題観点）が含まれる場合は、設問の観点として優先してください。
ただし、drillFocus は出題の優先順位を示す補助情報であり、根拠は必ず講座 Markdown に限定してください。

各設問では、受講者に実務上の判断とその理由を説明させてください。
設問文そのもので理由の記述を明示的に求めてください（例: 設問文の末尾に「判断理由も書いてください。」を付ける）。
単純な用語定義や暗記確認の設問にはしないでください。手順だけを問い、理由を問わない設問にもしないでください。

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
- sourceEvidence.excerpt は講座 Markdown に実在する原文と完全一致する文字列にしてください。
- question、intent、rubric、idealAnswer、sourceEvidence のすべてで、講座 Markdown に明示されている内容だけを使ってください。
- 講座 Markdown に根拠がないルール、数値、期限、手順、例外、目的、背景理由を問わないでください。
- drillFocus（出題観点）に対応する記述が講座 Markdown に無い場合は、drillFocus 由来の業務ルール・数値・例外条件を補わず、教材に実在する内容のみで出題してください。
- 判断理由は「設問の状況が講座 Markdown のどのルールに該当するか」を説明する内容に限定してください。業務調整、リスク低減、給与計算、監査対応など、講座 Markdown に書かれていない目的や背景を補って書かないでください。
- idealAnswer は sourceEvidence の excerpt から直接確認できる内容だけで構成してください。excerpt に目的や背景理由が書かれていない場合は、目的や背景理由を創作せず、該当ルールに従う必要があることだけを書いてください。
- rubric の criterion は sourceEvidence の excerpt から直接採点できる観点だけにしてください。
- sourceEvidence.excerpt は講座 Markdown に存在する文言をそのまま抜粋し、要約や言い換えをしないでください。
- deployment details、Firestore path、secret、share token を出力しないでください。
- 受講者に表示される文章は日本語で書いてください。
