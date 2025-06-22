const cors = require('cors');
const express = require('express');
const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());

// Sample API route
app.get('/api/prophecies', (req, res) => {
  res.json([
    {
      id: "1",
      verse: "Isaiah 53:5",
      meaning: "The suffering of Christ brings healing."
    },
    {
      id: "2",
      verse: "Joel 2:28",
      meaning: "God will pour out His spirit on all people."
    }
  ]);
});

// Start the server
app.listen(PORT, () => {
  console.log(`RevelaCode backend running on port ${PORT}`);
});
