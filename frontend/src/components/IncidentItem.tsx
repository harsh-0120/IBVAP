import React from 'react';
import { ShieldAlert, ArrowRightLeft, ArrowRight } from 'lucide-react';
import { IncidentResponse } from '../types/api';
import { formatIncidentTime, formatConfidence } from '../utils/formatters';
import { api } from '../services/api';

interface IncidentItemProps {
  incident: IncidentResponse;
  isLatest?: boolean;
}

export const IncidentItem: React.FC<IncidentItemProps> = ({
  incident,
  isLatest = false,
}) => {
  const isZoneIntrusion = incident.event_type === 'ZONE_INTRUSION';
  const severityType = isZoneIntrusion ? 'critical' : 'warning';

  const snapshotUrl = api.getSnapshotUrl(incident.id);
  const timeFormatted = formatIncidentTime(incident.timestamp, incident.iso_timestamp, false);

  const formattedDirection =
    incident.direction === 'LEFT_TO_RIGHT'
      ? 'LEFT → RIGHT'
      : incident.direction === 'RIGHT_TO_LEFT'
      ? 'RIGHT → LEFT'
      : null;

  return (
    <article
      className="timeline-event-item"
      aria-label={`Incident #${incident.id}: ${incident.event_type}`}
    >
      {/* Small Timeline Node Marker (Red for intrusion, Amber for tripwire) */}
      <span className={`timeline-node-marker ${severityType}`} />

      {/* Event Header: Type + Timestamp */}
      <div className="timeline-event-header">
        <div className={`timeline-event-type ${severityType}`}>
          {isZoneIntrusion ? (
            <ShieldAlert size={12} />
          ) : (
            <ArrowRightLeft size={12} />
          )}
          <span>{isZoneIntrusion ? 'ZONE INTRUSION' : 'TRIPWIRE CROSSING'}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
          {isLatest && <span className="timeline-new-badge">NEW</span>}
          <time className="timeline-event-time" dateTime={incident.iso_timestamp}>
            {timeFormatted}
          </time>
        </div>
      </div>

      {/* Target Boundary / Zone Name */}
      <div className="timeline-zone-name">
        {incident.zone_name}
      </div>

      {/* Metadata Row: Camera, Track ID, Direction, Confidence */}
      <div className="timeline-meta-row">
        <div>
          <span>{incident.camera_id}</span>
          <span style={{ margin: '0 5px', color: 'var(--border-strong)' }}>│</span>
          <span className="timeline-meta-target">Track #{incident.track_id}</span>
        </div>

        <div>
          {formattedDirection && (
            <span style={{ color: 'var(--severity-warning)', marginRight: '8px' }}>
              {formattedDirection}
            </span>
          )}
          {incident.confidence !== null && (
            <span style={{ color: 'var(--text-secondary)' }}>
              {formatConfidence(incident.confidence)}
            </span>
          )}
        </div>
      </div>

      {/* Action Footer: Incident ID + Verified Forensic Snapshot Link */}
      <div className="timeline-action-row">
        <span className="mono" style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
          ID #{incident.id}
        </span>

        <a
          href={snapshotUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="timeline-snapshot-btn"
          title="Open verified forensic snapshot JPEG"
        >
          <span>VIEW SNAPSHOT</span>
          <ArrowRight size={11} />
        </a>
      </div>
    </article>
  );
};
