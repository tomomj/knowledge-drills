Analyze graded answer results for repeated failure signals without inventing company rules.

Return each Failure Signal with:
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

Rules:
- Prioritize repeated patterns across answers over isolated mistakes.
- If sampleSize is under 3, include confidenceNote and phrase the signal as a small-sample trend.
- Separate learner misunderstanding from likely documentation gaps.
- Do not blame learners.
- Do not invent company rules, policies, facts, or obligations not present in the course Markdown.
- Do not include raw learner answer text unless it is necessary evidence and already supplied.
