import { useMemo } from 'react'
import {
  createBrowserRouter,
  Navigate,
  Outlet,
  RouterProvider,
  type RouteObject,
} from 'react-router-dom'

import { AuthGate, AuthProvider, type AuthProviderProps } from '../auth/AuthProvider'
import { CourseEditorPage } from '../pages/CourseEditorPage'
import { CourseHistoryPage } from '../pages/CourseHistoryPage'
import { CourseListPage } from '../pages/CourseListPage'
import { DrillAdminPage } from '../pages/DrillAdminPage'
import { LearnerDrillPage } from '../pages/LearnerDrillPage'
import { PatchReviewPage } from '../pages/PatchReviewPage'

type OwnerAuthOptions = Omit<AuthProviderProps, 'children'>

type AppRoutesOptions = {
  ownerAuth?: OwnerAuthOptions
}

type AppRouterProps = {
  ownerAuth?: OwnerAuthOptions
}

function createAppRoutes(options: AppRoutesOptions = {}): RouteObject[] {
  return [
    {
      path: '/',
      element: <Navigate to="/courses" replace />,
    },
    {
      element: <OwnerRouteGuard ownerAuth={options.ownerAuth} />,
      children: [
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
          path: '/courses/:courseId/drill-runs/:drillRunId/analysis',
          element: <PatchReviewPage />,
        },
        {
          path: '/patches/:patchId',
          element: <PatchReviewPage />,
        },
      ],
    },
    {
      path: '/drills/:shareToken',
      element: <LearnerDrillPage />,
    },
  ]
}

export function AppRouter({ ownerAuth }: AppRouterProps = {}) {
  const router = useMemo(() => createBrowserRouter(createAppRoutes({ ownerAuth })), [ownerAuth])
  return <RouterProvider router={router} />
}

function OwnerRouteGuard({ ownerAuth }: { ownerAuth?: OwnerAuthOptions }) {
  const authProps = ownerAuth ?? {}
  return (
    <AuthProvider {...authProps}>
      <AuthGate>
        <Outlet />
      </AuthGate>
    </AuthProvider>
  )
}
