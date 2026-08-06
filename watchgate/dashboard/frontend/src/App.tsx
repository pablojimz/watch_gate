import { useEffect, useState, type ReactElement } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/AppLayout'
import { api, type MeResponse } from '@/api/client'
import LoginPage from '@/pages/LoginPage'
import ReposPage from '@/pages/ReposPage'
import RepoPage from '@/pages/RepoPage'
import FeedbackPage from '@/pages/FeedbackPage'
import AdminPage from '@/pages/AdminPage'
import MetricsPage from '@/pages/MetricsPage'
import { Skeleton } from '@/components/ui/skeleton'

function RequireAuth({
  children,
  me,
}: {
  children: (me: MeResponse) => ReactElement
  me: MeResponse | null | undefined
}) {
  if (me === undefined) {
    return (
      <div className="flex h-screen items-center justify-center p-6">
        <Skeleton className="h-10 w-48" />
      </div>
    )
  }
  if (me === null) return <Navigate to="/login" replace />
  return children(me)
}

export default function App() {
  const [me, setMe] = useState<MeResponse | null | undefined>(undefined)

  useEffect(() => {
    void api
      .me()
      .then(setMe)
      .catch(() => setMe(null))
  }, [])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <RequireAuth me={me}>
              {(user) => <AppLayout isAdmin={user.is_admin} />}
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/repos" replace />} />
          <Route path="repos" element={<ReposPage />} />
          <Route path="repos/:owner/:name" element={<RepoPage />} />
          <Route path="repos/:owner/:name/feedback" element={<FeedbackPage />} />
          <Route path="metrics" element={<MetricsPage />} />
          <Route
            path="admin"
            element={
              me?.is_admin ? <AdminPage /> : <Navigate to="/repos" replace />
            }
          />
        </Route>
        <Route path="*" element={<Navigate to="/repos" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
