import { SignJWT, jwtVerify } from 'jose'
import { config } from '../config.js'

const SESSION_ISSUER = 'modelme-api'
const SESSION_AUDIENCE = 'modelme-web'

function key(secret) {
  if (secret.length < 32 || secret.startsWith('replace-')) {
    const error = new Error('JWT_SECRET must be configured with at least 32 characters')
    error.status = 503
    throw error
  }
  return new TextEncoder().encode(secret)
}

export async function createSessionToken(user, secret = config.jwtSecret) {
  return new SignJWT({ ver: user.sessionVersion })
    .setProtectedHeader({ alg: 'HS256', typ: 'JWT' })
    .setSubject(user.id || user._id.toString())
    .setIssuer(SESSION_ISSUER)
    .setAudience(SESSION_AUDIENCE)
    .setIssuedAt()
    .setExpirationTime(`${config.sessionTtlSeconds}s`)
    .sign(key(secret))
}

export async function verifySessionToken(token, secret = config.jwtSecret) {
  const { payload } = await jwtVerify(token, key(secret), {
    issuer: SESSION_ISSUER,
    audience: SESSION_AUDIENCE,
    algorithms: ['HS256'],
  })
  if (typeof payload.sub !== 'string' || !Number.isInteger(payload.ver)) {
    throw new Error('Invalid session token')
  }
  return { userId: payload.sub, sessionVersion: payload.ver }
}

export function sessionCookieOptions() {
  return {
    httpOnly: true,
    secure: config.nodeEnv === 'production',
    sameSite: 'strict',
    path: '/api',
    maxAge: config.sessionTtlSeconds * 1000,
  }
}
