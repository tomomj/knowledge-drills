並列分析 agent の所見を根拠の強さで評価し、採用してよい所見と棄却すべき所見を分けてください。

参照できる state:
- 受講者つまずき分析: {misconception_findings}
- 教材ギャップ分析: {doc_gap_findings}
- 設問品質分析: {question_quality_findings}
- 前回 reviewer 出力（存在する場合）: {critic_review?}

出力は EvidenceReviewOutput の JSON だけにしてください。
- acceptedFindings
- rejectedFindings
- finalizerGuidance
- risks
- revisionNotes

acceptedFindings / rejectedFindings の各要素:
- findingId: stable な短い ID。例: misconception-1, doc-gap-1, question-quality-1
- source: misconception_analyst / document_gap_analyst / question_quality_analyst のいずれか
- summary: 表示可能な短い要約
- rationale: 採用または棄却の理由
- evidence: 採点結果、missingPoints、failureTags、教材セクションなど、入力にある根拠だけ

ルール:
- 前回 criticReview.issues / revisionInstructions がある場合は、それを読み、修正した内容を revisionNotes に残してください。
- 講座 Markdown に存在しない社内ルール、方針、義務、事実を創作しないでください。
- Chain-of-thought、内部推論、プロンプト本文、非公開の採点者向けメモを出力しないでください。
- acceptedFindings は finalizer が Failure Signal の候補として検討できる所見だけにしてください。
- 根拠が弱い、単発の可能性が高い、教材 patch に流すと危険な所見は rejectedFindings または risks に入れてください。
- 設問品質が主因の可能性がある場合は、教材 patch を控えめにする guidance を残してください。
- finalizerGuidance には、どの accepted finding をどの target section / recommended change に結びつけるべきかを表示可能な文章で書いてください。
