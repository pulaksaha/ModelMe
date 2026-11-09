import { Router } from 'express'
import argon2 from 'argon2'
import { z } from 'zod'
import { User } from '../models/User.js'
import { requireSession } from '../middleware/requireSession.js'
import { createSessionToken, sessionCookieOptions } from '../services/session.js'

const router = Router()
const registerSchema = z.object({
  displayName: z.string().trim().min(1).max(80),
  email: z.string().trim().email().max(254),
  password: z.string().min(12).max(128),
}).strict()
const loginSchema = z.object({
  email: z.string().trim().email().max(254),
  password: z.string().min(1).max(128),
}).strict()

function validationError(error) {
  return { detail: 'Invalid request', issues: error.issues.map(issue => ({ field: issue.path.join('.'), message: issue.message })) }
}

function publicUser(user) {
  return { id: user.id, displayName: user.displayName, email: user.email }
}

async function startSession(user, res) {
  const token = await createSessionToken(user)
  res.cookie('modelme_session', token, sessionCookieOptions())
}

router.post('/register', async (req, res, next) => {
  const parsed = registerSchema.safeParse(req.body)
  if (!parsed.success) return res.status(400).json(validationError(parsed.error))

  try {
    const email = parsed.data.email.toLowerCase()
    const passwordHash = await argon2.hash(parsed.data.password, { type: argon2.argon2id })
    const user = await User.create({ displayName: parsed.data.displayName, email, passwordHash })
    await startSession(user, res)
    return res.status(201).json({ user: publicUser(user) })
  } catch (error) {
    if (error.code === 11000) return res.status(409).json({ detail: 'An account with this email already exists' })
    return next(error)
  }
})

router.post('/login', async (req, res, next) => {
  const parsed = loginSchema.safeParse(req.body)
  if (!parsed.success) return res.status(400).json(validationError(parsed.error))

  try {
    const user = await User.findOne({ email: parsed.data.email.toLowerCase() }).select('+passwordHash')
    const valid = user && await argon2.verify(user.passwordHash, parsed.data.password)
    if (!valid) return res.status(401).json({ detail: 'Email or password is incorrect' })
    await startSession(user, res)
    return res.json({ user: publicUser(user) })
  } catch (error) {
    return next(error)
  }
})

router.post('/logout', requireSession, async (req, res, next) => {
  try {
    await User.updateOne({ _id: req.auth.userId }, { $inc: { sessionVersion: 1 } })
    res.clearCookie('modelme_session', sessionCookieOptions())
    return res.status(204).end()
  } catch (error) {
    return next(error)
  }
})

router.get('/me', requireSession, (req, res) => {
  res.json({ user: { id: req.auth.userId, displayName: req.auth.displayName, email: req.auth.email } })
})

export default router
