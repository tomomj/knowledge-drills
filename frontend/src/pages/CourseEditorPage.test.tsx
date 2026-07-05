import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { CourseEditorPage } from './CourseEditorPage'

vi.mock('../api/client', () => ({
  api: {
    createCourse: vi.fn(),
    updateCourse: vi.fn(),
    generateDrill: vi.fn(),
  },
  ApiClientError: class ApiClientError extends Error {},
}))

describe('CourseEditorPage', () => {
  it('shows confidential material warning and validates empty title', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <CourseEditorPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('MVP 検証では本物の機密社内資料を入力しないでください。')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: '保存する' }))

    expect(screen.getByText('タイトルが必要です。')).toBeTruthy()
  })
})
