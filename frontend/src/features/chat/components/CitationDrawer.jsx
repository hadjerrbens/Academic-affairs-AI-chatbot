import React from 'react';

export const CitationDrawer = ({ citation, onClose }) => {
  if (!citation) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative w-full max-w-md bg-white h-full shadow-xl p-6 overflow-y-auto">
        <button onClick={onClose} className="absolute top-4 right-4 text-gray-500 hover:text-black">
          ✕
        </button>
        <h2 className="text-lg font-bold text-gray-900 mb-2">{citation.title}</h2>
        <p className="text-sm text-gray-500 mb-4">{citation.section}</p>
        <div className="text-sm text-gray-700 whitespace-pre-wrap border-t pt-4">
          "{citation.text}"
        </div>
      </div>
    </div>
  );
};