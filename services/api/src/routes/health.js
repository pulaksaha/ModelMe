import { Router } from 'express'
import { isMongoReady } from '../db/mongo.js'

export function readiness(mongoReady) {
  return {
    httpStatus: mongoReady ? 200 : 503,
    body: {
      status: mongoReady ? 'ready' : 'degraded',
      service: 'modelme-api',
      dependencies: { mongodb: mongoReady ? 'connected' : 'disconnected' },
    },
  }
}

const router = Router()

router.get('/live', (_req, res) => {
  res.json({ status: 'ok', service: 'modelme-api' })
})

router.get('/ready', (_req, res) => {
  const result = readiness(isMongoReady())
  res.status(result.httpStatus).json(result.body)
})

router.get('/', (_req, res) => {
  const result = readiness(isMongoReady())
  res.status(result.httpStatus).json(result.body)
})

export default router
