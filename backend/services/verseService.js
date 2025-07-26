// backend/services/verseService.js
import ScriptureText from '../models/ScriptureText.js';
import axios from 'axios';

export async function getVerse({ religion, book, chapter, verse, version }) {
  const doc = await ScriptureText.findOne({
    religion,
    book,
    chapter,
    verse,
    version
  });

  if (!doc) throw new Error('Verse not found');

  if (doc.sourceType === 'local' && doc.text) {
    return doc.text;
  }

  if (doc.sourceType === 'api' && doc.sourceUrl) {
    try {
      const res = await axios.get(doc.sourceUrl, {
        headers: {
          // Example: if you need API key
          'api-key': process.env.BIBLE_API_KEY
        }
      });
      // You decide: pick correct field from API response
      const externalText = res.data.data?.content || res.data?.text;

      // Optional: cache it
      doc.text = externalText;
      doc.sourceType = 'local';
      await doc.save();

      return externalText;
    } catch (err) {
      console.error('Error fetching from external API:', err);
      throw new Error('External verse fetch failed');
    }
  }

  throw new Error('Invalid verse config');
}
