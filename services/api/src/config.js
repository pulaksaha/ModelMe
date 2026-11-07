const parsedPort = Number(process.env.API_PORT || 3001)

if (!Number.isInteger(parsedPort) || parsedPort < 1 || parsedPort > 65535) {
  throw new Error('API_PORT must be an integer between 1 and 65535')
}

export const config = Object.freeze({
  port: parsedPort,
  mongoUri: process.env.MONGODB_URI || 'mongodb://127.0.0.1:27017/modelme',
  processingServiceUrl: process.env.PROCESSING_SERVICE_URL || 'http://127.0.0.1:8000',
  frontendDist: process.env.FRONTEND_DIST || '../../../frontend/dist',
})
