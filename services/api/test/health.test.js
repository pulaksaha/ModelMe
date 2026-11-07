import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { test } from 'node:test'
import { createApp } from '../src/app.js'
import { readiness } from '../src/routes/health.js'

async function withServer(callback) {
  const server = createServer(createApp())
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  try {
    await callback(`http://127.0.0.1:${address.port}`)
  } finally {
    await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
  }
}

test('liveness endpoint responds without a database connection', async () => {
  await withServer(async baseUrl => {
    const response = await fetch(`${baseUrl}/api/health/live`)
    assert.equal(response.status, 200)
    assert.deepEqual(await response.json(), { status: 'ok', service: 'modelme-api' })
  })
})

test('unknown API routes return JSON 404 responses', async () => {
  await withServer(async baseUrl => {
    const response = await fetch(`${baseUrl}/api/not-a-route`)
    assert.equal(response.status, 404)
    assert.deepEqual(await response.json(), { detail: 'API route not found' })
  })
})

test('readiness is healthy when MongoDB is connected', () => {
  const result = readiness(true)
  assert.equal(result.httpStatus, 200)
  assert.equal(result.body.status, 'ready')
  assert.equal(result.body.dependencies.mongodb, 'connected')
})

test('readiness is degraded when MongoDB is disconnected', () => {
  const result = readiness(false)
  assert.equal(result.httpStatus, 503)
  assert.equal(result.body.status, 'degraded')
  assert.equal(result.body.dependencies.mongodb, 'disconnected')
})
