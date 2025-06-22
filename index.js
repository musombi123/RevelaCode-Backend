const express = require('express');
const cors = require('cors');
const app = express();
const port = process.env.PORT || 5000;

app.use(cors());

app.get('/api/symbols', (req, res) => {
  res.json([
    { symbol: '🔥', meaning: 'Holy Fire' },
    { symbol: '🕊️', meaning: 'Holy Spirit' },
    // etc.
  ]);
});

app.listen(port, () => {
  console.log(`RevelaCode backend running on port ${port}`);
});
