受講者回答は、提供された rubric と回答本文だけに基づいて採点してください。

次の field を返してください。
- questionId
- score
- maxScore
- correctPoints
- missingPoints
- feedback
- failureTags

ルール:
- 提供された rubric、ideal answer、source evidence、learner answer だけを使ってください。
- 受講者が書いていない内容を推測、創作、補完して加点しないでください。
- 回答が短すぎる場合も受け付けますが、不足している理由説明を missingPoints と score に反映してください。
- maxScore は4のままにし、score が maxScore を超えないようにしてください。
- failureTags には missing_evidence や unclear_condition のような具体的な不足概念を使ってください。
- 受講者向けの最小限の feedback を超えて、rubric の内部情報を露出しないでください。
- 受講者に表示される文章は日本語で書いてください。
