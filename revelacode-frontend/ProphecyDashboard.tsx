
import React, { useEffect, useState } from 'react';
import axios from 'axios';

interface ProphecyData {
  symbol: string;
  meaning: string;
  reference: string;
  status: string;
  fulfilled: string;
  tags: string[];
}

const ProphecyDashboard: React.FC = () => {
  const [prophecies, setProphecies] = useState<Record<string, ProphecyData>>({});
  const [selectedTag, setSelectedTag] = useState<string>('all');

  useEffect(() => {
    axios.get('https://revelacode-backend.onrender.com/symbols')
      .then(response => setProphecies(response.data))
      .catch(error => console.error('Error fetching prophecies:', error));
  }, []);

  const allTags = Array.from(
    new Set(
      Object.values(prophecies).flatMap(p => p.tags || [])
    )
  );

  const filtered = Object.entries(prophecies).filter(
    ([, prophecy]) => selectedTag === 'all' || prophecy.tags.includes(selectedTag)
  );

  return (
    <div className="p-6 bg-gray-100 min-h-screen">
      <h1 className="text-3xl font-bold mb-6 text-center text-indigo-700">📜 RevelaCode Prophecy Dashboard</h1>

      <div className="mb-4">
        <label className="mr-2 font-medium">Filter by tag:</label>
        <select
          className="border p-2 rounded"
          onChange={(e) => setSelectedTag(e.target.value)}
          value={selectedTag}
        >
          <option value="all">All</option>
          {allTags.map(tag => (
            <option key={tag} value={tag}>{tag}</option>
          ))}
        </select>
      </div>

      {filtered.map(([key, prophecy]) => (
        <div
          key={key}
          className="bg-white rounded-lg shadow-md p-6 mb-4 border border-gray-200"
        >
          <h2 className="text-xl font-semibold text-indigo-600 mb-2">🔹 {prophecy.symbol}</h2>
          <p className="mb-1"><strong>Meaning:</strong> {prophecy.meaning}</p>
          <p className="mb-1"><strong>Reference:</strong> {prophecy.reference}</p>
          <p className="mb-1"><strong>Status:</strong> <span className="capitalize">{prophecy.status}</span></p>
          <p className="mb-1"><strong>Fulfilled:</strong> {prophecy.fulfilled}</p>
          <div className="flex flex-wrap gap-2 mt-2">
            {prophecy.tags.map((tag, i) => (
              <span
                key={i}
                className="px-2 py-1 bg-indigo-100 text-indigo-800 text-xs font-medium rounded-full"
              >
                #{tag}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

export default ProphecyDashboard;
