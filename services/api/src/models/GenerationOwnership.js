import mongoose from 'mongoose'

const generationOwnershipSchema = new mongoose.Schema({
  jobId: { type: String, required: true, unique: true, index: true },
  ownerId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true, index: true },
  source: { type: String, default: 'legacy-reconstruction-service' },
}, { timestamps: true })

export const GenerationOwnership = mongoose.models.GenerationOwnership
  || mongoose.model('GenerationOwnership', generationOwnershipSchema)
