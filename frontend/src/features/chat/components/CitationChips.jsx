import React, { useState } from 'react';
import { CitationDrawer } from './CitationDrawer';

export const CitationChips = ({ citations }) => {
  const [activeCitation, setActiveCitation] = useState(null);

  if (!citations || citations.length === 0) return null;

  return (
    <>
      <div className="flex flex-wrap gap-2 mt-2">
        {citations.map((cite, index) => (
          <button
            key={cite.id}
            onClick={() => setActiveCitation(cite)}
            className="inline-flex items-center px-2 py-1 text-xs font-medium bg-blue-100 text-blue-700 rounded-md hover:bg-blue-200 transition-colors"
          >
            [{index + 1}] {cite.title}
          </button>
        ))}
      </div>
      
      <CitationDrawer 
        citation={activeCitation} 
        onClose={() => setActiveCitation(null)} 
      />
    </>
  );
};