import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import express from 'express'
import helmet from 'helmet'
import cookieParser from 'cookie-parser'
import { createProxyMiddleware, fixRequestBody, responseInterceptor } from 'http-proxy-middleware'
import { config } from './config.js'
import { GenerationOwnership } from './models/GenerationOwnership.js'
import { requireSession } from './middleware/requireSession.js'
import { authorizeReconstruction } from './middleware/reconstructionAccess.js'
import authRouter from './routes/auth.js'
import healthRouter from './routes/health.js'

const currentDir = dirname(fileURLToPath(import.meta.url))

export function createApp({ processingServiceUrl = config.processingServiceUrl } = {}) {
  const app = express()
  app.disable('x-powered-by')
  app.use(helmet())
  app.use(cookieParser())
  app.use(express.json({ limit: '256kb' }))

  app.use('/api/health', healthRouter)
  app.use('/api/auth', authRouter)

  // The legacy processor retains geometry work; Express adds the account and
  // ownership boundary until Phase 6 replaces this proxy with durable jobs.
  app.use('/api/reconstruction', requireSession, authorizeReconstruction, createProxyMiddleware({
    target: processingServiceUrl,
    changeOrigin: true,
    pathRewrite: path => `/api/reconstruction${path}`,
    selfHandleResponse: true,
    on: {
      proxyReq: fixRequestBody,
      proxyRes: responseInterceptor(async (body, proxyRes, req, res) => {
        const originalPath = (req.originalUrl || req.url || '').split('?')[0]
        if (req.method !== 'POST' || originalPath !== '/api/reconstruction/upload' || proxyRes.statusCode < 200 || proxyRes.statusCode >= 300) return body
        try {
          const uploaded = JSON.parse(body.toString('utf8'))
          if (typeof uploaded.job_id !== 'string' || !uploaded.job_id) throw new Error('Upload response did not include job_id')
          await GenerationOwnership.create({ jobId: uploaded.job_id, ownerId: req.auth.userId })
          return body
        } catch (error) {
          console.error('Could not persist reconstruction ownership:', error.message)
          res.statusCode = 503
          res.setHeader('Content-Type', 'application/json; charset=utf-8')
          res.removeHeader('Content-Length')
          return Buffer.from(JSON.stringify({ detail: 'Could not save model ownership metadata' }))
        }
      }),
      error: (_error, _req, res) => {
        if (!res.headersSent) {
          res.writeHead(503, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ detail: 'Reconstruction service is unavailable' }))
        }
      },
    },
  }))

  app.use('/api', (_req, res) => res.status(404).json({ detail: 'API route not found' }))

  const frontendDist = resolve(currentDir, config.frontendDist)
  if (existsSync(frontendDist)) {
    app.use(express.static(frontendDist, { index: false, maxAge: '1h' }))
    app.get(/^(?!\/api(?:\/|$)).*/, (_req, res, next) => {
      res.sendFile(resolve(frontendDist, 'index.html'), error => error && next(error))
    })
  }

  app.use((error, _req, res, _next) => {
    console.error('Unhandled API error:', error.message)
    res.status(error.status || 500).json({ detail: 'Internal server error' })
  })

  return app
}
