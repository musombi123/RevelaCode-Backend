import express from 'express';
import cors from 'cors';
import legalRoutes from './routes/legal.routes.js';

const app = express();
const port = process.env.PORT || 5000;

app.use(cors());
app.use(express.json());

app.use('/api/legal', legalRoutes);

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
