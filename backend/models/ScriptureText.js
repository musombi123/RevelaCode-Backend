// models/ScriptureText.js
import mongoose from 'mongoose';

const ScriptureTextSchema = new mongoose.Schema({
  religion: {
    type: String,
    enum: ['Christianity', 'Islam', 'Hinduism', 'Other'],
    required: true
  },
  book: { type: String, required: true }, // e.g., 'Genesis', 'Al-Baqarah', 'Bhagavad Gita'
  chapter: { type: Number, required: true },
  verse: { type: Number, required: true },
  text: { type: String },  // optional if using external API
  language: { type: String, default: 'en' },
  version: { type: String }, // e.g., 'KJV', 'NIV', 'Sahih', 'Hindi', etc.
  sourceType: {
    type: String,
    enum: ['local', 'api'],
    default: 'local'
  },
  sourceUrl: { type: String }, // API endpoint if sourceType === 'api'
  meta: {
    translator: String,
    copyright: String,
    notes: String
  }
});

export default mongoose.model('ScriptureText', ScriptureTextSchema);
