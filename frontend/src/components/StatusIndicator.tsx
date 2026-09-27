import React from 'react';

interface StatusIndicatorProps {
  status: 'online' | 'offline' | string;
  label?: string;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({ status, label }) => {
  const isOnline = status.toLowerCase() === 'online' || status.toLowerCase() === 'healthy';
  const displayLabel = label || (isOnline ? 'SYSTEM ONLINE' : 'DISCONNECTED');

  return (
    <div className={`status-pill ${isOnline ? 'online' : 'offline'}`} role="status">
      <span className="status-dot" aria-hidden="true" />
      <span>{displayLabel}</span>
    </div>
  );
};
