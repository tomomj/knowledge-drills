import type {
  AnalysisStartResponse,
  AnswerPayload,
  ApiError,
  CourseCreateResponse,
  CourseDetail,
  CourseListResponse,
  CoursePayload,
  CourseRevisionDiff,
  CourseRevisionListResponse,
  CurrentUser,
  DocumentPatch,
  DrillAdmin,
  DrillAnswersResponse,
  DrillGenerationStartResponse,
  LearnerDrill,
  PatchDecisionPayload,
  SubmitAnswerResponse,
} from './types'
import { getAuthToken } from '../lib/authToken'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiClientError extends Error {
  readonly error: ApiError
  readonly status: number

  constructor(status: number, error: ApiError) {
    super(error.message)
    this.name = 'ApiClientError'
    this.status = status
    this.error = error
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = await buildHeaders(init?.headers)
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  })
  const payload = (await response.json().catch(() => null)) as T | ApiError | null
  if (!response.ok) {
    throw new ApiClientError(response.status, normalizeError(payload))
  }
  return payload as T
}

async function buildHeaders(initHeaders?: HeadersInit): Promise<Headers> {
  const headers = new Headers(initHeaders)
  if (!headers.has('content-type')) {
    headers.set('content-type', 'application/json')
  }
  const authToken = await getAuthToken()
  if (authToken) {
    headers.set('authorization', `Bearer ${authToken}`)
  }
  return headers
}

function normalizeError(payload: unknown): ApiError {
  if (isApiError(payload)) {
    return payload
  }
  return { code: 'network_error', message: 'リクエストに失敗しました。' }
}

function isApiError(payload: unknown): payload is ApiError {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'code' in payload &&
    'message' in payload
  )
}

export const api = {
  getCurrentUser: () => requestJson<CurrentUser>('/api/me'),
  createCourse: (payload: CoursePayload) =>
    requestJson<CourseCreateResponse>('/api/courses', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listCourses: () => requestJson<CourseListResponse>('/api/courses'),
  getCourse: (courseId: string) => requestJson<CourseDetail>(`/api/courses/${courseId}`),
  updateCourse: (courseId: string, payload: CoursePayload) =>
    requestJson<CourseDetail>(`/api/courses/${courseId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  listCourseRevisions: (courseId: string) =>
    requestJson<CourseRevisionListResponse>(`/api/courses/${courseId}/revisions`),
  diffCourseRevisions: (courseId: string, fromVersion: number, toVersion: number) =>
    requestJson<CourseRevisionDiff>(
      `/api/courses/${courseId}/revisions/diff?from=${fromVersion}&to=${toVersion}`,
    ),
  generateDrill: (courseId: string) =>
    requestJson<DrillGenerationStartResponse>(`/api/courses/${courseId}/drill-runs`, {
      method: 'POST',
    }),
  getDrill: (courseId: string, drillRunId: string) =>
    requestJson<DrillAdmin>(`/api/courses/${courseId}/drill-runs/${drillRunId}`),
  getDrillAnswers: (courseId: string, drillRunId: string) =>
    requestJson<DrillAnswersResponse>(`/api/courses/${courseId}/drill-runs/${drillRunId}/answers`),
  analyzeDrill: (courseId: string, drillRunId: string) =>
    requestJson<AnalysisStartResponse>(
      `/api/courses/${courseId}/drill-runs/${drillRunId}/analyze`,
      { method: 'POST' },
    ),
  getLearnerDrill: (shareToken: string) =>
    requestJson<LearnerDrill>(`/api/drills/${shareToken}`),
  submitAnswer: (shareToken: string, payload: AnswerPayload) =>
    requestJson<SubmitAnswerResponse>(`/api/drills/${shareToken}/answers`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getPatch: (patchId: string) => requestJson<DocumentPatch>(`/api/patches/${patchId}`),
  applyPatch: (patchId: string, payload: PatchDecisionPayload) =>
    requestJson<DocumentPatch>(`/api/patches/${patchId}/apply`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  rejectPatch: (patchId: string, payload: PatchDecisionPayload) =>
    requestJson<DocumentPatch>(`/api/patches/${patchId}/reject`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}
