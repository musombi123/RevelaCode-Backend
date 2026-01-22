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
  
  return jsonify({
    "status": "success",
    "type": doc.get("type"),
    "content": doc.get("content"),
    "version": doc.get("version", "1.0"),
    "lastUpdated": doc.get("lastUpdated") or doc.get("updated_at") or datetime.utcnow().isoformat()
  }), 200
}

export default LegalText;
