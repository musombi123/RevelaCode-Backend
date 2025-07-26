import React, { useState, useEffect } from 'react';

const LegalText = ({ type }) => {
  const [content, setContent] = useState('');
  const [lastUpdated, setLastUpdated] = useState('');

  useEffect(() => {
    fetch(`/api/legal/${type}`)
      .then(res => res.json())
      .then(data => {
        setContent(data.content);
        setLastUpdated(new Date(data.lastUpdated).toLocaleDateString());
      })
      .catch(console.error);
  }, [type]);

  return (
    <div className="p-4">
      <h2 className="text-xl font-bold capitalize">{type} Policy</h2>
      <p className="text-sm text-gray-500">Last updated: {lastUpdated}</p>
      <div className="prose mt-4 whitespace-pre-wrap">{content}</div>
    </div>
  );
};

export default LegalText;
