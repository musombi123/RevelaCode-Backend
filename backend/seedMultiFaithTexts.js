// backend/seedMultiFaithTexts.js
import mongoose from 'mongoose';
import dotenv from 'dotenv';
import ScriptureText from './models/ScriptureText.js';

dotenv.config();

const seed = async () => {
  try {
    await mongoose.connect(process.env.MONGO_URI);

    await ScriptureText.deleteMany();

    await ScriptureText.create([
      // Local KJV verse
      {
        religion: 'Christianity',
        book: 'John',
        chapter: 3,
        verse: 16,
        text: 'For God so loved the world...',
        language: 'en',
        version: 'KJV',
        sourceType: 'local'
      },
      // External NIV (won't store text, just link)
      {
        religion: 'Christianity',
        book: 'John',
        chapter: 3,
        verse: 16,
        language: 'en',
        version: 'NIV',
        sourceType: 'api',
        sourceUrl: 'https://api.scripture.api.bible/v1/bibles/{BIBLE_ID}/verses/JHN.3.16'
      },
      // Quran example, local
      {
        religion: 'Islam',
        book: 'Al-Baqarah',
        chapter: 2,
        verse: 255,
        text: 'Allah! There is no deity except Him, the Ever-Living...',
        language: 'en',
        version: 'Sahih',
        sourceType: 'local'
      },
      // Gita example, API
      {
        religion: 'Hinduism',
        book: 'Bhagavad Gita',
        chapter: 2,
        verse: 47,
        language: 'en',
        version: 'EN',
        sourceType: 'api',
        sourceUrl: 'https://bhagavadgitaapi.in/slok/2/47'
      }
    ]);

    console.log('✅ Seeded multi‑faith texts!');
    process.exit();
  } catch (err) {
    console.error(err);
    process.exit(1);
  }
};

seed();
