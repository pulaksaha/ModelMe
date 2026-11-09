import { useNavigate } from 'react-router'
import { ArrowUpRight, LogOut, Ruler, UserRound } from 'lucide-react'
import Generator from '../Generator.jsx'
import { useAuth } from './AuthContext.jsx'

export default function Dashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function signOut() {
    try { await logout() } finally { navigate('/login', { replace: true }) }
  }

  return <div className="dashboard-shell">
    <header className="dashboard-bar">
      <a className="brand" href="/"><span className="brand-mark"><i /><i /><i /></span><span>form<span className="brand-dot">.</span></span></a>
      <div className="dashboard-user"><span className="dashboard-user-name"><UserRound size={15} /> {user?.displayName}</span><button className="signout-button" onClick={signOut}><LogOut size={15} /> Sign out</button></div>
    </header>
    <section className="dashboard-overview">
      <div><div className="eyebrow"><span>YOUR WORKSPACE</span> BODY MODELING</div><h1>Good to see you,<br /><em>{user?.displayName}.</em></h1><p>Build and revisit body models from your measurements.</p></div>
      <a className="dashboard-action" href="#generator"><Ruler size={17} /> Start a model <ArrowUpRight size={15} /></a>
    </section>
    <section className="dashboard-cards">
      <article><span className="eyebrow">BODY PROFILES</span><strong>Ready for your first profile</strong><small>Measurement profiles arrive in Phase 3.</small></article>
      <article><span className="eyebrow">MODEL HISTORY</span><strong>Generation workspace</strong><small>Completed models can be reviewed here after persistence is added.</small></article>
    </section>
    <div id="generator"><Generator /></div>
  </div>
}
