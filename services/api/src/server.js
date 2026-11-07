import { createServer } from 'node:http'
import { config } from './config.js'
import { createApp } from './app.js'
import { connectMongo, disconnectMongo } from './db/mongo.js'

const server = createServer(createApp())

server.listen(config.port, '0.0.0.0', () => {
  console.info(`ModelMe API listening on port ${config.port}`)
})

async function connectWithRetry() {
  try {
    await connectMongo(config.mongoUri)
    console.info('MongoDB connected')
  } catch (error) {
    console.error(`MongoDB unavailable (${error.name}); retrying in 5 seconds`)
    const timer = setTimeout(connectWithRetry, 5000)
    timer.unref()
  }
}

void connectWithRetry()

async function shutdown(signal) {
  console.info(`${signal}: closing ModelMe API`)
  server.close(async () => {
    await disconnectMongo()
    process.exit(0)
  })
  const forcedExit = setTimeout(() => process.exit(1), 10000)
  forcedExit.unref()
}

process.once('SIGINT', () => void shutdown('SIGINT'))
process.once('SIGTERM', () => void shutdown('SIGTERM'))
