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
  drillFocus: string | null
  version: number
  latestDrillRunId: string | null
  latestPatchId: string | null
}

export type CourseScoreTrendPoint = {
  courseVersion: number
  averageScore: number
  maxScore: number
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
  scoreTrend: CourseScoreTrendPoint[] | null
  isDemo: boolean
  needsAnalysis: boolean
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
  drillFocus?: string | null
}

export type CourseCreateResponse = {
  courseId: string
}

export type CurrentUser = {
  uid: string
  email: string | null
  displayName: string | null
  photoUrl: string | null
  createdAt: string
  lastLoginAt: string
  demoSeededAt: string | null
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

export type AnalysisStepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped'

export type AnalysisTimelineItem = {
  id: string
  title: string
  status: AnalysisStepStatus
  summary: string | null
  evidence: string[]
  completedAt: string | null
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

export type ShareStatus = 'open' | 'closed' | 'superseded' | 'unavailable'

export type QuestionScoreSummary = {
  questionId: string
  averageScore: number | null
  maxScore: number
  gradedAnswerCount: number
  commonMissingPoints: string[]
  failureTags: string[]
}

export type DrillScoreSummary = {
  gradedAnswerCount: number
  averageScore: number | null
  maxScore: number
  questions: QuestionScoreSummary[]
}

export type DrillAdmin = {
  id: string
  courseId: string
  courseVersion: number
  drillFocus: string | null
  status: DrillStatus
  questions: AdminQuestion[]
  rubricSummary: string[]
  shareUrl: string | null
  shareStatus: ShareStatus
  answerCount: number
  scoreSummary: DrillScoreSummary | null
  analysisTimeline: AnalysisTimelineItem[]
  canAnalyze: boolean
  errorMessage: string | null
  needsAnalysis: boolean
}

export type DrillGenerationStartResponse = {
  drillRunId: string
  shareUrl: string | null
}

export type LearnerDrill = {
  drillRunId: string
  courseId: string
  courseTitle: string
  courseMarkdown: string
  courseVersion: number
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

export type CourseMetricsRun = {
  drillRunId: string
  courseVersion: number
  answerCount: number
  averageScore: number | null
  maxScore: number | null
}

export type CourseMetricsResponse = {
  courseId: string
  runs: CourseMetricsRun[]
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
  affectedCount: number
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
  analysisTimeline: AnalysisTimelineItem[]
  ownerFeedback: string | null
}

export type PatchDecisionPayload = {
  ownerFeedback: string | null
}

export type AnalysisStartResponse = {
  // null は承認された所見がなくパッチ提案が見送られたことを表す
  patchId: string | null
}
