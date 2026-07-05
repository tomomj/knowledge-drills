import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'

import { CourseEditorPage } from '../pages/CourseEditorPage'
import { CourseHistoryPage } from '../pages/CourseHistoryPage'
import { CourseListPage } from '../pages/CourseListPage'
import { DrillAdminPage } from '../pages/DrillAdminPage'
import { LearnerDrillPage } from '../pages/LearnerDrillPage'
import { PatchReviewPage } from '../pages/PatchReviewPage'

const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/courses" replace />,
  },
  {
    path: '/courses',
    element: <CourseListPage />,
  },
  {
    path: '/courses/new',
    element: <CourseEditorPage />,
  },
  {
    path: '/courses/:courseId',
    element: <CourseEditorPage />,
  },
  {
    path: '/courses/:courseId/history',
    element: <CourseHistoryPage />,
  },
  {
    path: '/courses/:courseId/drill-runs/:drillRunId',
    element: <DrillAdminPage />,
  },
  {
    path: '/drills/:shareToken',
    element: <LearnerDrillPage />,
  },
  {
    path: '/courses/:courseId/drill-runs/:drillRunId/analysis',
    element: <PatchReviewPage />,
  },
  {
    path: '/patches/:patchId',
    element: <PatchReviewPage />,
  },
])

export function AppRouter() {
  return <RouterProvider router={router} />
}
