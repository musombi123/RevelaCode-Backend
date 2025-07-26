import React, { useState } from 'react';

const UpdateLegalDoc = () => {
  const [type, setType] = useState('privacy');
  const [content, setContent] = useState('');
  const [version, setVersion] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch('/api/legal/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, content, version })
      });
      const data = await res.json();
      alert('Updated successfully!');
      console.log(data);
    } catch (err) {
      console.error(err);
      alert('Error updating');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 p-4">
      <div>
        <label className="block mb-1">Type:</label>
        <select value={type} onChange={e => setType(e.target.value)} className="border p-2">
          <option value="privacy">Privacy</option>
          <option value="terms">Terms</option>
        </select>
      </div>
      <div>
        <label className="block mb-1">Content:</label>
        <textarea value={content} onChange={e => setContent(e.target.value)} rows="10" className="border p-2 w-full"></textarea>
      </div>
      <div>
        <label className="block mb-1">Version (e.g., 1.1):</label>
        <input value={version} onChange={e => setVersion(e.target.value)} className="border p-2" />
      </div>
      <button type="submit" className="bg-blue-500 text-white px-4 py-2 rounded">Update</button>
    </form>
  );
};

export default UpdateLegalDoc;
