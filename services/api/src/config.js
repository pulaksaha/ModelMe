const parsedPort = Number(process.env.API_PORT || 3001)

if (!Number.isInteger(parsedPort) || parsedPort < 1 || parsedPort > 65535) {
  throw new Error('API_PORT must be an integer between 1 and 65535')
}

export const config = Object.freeze({
  port: parsedPort,
  mongoUri: process.env.MONGODB_URI || 'mongodb://127.0.0.1:27017/modelme',
  processingServiceUrl: process.env.PROCESSING_SERVICE_URL || 'http://127.0.0.1:8000',
  processingHealthUrl: process.env.PROCESSING_HEALTH_URL || `${process.env.PROCESSING_SERVICE_URL || 'http://127.0.0.1:8000'}/api/health`,
  frontendDist: process.env.FRONTEND_DIST || '../../../frontend/dist',
  jwtSecret: process.env.JWT_SECRET || '',
  sessionTtlSeconds: Number(process.env.SESSION_TTL_SECONDS || 1800),
  nodeEnv: process.env.NODE_ENV || 'development',
})

if (!Number.isInteger(config.sessionTtlSeconds) || config.sessionTtlSeconds < 300 || config.sessionTtlSeconds > 86400) {
  throw new Error('SESSION_TTL_SECONDS must be an integer between 300 and 86400')
}

if (config.nodeEnv === 'production' && config.jwtSecret.length < 32) {
  throw new Error('JWT_SECRET must contain at least 32 characters in production')
}
