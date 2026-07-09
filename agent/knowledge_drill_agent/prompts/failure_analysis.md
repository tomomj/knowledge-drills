採点済み回答を分析し、社内ルールを創作せずに、繰り返し発生している Failure Signal を抽出してください。

最終出力では次の field を返してください。
- failureSignals
- perspectives

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

perspectives には、可能な限り次の3件の観点別所見を返してください。
- id: material_gap, title: 教材ギャップ, summary: 教材ギャップ視点の1行要約
- id: question_quality, title: 設問品質, summary: 設問品質視点の1行要約
- id: learner_pattern, title: つまずきパターン, summary: つまずきパターン視点の1行要約

ルール:
- 孤立したミスよりも、複数回答にまたがる繰り返しパターンを優先してください。
- affectedCount には、その誤答傾向を示した受講者数を設定してください。
- sampleSize には、その誤答傾向を示した受講者数ではなく、提供された採点済み回答の受講者総数を設定してください。何人がその傾向を示したかは affectedCount に記録してください。
- affectedCount / sampleSize が構造化された人数情報です。evidence の自由文では「3名中3名」「100%」のような人数比や割合を書かず、該当する missingPoints / failureTags / questionId / target section などの根拠を記載してください。
- sampleSize が3未満の場合は confidenceNote を含め、小さいサンプルに基づく傾向として表現してください。
- 受講者の理解不足と、資料側の説明不足の可能性を区別してください。
- 受講者を責めないでください。
- 講座 Markdown に存在しない社内ルール、方針、事実、義務を創作しないでください。
- 必要な evidence であり、かつ入力で提供済みの場合を除き、受講者回答の原文を含めないでください。
- 受講者や講座オーナーに表示される文章は日本語で書いてください。
