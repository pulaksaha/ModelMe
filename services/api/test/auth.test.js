import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { randomBytes, randomUUID } from 'node:crypto'
import { test } from 'node:test'
import argon2 from 'argon2'
import mongoose from 'mongoose'
import { SignJWT } from 'jose'
import { connectMongo, disconnectMongo } from '../src/db/mongo.js'
import { GenerationOwnership } from '../src/models/GenerationOwnership.js'
import { User } from '../src/models/User.js'
import { createSessionToken, sessionCookieOptions, verifySessionToken } from '../src/services/session.js'
import { config } from '../src/config.js'
import { createApp } from '../src/app.js'

const signingSecret = randomBytes(48).toString('base64')

test('passwords are Argon2id hashed and verify against the original password', async () => {
  const hash = await argon2.hash('long-and-private-passphrase', { type: argon2.argon2id })
  assert.match(hash, /^\$argon2id\$/)
  assert.equal(await argon2.verify(hash, 'long-and-private-passphrase'), true)
  assert.equal(await argon2.verify(hash, 'wrong-passphrase'), false)
})

test('JWT sessions expire, bind their audience, and reject tampering', async () => {
  const token = await createSessionToken({ id: '507f1f77bcf86cd799439011', sessionVersion: 3 }, signingSecret)
  assert.deepEqual(await verifySessionToken(token, signingSecret), { userId: '507f1f77bcf86cd799439011', sessionVersion: 3 })
  await assert.rejects(verifySessionToken(`${token.slice(0, -1)}x`, signingSecret))
  await assert.rejects(verifySessionToken(token, randomBytes(48).toString('base64')))
  const key = new TextEncoder().encode(signingSecret)
  const expired = await new SignJWT({ ver: 0 }).setProtectedHeader({ alg: 'HS256' })
    .setSubject('507f1f77bcf86cd799439011').setIssuer('modelme-api').setAudience('modelme-web')
    .setIssuedAt(Math.floor(Date.now() / 1000) - 120).setExpirationTime(Math.floor(Date.now() / 1000) - 60).sign(key)
  await assert.rejects(verifySessionToken(expired, signingSecret), /exp/i)
})

test('session cookie is HttpOnly, same-site strict, and scoped to the API', () => {
  const options = sessionCookieOptions()
  assert.equal(options.httpOnly, true)
  assert.equal(options.sameSite, 'strict')
  assert.equal(options.path, '/api')
  assert.equal(options.maxAge, config.sessionTtlSeconds * 1000)
})

async function openTestServer(appOptions) {
  const server = createServer(createApp(appOptions))
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  return { server, baseUrl: `http://127.0.0.1:${server.address().port}` }
}

