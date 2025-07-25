import LegalDoc from '../models/LegalDoc.js';

// Get legal text by type
export const getLegalDoc = async (req, res) => {
  try {
    const type = req.params.type; // 'privacy' or 'terms'
    const doc = await LegalDoc.findOne({ type });
    if (!doc) return res.status(404).json({ message: 'Document not found' });
    res.json({
      type: doc.type,
      content: doc.content,
      lastUpdated: doc.lastUpdated,
      version: doc.version
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ message: 'Server error' });
  }
};

// Update legal text (admin only)
export const updateLegalDoc = async (req, res) => {
  try {
    const { type, content, version } = req.body;
    if (!type || !content) return res.status(400).json({ message: 'Type and content required' });
    
    const doc = await LegalDoc.findOneAndUpdate(
      { type },
      { content, lastUpdated: Date.now(), version },
      { upsert: true, new: true }
    );
    res.json({ message: 'Document updated', doc });
  } catch (err) {
    console.error(err);
    res.status(500).json({ message: 'Server error' });
  }
};
