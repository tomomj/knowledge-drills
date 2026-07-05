Generate exactly three scenario-based free-text drill questions from the supplied course Markdown.

Each question must ask the learner to explain a practical judgment and the reason for it. Do not
write simple terminology-definition questions.

For every question, return:
- id
- question
- intent
- rubric
- idealAnswer
- sourceEvidence
- maxScore

Rules:
- Generate exactly three questions.
- Set maxScore to 4 for every question.
- Make rubric points total exactly 4 for every question.
- Include at least one sourceEvidence object with sectionHeading and excerpt from the supplied course Markdown.
- Do not ask about content that is not grounded in the course Markdown.
- Do not expose deployment details, Firestore paths, secrets, or share tokens.
