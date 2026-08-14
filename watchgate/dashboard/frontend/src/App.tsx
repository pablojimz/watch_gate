import { useEffect, useState, type ReactElement } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/AppLayout'
import { api, type MeResponse } from '@/api/client'
import LoginPage from '@/pages/LoginPage'
import ReposPage from '@/pages/ReposPage'
import ExternalReposPage from '@/pages/ExternalReposPage'
import RepoPage from '@/pages/RepoPage'
import FeedbackPage from '@/pages/FeedbackPage'
import AdminPage from '@/pages/AdminPage'
import MetricsPage from '@/pages/MetricsPage'
import ApiKeysPage from '@/pages/ApiKeysPage'
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
          <Route path="audits" element={<ExternalReposPage />} />
          {/* Un solo segmento (:repo), codificado con encodeURIComponent al
              construir el link -- no ":owner/:name" en dos segmentos. El
              nombre de un repo es un string libre en metadata.repo/repo_path
              (ver watchgate/api/routers/analyze.py): no siempre tiene el
              formato "owner/name" (p. ej. "prueba_watchgate", sin barra),
              y partirlo en dos segmentos de URL rompía el matcheo de rutas
              para cualquier repo con 0 o 2+ barras, cayendo al catch-all de
              abajo y devolviendo silenciosamente a /repos sin avisar. */}
          <Route path="repos/:repo" element={<RepoPage />} />
          <Route path="repos/:repo/feedback" element={<FeedbackPage />} />
          <Route path="metrics" element={<MetricsPage />} />
          <Route path="api-keys" element={<ApiKeysPage />} />
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
