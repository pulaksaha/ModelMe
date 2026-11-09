import { Router } from 'express'
import { isMongoReady } from '../db/mongo.js'
import { config } from '../config.js'

export function readiness(mongoReady, processingReady) {
  const ready = mongoReady && processingReady
  return {
    httpStatus: ready ? 200 : 503,
    body: {
      status: ready ? 'ready' : 'degraded',
      service: 'modelme-api',
      dependencies: {
        mongodb: mongoReady ? 'connected' : 'disconnected',
        reconstruction: processingReady ? 'available' : 'unavailable',
      },
    },
  }
}

export async function isProcessingReady() {
  try {
    const response = await fetch(config.processingHealthUrl, { signal: AbortSignal.timeout(2000) })
    if (!response.ok) return false
    const health = await response.json()
    return health.status === 'ok'
  } catch {
    return false
  }
}

const router = Router()

router.get('/live', (_req, res) => {
  res.json({ status: 'ok', service: 'modelme-api' })
})

router.get('/ready', async (_req, res) => {
  const [mongoReady, processingReady] = await Promise.all([isMongoReady(), isProcessingReady()])
  const result = readiness(mongoReady, processingReady)
  res.status(result.httpStatus).json(result.body)
})

router.get('/', async (_req, res) => {
  const [mongoReady, processingReady] = await Promise.all([isMongoReady(), isProcessingReady()])
  const result = readiness(mongoReady, processingReady)
  res.status(result.httpStatus).json(result.body)
})

export default router
