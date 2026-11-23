import React, { useState } from 'react';

export const ConfirmCard = ({ actionId, summary, fee, estimatedDays }) => {
  const [status, setStatus] = useState('idle');
  const [errorMessage, setErrorMessage] = useState('');

  const handleAction = async (endpoint) => {
    setStatus('loading');
    try {
      const res = await fetch(`/api/actions/${actionId}/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!res.ok) throw new Error(await res.text());

      if (endpoint === 'cancel') {
        setStatus('success');
        setErrorMessage('Action cancelled.');
      } else {
        setStatus('success');
      }
    } catch (err) {
      setStatus('error');
      setErrorMessage(err.message || 'Failed to process action.');
    }
  };

  if (status === 'success') {
    return (
      <div className="my-4 p-4 border rounded-lg bg-green-50 border-green-200">
        <p className="text-green-800 font-medium">
          {errorMessage || 'Transcript request confirmed successfully!'}
        </p>
      </div>
    );
  }

  return (
    <div className="my-4 p-5 border border-blue-200 rounded-lg bg-blue-50 shadow-sm">
      <h3 className="font-bold text-blue-900 mb-2">Pending Action Confirmation</h3>
      <p className="text-sm text-gray-700 mb-4">{summary}</p>
      
      <div className="flex justify-between items-center text-sm mb-4 bg-white p-3 rounded border">
        <span><strong>Fee:</strong> ${fee}</span>
        <span><strong>Est. Delivery:</strong> {estimatedDays} days</span>
      </div>

      {status === 'error' && <p className="text-red-600 text-sm mb-2">{errorMessage}</p>}

      <div className="flex space-x-3">
        <button
          onClick={() => handleAction('confirm')}
          disabled={status === 'loading'}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {status === 'loading' ? 'Processing...' : 'Confirm & Submit'}
        </button>
        <button
          onClick={() => handleAction('cancel')}
          disabled={status === 'loading'}
          className="px-4 py-2 bg-white text-gray-700 text-sm font-medium rounded border hover:bg-gray-50 disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </div>
  );
};