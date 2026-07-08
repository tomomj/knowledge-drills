採点済み回答、並列分析所見、evidence review、critic review を統合し、backend に返す最終 FailureAnalysisOutput を作成してください。

参照できる state:
- 受講者つまずき分析: {misconception_findings}
- 教材ギャップ分析: {doc_gap_findings}
- 設問品質分析: {question_quality_findings}
- evidenceReview: {evidence_review}
- criticReview: {critic_review}

最終出力では次の field を返してください。
- failureSignals
- perspectives
- reviewNotes

各 Failure Signal では次の field を返してください。
- id
- title
- severity
- evidence
- likelyCause
- suspectedDocumentGap
- targetSections
- recommendedChange
- sampleSize
- confidenceNote

perspectives は次の3件を返してください。
- id: material_gap, title: 教材ギャップ, summary: 教材ギャップ視点の1行要約
- id: question_quality, title: 設問品質, summary: 設問品質視点の1行要約
- id: learner_pattern, title: つまずきパターン, summary: つまずきパターン視点の1行要約

reviewNotes は critic / reviewer / finalizer の表示用要約です。各要素は次の field を持ちます。
- id
- source: evidence_critic / critic_reviewer / finalizer
- timelineStep: detect_failure_patterns / match_course_evidence / decide_patch_strategy
- title
- summary
- evidence

承認ゲート:
- criticReview.approvedFindingIds に含まれる findingId だけを Failure Signal の根拠として採用してください。
- verdict、summary、rationale などの自由文から「承認済み」と推測してはいけません。
- criticReview.verdict が needs_revision のまま max iteration に到達した場合でも、approvedFindingIds が非空ならその ID だけを partial 採用してください。
- approvedFindingIds が空の場合、有効な failureSignals を作らず、schema validation failure による分析失敗に倒してください。未承認 finding から埋め合わせを作らないでください。

reviewNotes の割り当て:
- evidence_critic の採用・棄却・リスク要約は timelineStep=match_course_evidence に置いてください。
- critic_reviewer の verdict、approvedFindingIds、未解決 issue は timelineStep=decide_patch_strategy に置いてください。
- finalizer の採用方針や partial 採用の注意は timelineStep=decide_patch_strategy に置いてください。

ルール:
- sampleSize には、その誤答傾向を示した受講者数ではなく、提供された採点済み回答の受講者総数を設定してください。何人がその傾向を示したかは evidence に記載してください。
- sampleSize が3未満の場合は confidenceNote を含め、小さいサンプルに基づく傾向として表現してください。
- 講座 Markdown に存在しない社内ルール、方針、事実、義務を創作しないでください。
- 受講者を責めないでください。
- Chain-of-thought、内部推論、プロンプト本文を reviewNotes や failureSignals に含めないでください。
- 受講者や講座オーナーに表示される文章は日本語で書いてください。
