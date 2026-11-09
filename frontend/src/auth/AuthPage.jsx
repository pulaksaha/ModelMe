import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { Activity, ArrowRight, CircleAlert } from 'lucide-react'
import { useAuth } from './AuthContext.jsx'

export default function AuthPage({ mode }) {
  const registering = mode === 'register'
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ displayName: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (registering) await register(form)
      else await login({ email: form.email, password: form.password })
      navigate(location.state?.from || '/', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return <main className="auth-shell">
    <a className="brand auth-brand" href="/"><span className="brand-mark"><i /><i /><i /></span><span>form<span className="brand-dot">.</span></span></a>
    <section className="auth-card">
      <div className="eyebrow"><span>MODELME</span> PERSONAL BODY MODELING</div>
      <h1>{registering ? 'Create your account.' : 'Welcome back.'}</h1>
      <p>{registering ? 'Set up a private workspace for your measurements and 3D models.' : 'Sign in to continue to your measurement workspace.'}</p>
      <form onSubmit={submit}>
        {registering && <label>Your name<input autoComplete="name" required maxLength={80} value={form.displayName} onChange={event => setForm({ ...form, displayName: event.target.value })} /></label>}
        <label>Email address<input type="email" autoComplete="email" required maxLength={254} value={form.email} onChange={event => setForm({ ...form, email: event.target.value })} /></label>
        <label>Password<input type="password" autoComplete={registering ? 'new-password' : 'current-password'} required minLength={registering ? 12 : 1} maxLength={128} value={form.password} onChange={event => setForm({ ...form, password: event.target.value })} />{registering && <small>Use at least 12 characters.</small>}</label>
        {error && <div className="error-note"><CircleAlert size={15} /> <span>{error}</span></div>}
        <button className="primary-button" disabled={busy}>{busy ? 'Working…' : registering ? 'Create account' : 'Sign in'} <ArrowRight size={16} /></button>
      </form>
      <div className="auth-switch">{registering ? 'Already registered?' : 'New to ModelMe?'} <Link to={registering ? '/login' : '/register'}>{registering ? 'Sign in' : 'Create an account'}</Link></div>
      <div className="privacy-note"><Activity size={14} /> Your account session is stored in an HttpOnly cookie.</div>
    </section>
    <footer><span>MODELME <span className="brand-dot">●</span> PRIVATE WORKSPACE</span></footer>
  </main>
}