test('registration, login, protected identity, logout, and password storage work with MongoDB', async t => {
  try {
    await connectMongo(process.env.TEST_MONGODB_URI || 'mongodb://127.0.0.1:27017/modelme_test')
  } catch (error) {
    t.skip(`MongoDB integration check unavailable: ${error.message}`)
    return
  }

  const email = `phase2-${randomUUID()}@example.test`
  const { server, baseUrl } = await openTestServer()
  let userId
  const privateJobId = `owned-by-another-${randomUUID()}`
  try {
    const shortPassword = await fetch(`${baseUrl}/api/auth/register`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ displayName: 'Audit User', email, password: 'short' }),
    })
    assert.equal(shortPassword.status, 400)

    const registered = await fetch(`${baseUrl}/api/auth/register`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ displayName: 'Audit User', email, password: 'long-and-private-passphrase' }),
    })
    assert.equal(registered.status, 201)
    const registeredBody = await registered.json()
    userId = registeredBody.user.id
    const cookie = registered.headers.get('set-cookie')?.split(';')[0]
    assert.ok(cookie?.startsWith('modelme_session='))
    assert.match(registered.headers.get('set-cookie'), /HttpOnly/i)

    const stored = await User.findById(userId).select('+passwordHash')
    assert.ok(stored.passwordHash.startsWith('$argon2id$'))
    assert.equal(stored.passwordHash.includes('long-and-private-passphrase'), false)

    const identity = await fetch(`${baseUrl}/api/auth/me`, { headers: { Cookie: cookie } })
    assert.equal(identity.status, 200)
    assert.equal((await identity.json()).user.email, email)

    const anonymous = await fetch(`${baseUrl}/api/reconstruction/status/private-job`)
    assert.equal(anonymous.status, 401)
    const unowned = await fetch(`${baseUrl}/api/reconstruction/status/private-job`, { headers: { Cookie: cookie } })
    assert.equal(unowned.status, 404)
    await GenerationOwnership.create({ jobId: privateJobId, ownerId: new mongoose.Types.ObjectId() })
    const anotherUsersJob = await fetch(`${baseUrl}/api/reconstruction/status/${privateJobId}`, { headers: { Cookie: cookie } })
    assert.equal(anotherUsersJob.status, 404)

    const duplicate = await fetch(`${baseUrl}/api/auth/register`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ displayName: 'Audit User', email, password: 'long-and-private-passphrase' }),
    })
    assert.equal(duplicate.status, 409)

    const badLogin = await fetch(`${baseUrl}/api/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password: 'not-the-password' }),
    })
    assert.equal(badLogin.status, 401)

    const logout = await fetch(`${baseUrl}/api/auth/logout`, { method: 'POST', headers: { Cookie: cookie } })
    assert.equal(logout.status, 204)
    const revokedIdentity = await fetch(`${baseUrl}/api/auth/me`, { headers: { Cookie: cookie } })
    assert.equal(revokedIdentity.status, 401)
  } finally {
    await new Promise(resolve => server.close(resolve))
    await GenerationOwnership.deleteOne({ jobId: privateJobId })
    if (userId) await User.deleteOne({ _id: userId })
    await disconnectMongo()
  }
})

test('Express persists the owner returned by upload before allowing job polling', async t => {
  try {
    await connectMongo(process.env.TEST_MONGODB_URI || 'mongodb://127.0.0.1:27017/modelme_test')
  } catch (error) {
    t.skip(`MongoDB integration check unavailable: ${error.message}`)
    return
  }

  const email = `proxy-${randomUUID()}@example.test`
  const jobId = `proxy-job-${randomUUID()}`
  const seen = []
  const upstream = createServer((req, res) => {
    seen.push({ method: req.method, url: req.url })
    res.setHeader('Content-Type', 'application/json')
    if (req.method === 'POST' && req.url === '/api/reconstruction/upload') {
      res.end(JSON.stringify({ job_id: jobId, validation_status: 'warn' }))
    } else if (req.method === 'GET' && req.url === `/api/reconstruction/status/${jobId}`) {
      res.end(JSON.stringify({ job_id: jobId, status: 'queued', progress: 0 }))
    } else {
      res.statusCode = 404
      res.end(JSON.stringify({ detail: 'Unexpected mock upstream route' }))
    }
  })
  await new Promise((resolve, reject) => {
    upstream.once('error', reject)
    upstream.listen(0, '127.0.0.1', resolve)
  })

  const user = await User.create({ displayName: 'Proxy Test', email, passwordHash: 'test-only-hash' })
  const token = await createSessionToken(user)
  const { server, baseUrl } = await openTestServer({ processingServiceUrl: `http://127.0.0.1:${upstream.address().port}` })
  const cookie = `modelme_session=${token}`
  try {
    const form = new FormData()
    form.append('file', new Blob(['{}'], { type: 'application/json' }), 'synthetic.json')
    const upload = await fetch(`${baseUrl}/api/reconstruction/upload`, { method: 'POST', headers: { Cookie: cookie }, body: form })
    const uploadBody = await upload.json()
    assert.equal(upload.status, 200, JSON.stringify(uploadBody))
    assert.equal(uploadBody.job_id, jobId)

    const ownership = await GenerationOwnership.findOne({ jobId, ownerId: user.id }).lean()
    assert.ok(ownership, 'upload response ownership must be persisted before success returns')

    const status = await fetch(`${baseUrl}/api/reconstruction/status/${jobId}`, { headers: { Cookie: cookie } })
    const statusBody = await status.json()
    assert.equal(status.status, 200, JSON.stringify(statusBody))
    assert.deepEqual(statusBody, { job_id: jobId, status: 'queued', progress: 0 })
    assert.deepEqual(seen, [
      { method: 'POST', url: '/api/reconstruction/upload' },
      { method: 'GET', url: `/api/reconstruction/status/${jobId}` },
    ])
  } finally {
    await new Promise(resolve => server.close(resolve))
    await new Promise(resolve => upstream.close(resolve))
    await GenerationOwnership.deleteOne({ jobId })
    await User.deleteOne({ _id: user._id })
    await disconnectMongo()
  }
})
