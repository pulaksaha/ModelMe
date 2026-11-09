import { User } from '../models/User.js'
import { verifySessionToken } from '../services/session.js'

export async function requireSession(req, res, next) {
  const token = req.cookies?.modelme_session
  if (!token) return res.status(401).json({ detail: 'Authentication required' })

  try {
    const session = await verifySessionToken(token)
    const user = await User.findById(session.userId).select('displayName email sessionVersion')
    if (!user || user.sessionVersion !== session.sessionVersion) {
      return res.status(401).json({ detail: 'Session is invalid or expired' })
    }
    req.auth = { userId: user.id, email: user.email, displayName: user.displayName }
    return next()
  } catch {
    return res.status(401).json({ detail: 'Session is invalid or expired' })
  }
}
