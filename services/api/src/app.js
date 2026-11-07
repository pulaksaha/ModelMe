import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import express from 'express'
import helmet from 'helmet'
import { createProxyMiddleware } from 'http-proxy-middleware'
import { config } from './config.js'
import healthRouter from './routes/health.js'

const currentDir = dirname(fileURLToPath(import.meta.url))

export function createApp() {
  const app = express()
  app.disable('x-powered-by')
  app.use(helmet())

  app.use('/api/health', healthRouter)

  // Transitional bridge: preserve current FastAPI reconstruction routes while
  // Express becomes the API entry point. Phase 6 replaces this with job records.
  app.use('/api/reconstruction', createProxyMiddleware({
    target: config.processingServiceUrl,
    changeOrigin: true,
    pathRewrite: path => `/api/reconstruction${path}`,
    on: {
      error: (_error, _req, res) => {
        if (!res.headersSent) {
          res.writeHead(503, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ detail: 'Reconstruction service is unavailable' }))
        }
      },
    },
  }))

  app.use(express.json({ limit: '256kb' }))
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
