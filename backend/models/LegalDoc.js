import mongoose from 'mongoose';

const LegalDocSchema = new mongoose.Schema({
  type: { type: String, enum: ['privacy', 'terms'], required: true, unique: true },
  content: { type: String, required: true },
  lastUpdated: { type: Date, default: Date.now },
  version: { type: String } // optional, like '2025-07-25'
});

export default mongoose.model('LegalDoc', LegalDocSchema);
