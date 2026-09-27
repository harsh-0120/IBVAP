import React from 'react';
import { Shield, Activity } from 'lucide-react';
import { ZoneResponse, IncidentResponse } from '../types/api';

interface ZoneSummaryProps {
  zonesData: ZoneResponse | null;
  loading?: boolean;
  incidents?: IncidentResponse[];
}

export const ZoneSummary: React.FC<ZoneSummaryProps> = ({
  zonesData,
  loading = false,
  incidents = [],
}) => {
  const zones = zonesData?.zones || [];
  const tripwires = zonesData?.tripwires || [];

  const getIncidentCountForBoundary = (id: string, name: string) => {
    return incidents.filter(
      (inc) => inc.zone_id === id || inc.zone_name === name
    ).length;
  };

  return (
    <div className="zones-panel" aria-label="Monitored Spatial Boundaries">
      {/* Restricted Virtual Fences Section */}
      <div className="zones-panel-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Shield size={14} color="var(--severity-critical)" />
          <span>RESTRICTED VIRTUAL FENCES</span>
        </div>
        <span className="mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
          {zones.length} CONFIGURED
        </span>
      </div>

      <div className="zones-rows-container">
        {loading && zones.length === 0 ? (
          <div className="empty-state-box mono" style={{ padding: '12px' }}>
            <span>SYNCING ZONES...</span>
          </div>
        ) : zones.length === 0 ? (
          <div className="zone-operational-row" style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
            No restricted zones configured
          </div>
        ) : (
          zones.map((zone) => {
            const eventCount = getIncidentCountForBoundary(zone.id, zone.name);
            const isActive = eventCount > 0;

            return (
              <div key={zone.id} className="zone-operational-row">
                <div className="zone-row-left">
                  <span
                    className="zone-status-indicator"
                    style={{
                      backgroundColor: isActive
                        ? 'var(--severity-critical)'
                        : 'var(--status-online)',
                    }}
                  />
                  <div>
                    <div className="zone-row-name">{zone.name}</div>
                    <div className="zone-row-sub">
                      {isActive
                        ? `${eventCount} recent event${eventCount > 1 ? 's' : ''}`
                        : 'No recent events'}
                    </div>
                  </div>
                </div>
                <span className={`zone-row-tag ${isActive ? 'active' : 'secured'}`}>
                  {isActive ? 'ACTIVE' : 'SECURED'}
                </span>
              </div>
            );
          })
        )}
      </div>

      {/* Directional Tripwires Section */}
      <div className="zones-panel-header" style={{ borderTop: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={14} color="var(--severity-warning)" />
          <span>DIRECTIONAL TRIPWIRES</span>
        </div>
        <span className="mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
          {tripwires.length} CONFIGURED
        </span>
      </div>

      <div className="zones-rows-container">
        {loading && tripwires.length === 0 ? (
          <div className="empty-state-box mono" style={{ padding: '12px' }}>
            <span>SYNCING TRIPWIRES...</span>
          </div>
        ) : tripwires.length === 0 ? (
          <div className="zone-operational-row" style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
            No directional tripwires configured
          </div>
        ) : (
          tripwires.map((wire) => {
            const eventCount = getIncidentCountForBoundary(wire.id, wire.name);
            const isActive = eventCount > 0;

            return (
              <div key={wire.id} className="zone-operational-row">
                <div className="zone-row-left">
                  <span
                    className="zone-status-indicator"
                    style={{
                      backgroundColor: isActive
                        ? 'var(--severity-warning)'
                        : 'var(--status-online)',
                    }}
                  />
                  <div>
                    <div className="zone-row-name">{wire.name}</div>
                    <div className="zone-row-sub">
                      {isActive
                        ? `${eventCount} recent crossing${eventCount > 1 ? 's' : ''}`
                        : 'No recent crossings'}
                    </div>
                  </div>
                </div>
                <span
                  className={`zone-row-tag ${isActive ? 'active' : 'secured'}`}
                  style={
                    isActive
                      ? {
                          background: 'var(--severity-warning-bg)',
                          borderColor: 'var(--severity-warning-border)',
                          color: 'var(--severity-warning)',
                        }
                      : undefined
                  }
                >
                  {isActive ? 'ACTIVE' : 'SECURED'}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
