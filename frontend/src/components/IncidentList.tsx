import React from 'react';
import { ShieldAlert, Inbox } from 'lucide-react';
import { IncidentResponse } from '../types/api';
import { IncidentItem } from './IncidentItem';

interface IncidentListProps {
  incidents: IncidentResponse[];
  loading?: boolean;
  totalCount?: number;
}

export const IncidentList: React.FC<IncidentListProps> = ({
  incidents = [],
  loading = false,
  totalCount,
}) => {
  const safeIncidents = Array.isArray(incidents) ? incidents : [];

  return (
    <section className="incidents-panel" aria-label="Recent Incidents Timeline">
      {/* Panel Header */}
      <div className="incidents-panel-header">
        <div className="incidents-header-title">
          <ShieldAlert size={14} color="var(--severity-critical)" />
          <span>RECENT INCIDENTS</span>
        </div>
        <div className="incidents-header-count">
          {totalCount !== undefined ? `TOTAL: ${totalCount}` : `${safeIncidents.length} EVENTS`}
        </div>
      </div>

      {/* Independent Scrollable Timeline Feed */}
      <div className="incident-feed-scroll">
        {loading && safeIncidents.length === 0 ? (
          <div className="empty-state-box mono">
            <span>SYNCING INCIDENT DATABASE...</span>
          </div>
        ) : safeIncidents.length === 0 ? (
          <div className="empty-state-box">
            <Inbox className="empty-state-icon" />
            <span className="mono" style={{ fontWeight: 600 }}>NO PERIMETER BREACHES DETECTED</span>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Perimeter is secure.
            </span>
          </div>
        ) : (
          <div className="timeline-track-container">
            {safeIncidents.map((incident, index) => (
              <IncidentItem
                key={incident.id}
                incident={incident}
                isLatest={index === 0}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
};
