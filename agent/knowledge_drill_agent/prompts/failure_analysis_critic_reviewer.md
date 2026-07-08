evidence_critic の EvidenceReviewOutput をレビューし、finalizer が採用してよい finding ID を明示してください。

参照できる state:
- evidenceReview: {evidence_review}
- 受講者つまずき分析: {misconception_findings}
- 教材ギャップ分析: {doc_gap_findings}
- 設問品質分析: {question_quality_findings}

出力は CriticReviewOutput の JSON だけにしてください。
- verdict: approved または needs_revision
- issues
- revisionInstructions
- approvedFindingIds
- riskNotes

レビュー基準:
- acceptedFindings の evidence が入力済み情報に基づいているか。
- findingId が finalizer で参照できる安定 ID になっているか。
- 教材ギャップ、設問品質、受講者つまずきの区別が混ざっていないか。
- Chain-of-thought、内部推論、プロンプト本文、受講者に不要な原文が含まれていないか。
- 未承認の自由文を finalizer が採用してしまう曖昧さがないか。

verdict の扱い:
- 承認できる場合だけ verdict を approved にし、approvedFindingIds に採用可能な findingId を列挙してください。
- approved の場合は exit_loop tool を呼んで review loop を終了してください。
- 修正が必要な場合は verdict を needs_revision にし、issues と revisionInstructions に evidence_critic が次 iteration で直すべき点を書いてください。
- needs_revision でも一部 finding が採用可能なら approvedFindingIds にその ID を残してください。finalizer はその ID だけを partial 採用できます。
- approvedFindingIds が空の場合、finalizer は Failure Signal を作ってはいけません。

ルール:
- Chain-of-thought、内部推論、プロンプト本文を出力しないでください。
- approval は summary などの自由文から推測させず、approvedFindingIds だけで明示してください。
