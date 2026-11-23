import React from 'react';

export const ToolCard = ({ toolName, data }) => {
  return (
    <div className="my-4 p-4 border rounded-lg bg-gray-50 shadow-sm">
      <div className="flex items-center space-x-2 mb-2">
        <span className="text-sm font-bold text-gray-600 uppercase tracking-wider">
          {toolName.replace(/_/g, ' ')}
        </span>
      </div>
      
      {data.summary && (
        <p className="text-sm text-gray-800">{data.summary}</p>
      )}

      {toolName === 'check_waiver_eligibility' && (
        <div className="mt-2 text-sm">
          <strong>Verdict:</strong> <span className="uppercase font-semibold text-blue-600">{data.verdict}</span>
          {data.required_documents && data.required_documents.length > 0 && (
            <div className="mt-2">
              <strong>Required Documents:</strong>
              <ul className="list-disc pl-5">
                {data.required_documents.map((doc, i) => <li key={i}>{doc}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};