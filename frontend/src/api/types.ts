export type ApiError = {
  code: string
  message: string
  requestId?: string
  currentStatus?: string
}

export type CourseDetail = {
  id: string
  title: string
  markdown: string
  version: number
  latestDrillRunId: string | null
  latestPatchId: string | null
}

export type CourseSummary = {
  id: string
  title: string
  version: number
  updatedAt: string | null
  drillStatus: DrillStatus | null
  answerCount: number
  patchStatus: PatchStatus | null
  latestDrillRunId: string | null
  latestPatchId: string | null
}

export type CourseListResponse = {
  courses: CourseSummary[]
}

export type CourseRevisionSummary = {
  version: number
  title: string
  updatedAt: string | null
}

export type CourseRevisionListResponse = {
  revisions: CourseRevisionSummary[]
}

export type CourseRevisionDiff = {
  fromVersion: number
  toVersion: number
  diffText: string
}

export type CoursePayload = {
  title: string
  markdown: string
}

export type CourseCreateResponse = {
  courseId: string
}

export type RubricItem = {
  criterion: string
  points: number
  required: boolean
}

export type SourceEvidence = {
  sectionHeading: string
  excerpt: string
}

export type AdminQuestion = {
  id: string
  question: string
  intent: string
  rubric: RubricItem[]
  idealAnswer: string
  sourceEvidence: SourceEvidence[]
  maxScore: number
}

export type LearnerQuestion = {
  id: string
  question: string
  maxScore: number
}

export type DrillStatus = 'generating' | 'ready' | 'failed' | 'analyzing' | 'analyzed'

export type DrillAdmin = {
  id: string
  courseId: string
  courseVersion: number
  status: DrillStatus
  questions: AdminQuestion[]
  rubricSummary: string[]
  shareUrl: string | null
  answerCount: number
  canAnalyze: boolean
  errorMessage: string | null
}

export type DrillGenerationStartResponse = {
  drillRunId: string
  shareUrl: string
}

export type LearnerDrill = {
  drillRunId: string
  courseId: string
  questions: LearnerQuestion[]
}

export type GradingResult = {
  questionId: string
  score: number
  maxScore: number
  correctPoints: string[]
  missingPoints: string[]
  feedback: string
  failureTags: string[]
}

export type DrillAnswer = {
  id: string
  learnerName: string
  status: 'grading' | 'graded' | 'failed'
  totalScore: number | null
  maxScore: number | null
  answers: Record<string, string>
  gradingResults: GradingResult[]
}

export type DrillAnswersResponse = {
  courseVersion: number
  answers: DrillAnswer[]
}

export type AnswerPayload = {
  learnerName: string
  answers: Array<{
    questionId: string
    answerText: string
  }>
}

export type SubmitAnswerResponse = {
  answerId: string
  status: 'grading' | 'graded' | 'failed'
  feedback: string[]
}

export type PatchStatus = 'proposed' | 'applied' | 'rejected' | 'stale'

export type FailureSignal = {
  id: string
  title: string
  severity: 'low' | 'medium' | 'high'
  evidence: string[]
  likelyCause: string
  suspectedDocumentGap: string
  targetSections: string[]
  recommendedChange: string
  sampleSize: number
  confidenceNote: string | null
}

export type DocumentPatch = {
  id: string
  courseId: string
  drillRunId: string
  status: PatchStatus
  baseMarkdown: string
  patchedMarkdown: string
  patchSummary: string
  riskNotes: string[]
  diffText: string
  failureSignals: FailureSignal[]
  ownerFeedback: string | null
}

export type PatchDecisionPayload = {
  ownerFeedback: string | null
}

export type AnalysisStartResponse = {
  patchId: string
}
