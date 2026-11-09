import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router'
import AuthPage from './auth/AuthPage.jsx'
import Dashboard from './auth/Dashboard.jsx'
import { useAuth } from './auth/AuthContext.jsx'

function ProtectedRoute() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <main className="auth-shell"><div className="auth-loading">Loading your workspace…</div></main>
  return user ? <Outlet /> : <Navigate to="/login" replace state={{ from: location.pathname }} />
}

function PublicRoute() {
  const { user, loading } = useAuth()
  if (loading) return <main className="auth-shell"><div className="auth-loading">Loading your workspace…</div></main>
  return user ? <Navigate to="/" replace /> : <Outlet />
}

export default function App() {
  return <Routes>
    <Route element={<ProtectedRoute />}><Route path="/" element={<Dashboard />} /></Route>
    <Route element={<PublicRoute />}>
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
}
