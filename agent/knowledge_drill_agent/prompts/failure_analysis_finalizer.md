採点済み回答、並列分析所見、evidence review、critic review を統合し、backend に返す最終 FailureAnalysisOutput を作成してください。

参照できる state:
- 承認済み finding（Failure Signal の唯一の finding source）: {approved_findings}
- review 終了理由: {review_termination_reason}
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
- affectedCount
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
- failureSignals は approved_findings に含まれる finding だけから作成してください。criticReview.approvedFindingIds や自由文を再解釈して採用対象を増やしてはいけません。
- misconception_findings / doc_gap_findings / question_quality_findings の raw analyst state は perspectives と表示用 reviewNotes の要約にだけ使用し、Failure Signal の finding source には使用しないでください。
- evidenceReview の rejectedFindings、criticReview の自由文、summary、rationale から「承認済み」と推測してはいけません。
- review_termination_reason が max_iterations_partial の場合は、criticReview の最新 issues、revisionInstructions、riskNotes を critic_reviewer または finalizer の reviewNotes に明示してください。
- approved_findings は deterministic gate で検証済みです。そこにない finding から埋め合わせを作らないでください。
- approved_findings が空の場合、failureSignals は空配列で返してください。これは「patch を提案しない」という正当な見送り判断です。
- failureSignals を空で返す場合は、source=finalizer / timelineStep=decide_patch_strategy の reviewNote に、所見が承認されなかったため patch 提案を見送る判断であることを記録してください。

reviewNotes の割り当て:
- evidence_critic の採用・棄却・リスク要約は timelineStep=match_course_evidence に置いてください。
- critic_reviewer の verdict、approvedFindingIds、未解決 issue は timelineStep=decide_patch_strategy に置いてください。
- finalizer の採用方針や partial 採用の注意は timelineStep=decide_patch_strategy に置いてください。

ルール:
- affectedCount には、その誤答傾向を示した受講者数を設定してください。
- sampleSize には、その誤答傾向を示した受講者数ではなく、提供された採点済み回答の受講者総数を設定してください。何人がその傾向を示したかは affectedCount に記録してください。
- affectedCount / sampleSize が構造化された人数情報です。evidence や reviewNotes の自由文では「3名中3名」「100%」のような人数比や割合を書かず、該当する missingPoints / failureTags / questionId / target section などの根拠を記載してください。
- sampleSize が3未満の場合は confidenceNote を含め、小さいサンプルに基づく傾向として表現してください。
- severity は low / medium / high のいずれかだけを使ってください。
- 講座 Markdown に存在しない社内ルール、方針、事実、義務を創作しないでください。
- 受講者を責めないでください。
- Chain-of-thought、内部推論、プロンプト本文を reviewNotes や failureSignals に含めないでください。
- 受講者や講座オーナーに表示される文章は日本語で書いてください。
