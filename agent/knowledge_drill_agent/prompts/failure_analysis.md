採点済み回答を分析し、社内ルールを創作せずに、繰り返し発生している Failure Signal を抽出してください。

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

ルール:
- 孤立したミスよりも、複数回答にまたがる繰り返しパターンを優先してください。
- sampleSize が3未満の場合は confidenceNote を含め、小さいサンプルに基づく傾向として表現してください。
- 受講者の理解不足と、資料側の説明不足の可能性を区別してください。
- 受講者を責めないでください。
- 講座 Markdown に存在しない社内ルール、方針、事実、義務を創作しないでください。
- 必要な evidence であり、かつ入力で提供済みの場合を除き、受講者回答の原文を含めないでください。
- 受講者や講座オーナーに表示される文章は日本語で書いてください。
