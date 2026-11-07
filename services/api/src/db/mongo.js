import mongoose from 'mongoose'

let connectionAttempt

export function isMongoReady() {
  return mongoose.connection.readyState === 1
}

export async function connectMongo(uri = process.env.MONGODB_URI || 'mongodb://127.0.0.1:27017/modelme') {
  if (isMongoReady()) return mongoose.connection
  if (connectionAttempt) return connectionAttempt

  connectionAttempt = mongoose.connect(uri, { serverSelectionTimeoutMS: 3000 })
    .then(() => mongoose.connection)
    .finally(() => { connectionAttempt = undefined })
  return connectionAttempt
}

export async function disconnectMongo() {
  if (mongoose.connection.readyState !== 0) await mongoose.disconnect()
}
