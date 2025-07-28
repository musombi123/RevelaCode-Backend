import express from 'express';
import { getVerse } from '../services/verseService.js';

const router = express.Router();

router.post('/', async (req, res) => {
  try {
    const text = await getVerse(req.body);
    res.json({ text });
  } catch (err) {
    res.status(500).json({ message: err.message });
  }
});

export default router;
