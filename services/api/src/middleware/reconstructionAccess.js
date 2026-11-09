import { GenerationOwnership } from '../models/GenerationOwnership.js'
import { isMongoReady } from '../db/mongo.js'

const knownJobRoute = /^\/(?:generate|status|result|download|report)(?:\/|$)/

export async function authorizeReconstruction(req, res, next) {
  if (req.method === 'POST' && req.path === '/upload') {
    if (!isMongoReady()) return res.status(503).json({ detail: 'Database is unavailable' })
    return next()
  }

  if (!knownJobRoute.test(req.path)) return res.status(404).json({ detail: 'Reconstruction route not found' })

  const jobId = req.method === 'POST' && req.path === '/generate'
    ? req.body?.job_id
    : req.path.split('/').filter(Boolean).at(-1)
  if (typeof jobId !== 'string' || !jobId) return res.status(400).json({ detail: 'job_id is required' })

  try {
    const ownership = await GenerationOwnership.findOne({ jobId, ownerId: req.auth.userId }).lean()
    if (!ownership) return res.status(404).json({ detail: 'Job not found' })
    return next()
  } catch (error) {
    return next(error)
  }
}
