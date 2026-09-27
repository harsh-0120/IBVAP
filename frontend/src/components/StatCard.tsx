import React from 'react';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string | number;
  subtext?: string;
  icon?: LucideIcon;
  variant?: 'critical' | 'warning' | 'online' | 'neutral' | 'default';
  loading?: boolean;
}

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  subtext,
  icon: Icon,
  variant = 'default',
  loading = false,
}) => {
  const accentClass = variant !== 'default' ? `accent-${variant}` : '';

  return (
    <div
      className="telemetry-bar-item stat-card"
      role="region"
      aria-label={label}
    >
      <div className="telemetry-item-left stat-card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
          {Icon && <Icon size={12} color="var(--text-muted)" />}
          <span className="telemetry-item-label">{label}</span>
        </div>
        {subtext && (
          <span className="telemetry-item-sub stat-card-sub mono">
            {subtext}
          </span>
        )}
      </div>

      <div className={`telemetry-item-value stat-card-value ${accentClass}`}>
        {loading ? '...' : value}
      </div>
    </div>
  );
};
