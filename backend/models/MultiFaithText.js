// backend/models/MultiFaithText.js
import mongoose from 'mongoose';

const multiFaithTextSchema = new mongoose.Schema({
  type: {
    type: String,
    enum: ['bible', 'quran', 'torah', 'gita'],
    required: true,
  },
  version: {
    type: String, // e.g., "KJV", "NIV", "NKJV", "Sahih", etc.
    required: true,
  },
  language: {
    type: String, // e.g., "en", "ar", "he", "hi"
    default: "en",
  },
  content: {
    type: String,
    required: true,
  },
  licensed: {
    type: Boolean,
    default: false,
  },
  licenseSource: {
    type: String,
    default: null,
  }
}, { timestamps: true });

export default mongoose.model('MultiFaithText', multiFaithTextSchema);
