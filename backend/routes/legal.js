// backend/routes/legal.js
import express from 'express';
import LegalDoc from '../models/LegalDoc.js';

const router = express.Router();

router.get('/:type', async (req, res) => {
  try {
    const doc = await LegalDoc.findOne({ type: req.params.type }).sort({ version: -1 });
    if (!doc) return res.status(404).json({ message: 'Not found' });
    res.json(doc);
  } catch (err) {
    res.status(500).json({ message: err.message });
  }
});

export default router;
