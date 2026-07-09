import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  addAuthUnauthorizedListener,
  clearAuthUnauthorizedListeners,
} from '../lib/authEvents'
import { resetAuthTokenProvider, setAuthTokenProvider } from '../lib/authToken'
import { api } from './client'
import type { CourseMetricsResponse } from './types'

function mockFetchJson(payload: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue(payload),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function requestHeaders(fetchMock: ReturnType<typeof mockFetchJson>): Headers {
  const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined
  return init?.headers as Headers
}

describe('api client auth token', () => {
  afterEach(() => {
    clearAuthUnauthorizedListeners()
    resetAuthTokenProvider()
    vi.unstubAllGlobals()
  })

  it('adds a bearer authorization header when the token provider returns a token', async () => {
    const fetchMock = mockFetchJson({ courses: [] })
    setAuthTokenProvider(async () => 'mock-id-token')

    await api.listCourses()

    expect(requestHeaders(fetchMock).get('authorization')).toBe('Bearer mock-id-token')
  })

  it('does not add authorization when the token provider returns null', async () => {
    const fetchMock = mockFetchJson({ courses: [] })
    setAuthTokenProvider(async () => null)

    await api.listCourses()

    expect(requestHeaders(fetchMock).get('authorization')).toBeNull()
  })

  it('notifies auth listeners when an authenticated API returns 401', async () => {
    const listener = vi.fn()
    addAuthUnauthorizedListener(listener)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: vi.fn().mockResolvedValue({ code: 'unauthenticated', message: 'expired' }),
      }),
    )

    await expect(api.listCourses()).rejects.toMatchObject({ status: 401 })

    expect(listener).toHaveBeenCalledOnce()
  })

  it('requests course metrics for a course', async () => {
    const metrics: CourseMetricsResponse = {
      courseId: 'course-1',
      runs: [
        {
          drillRunId: 'drill-1',
          courseVersion: 1,
          answerCount: 2,
          averageScore: 3.5,
          maxScore: 4,
        },
      ],
    }
    const fetchMock = mockFetchJson(metrics)

    await expect(api.getCourseMetrics('course-1')).resolves.toEqual(metrics)

    expect(fetchMock).toHaveBeenCalledWith('/api/courses/course-1/metrics', expect.any(Object))
  })

  it('deletes a course', async () => {
    const fetchMock = mockFetchJson(null)

    await api.deleteCourse('course-1')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/courses/course-1',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })
})
