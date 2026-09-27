import { useState, useId } from 'react';
import {
  ShieldAlert,
  Camera,
  Activity,
  AlertTriangle,
  TrendingUp,
} from 'lucide-react';
import { AnalyticsResponse, TimeSeriesPoint } from '../types/api';

interface AnalyticsChartsProps {
  analytics: AnalyticsResponse | null;
  timeRange: '24h' | '7d' | 'all';
  onTimeRangeChange: (range: '24h' | '7d' | 'all') => void;
  loading?: boolean;
}

/**
 * 1. Incidents Over Time - Responsive SVG Area Chart
 */
export const IncidentsOverTimeChart: React.FC<{
  points: TimeSeriesPoint[];
  loading?: boolean;
}> = ({ points, loading }) => {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const gradId = useId();

  if (loading) {
    return (
      <div className="chart-card">
        <div className="chart-header">
          <div className="chart-title">
            <TrendingUp size={15} className="chart-icon text-cyan" />
            <span>INCIDENT TEMPORAL VELOCITY</span>
          </div>
        </div>
        <div className="chart-loading-skeleton" />
      </div>
    );
  }

  const width = 640;
  const height = 180;
  const padLeft = 40;
  const padRight = 20;
  const padTop = 20;
  const padBottom = 30;

  const chartWidth = width - padLeft - padRight;
  const chartHeight = height - padTop - padBottom;

  const maxVal = Math.max(...points.map((p) => p.count), 5);
  // Y-axis tick intervals
  const yTicks = [0, Math.ceil(maxVal / 2), maxVal];

  // Coordinate mapping
  const getX = (index: number) => {
    if (points.length <= 1) return padLeft + chartWidth / 2;
    return padLeft + (index / (points.length - 1)) * chartWidth;
  };

  const getY = (val: number) => {
    return padTop + chartHeight - (val / maxVal) * chartHeight;
  };

  // Build SVG Path
  const linePath = points.length > 0
    ? points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${getX(i).toFixed(1)},${getY(p.count).toFixed(1)}`).join(' ')
    : '';

  const areaPath = points.length > 0
    ? `${linePath} L ${getX(points.length - 1).toFixed(1)},${(padTop + chartHeight).toFixed(1)} L ${getX(0).toFixed(1)},${(padTop + chartHeight).toFixed(1)} Z`
    : '';

  const activePoint = hoverIndex !== null && hoverIndex >= 0 && hoverIndex < points.length
    ? points[hoverIndex]
    : null;

  // Decide how many X labels to display to avoid clutter
  const labelInterval = points.length > 14 ? Math.ceil(points.length / 7) : Math.ceil(points.length / 6);

  return (
    <div className="chart-card">
      <div className="chart-header">
        <div className="chart-title">
          <TrendingUp size={15} className="chart-icon text-cyan" />
          <span>INCIDENT TEMPORAL VELOCITY</span>
        </div>
        <div className="chart-legend-inline">
          <span className="legend-dot bg-cyan" />
          <span className="text-secondary mono text-xs">All Incidents</span>
        </div>
      </div>

      <div className="chart-svg-container" style={{ position: 'relative' }}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="analytics-svg"
          preserveAspectRatio="none"
          onMouseLeave={() => setHoverIndex(null)}
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#0ea5e9" stopOpacity="0.35" />
              <stop offset="90%" stopColor="#0ea5e9" stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Horizontal grid lines and Y-axis labels */}
          {yTicks.map((tickVal, i) => {
            const y = getY(tickVal);
            return (
              <g key={`ytick-${i}`}>
                <line
                  x1={padLeft}
                  y1={y}
                  x2={width - padRight}
                  y2={y}
                  stroke="var(--border-subtle)"
                  strokeDasharray="3 3"
                  strokeWidth="1"
                />
                <text
                  x={padLeft - 8}
                  y={y + 3}
                  textAnchor="end"
                  fill="var(--text-dim)"
                  fontSize="10"
                  fontFamily="var(--font-mono)"
                >
                  {tickVal}
                </text>
              </g>
            );
          })}

          {/* Area fill */}
          {areaPath && <path d={areaPath} fill={`url(#${gradId})`} />}

          {/* Main stroke line */}
          {linePath && (
            <path
              d={linePath}
              fill="none"
              stroke="#0ea5e9"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Interactive touch/hover columns */}
          {points.map((p, i) => {
            const x = getX(i);
            const y = getY(p.count);
            const isHovered = hoverIndex === i;

            return (
              <g key={`col-${i}`} onMouseEnter={() => setHoverIndex(i)}>
                {/* Invisible wide capture area */}
                <rect
                  x={x - (chartWidth / points.length) / 2}
                  y={padTop}
                  width={chartWidth / points.length}
                  height={chartHeight}
                  fill="transparent"
                  style={{ cursor: 'pointer' }}
                />

                {isHovered && (
                  <line
                    x1={x}
                    y1={padTop}
                    x2={x}
                    y2={padTop + chartHeight}
                    stroke="#0ea5e9"
                    strokeWidth="1"
                    strokeDasharray="2 2"
                    opacity="0.8"
                  />
                )}

                {/* Point dot */}
                {(isHovered || points.length <= 12 || p.count > 0) && (
                  <circle
                    cx={x}
                    cy={y}
                    r={isHovered ? 4.5 : 2.5}
                    fill={isHovered ? '#38bdf8' : '#0ea5e9'}
                    stroke="var(--bg-surface)"
                    strokeWidth="1.5"
                    style={{ transition: 'r 0.15s ease' }}
                  />
                )}

                {/* X-axis label */}
                {(i % labelInterval === 0 || i === points.length - 1) && (
                  <text
                    x={x}
                    y={height - 8}
                    textAnchor="middle"
                    fill="var(--text-muted)"
                    fontSize="10"
                    fontFamily="var(--font-mono)"
                  >
                    {p.time_bucket}
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        {/* Hover Tooltip Overlay */}
        {activePoint && (
          <div
            className="chart-tooltip"
            style={{
              left: `${Math.min(Math.max(getX(hoverIndex!), 80), width - 80)}px`,
              top: `${Math.max(getY(activePoint.count) - 50, 10)}px`,
            }}
          >
            <div className="tooltip-header mono">{activePoint.time_bucket}</div>
            <div className="tooltip-row">
              <span className="text-secondary">Incidents:</span>
              <span className="mono font-bold text-primary">{activePoint.count}</span>
            </div>
            {activePoint.intrusions > 0 && (
              <div className="tooltip-row text-xs">
                <span className="text-critical">Intrusions:</span>
                <span className="mono text-critical font-semibold">{activePoint.intrusions}</span>
              </div>
            )}
            {activePoint.tripwires > 0 && (
              <div className="tooltip-row text-xs">
                <span className="text-warning">Tripwires:</span>
                <span className="mono text-warning font-semibold">{activePoint.tripwires}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * 2. Incident Classification - Horizontal Bar Breakdown
 */
export const EventTypeBarChart: React.FC<{
  typeCounts: Record<string, number>;
  totalIncidents: number;
  loading?: boolean;
}> = ({ typeCounts, totalIncidents, loading }) => {
  if (loading) {
    return (
      <div className="chart-card">
        <div className="chart-header">
          <div className="chart-title">
            <ShieldAlert size={15} className="chart-icon text-critical" />
            <span>CLASSIFICATION BREAKDOWN</span>
          </div>
        </div>
        <div className="chart-loading-skeleton" />
      </div>
    );
  }

  const intrusions = typeCounts['ZONE_INTRUSION'] || 0;
  const tripwires = typeCounts['TRIPWIRE_CROSSING'] || 0;
  const baseTotal = totalIncidents > 0 ? totalIncidents : 1;

  const intrusionPct = Math.round((intrusions / baseTotal) * 100);
  const tripwirePct = Math.round((tripwires / baseTotal) * 100);

  return (
    <div className="chart-card">
      <div className="chart-header">
        <div className="chart-title">
          <ShieldAlert size={15} className="chart-icon text-critical" />
          <span>CLASSIFICATION BREAKDOWN</span>
        </div>
        <span className="mono text-xs text-muted">
          TOTAL: {totalIncidents}
        </span>
      </div>

      <div className="bars-container">
        {/* Zone Intrusion Bar */}
        <div className="bar-group">
          <div className="bar-label-row">
            <div className="bar-label-name">
              <span className="legend-dot bg-critical" />
              <span>Zone Intrusion (Polygon)</span>
            </div>
            <div className="bar-metrics mono">
              <span className="font-bold text-critical">{intrusions}</span>
              <span className="text-muted text-xs">({intrusionPct}%)</span>
            </div>
          </div>
          <div className="bar-track">
            <div
              className="bar-fill bg-critical"
              style={{ width: `${totalIncidents === 0 ? 0 : Math.max(intrusionPct, 2)}%` }}
            />
          </div>
        </div>

        {/* Tripwire Crossing Bar */}
        <div className="bar-group">
          <div className="bar-label-row">
            <div className="bar-label-name">
              <span className="legend-dot bg-warning" />
              <span>Tripwire Crossing (Vector)</span>
            </div>
            <div className="bar-metrics mono">
              <span className="font-bold text-warning">{tripwires}</span>
              <span className="text-muted text-xs">({tripwirePct}%)</span>
            </div>
          </div>
          <div className="bar-track">
            <div
              className="bar-fill bg-warning"
              style={{ width: `${totalIncidents === 0 ? 0 : Math.max(tripwirePct, 2)}%` }}
            />
          </div>
        </div>

        {totalIncidents === 0 && (
          <div className="chart-empty-notice mono text-muted text-xs">
            NO INCIDENTS RECORDED IN SELECTED INTERVAL
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * 3. Severity Distribution - SVG Donut Chart
 */
export const SeverityDonutChart: React.FC<{
  severityCounts: Record<string, number>;
  totalIncidents: number;
  loading?: boolean;
}> = ({ severityCounts, totalIncidents, loading }) => {
  if (loading) {
    return (
      <div className="chart-card">
        <div className="chart-header">
          <div className="chart-title">
            <AlertTriangle size={15} className="chart-icon text-warning" />
            <span>SEVERITY PROFILE</span>
          </div>
        </div>
        <div className="chart-loading-skeleton" />
      </div>
    );
  }

  const critical = severityCounts['critical'] || 0;
  const warning = severityCounts['warning'] || 0;

  // Donut geometry
  const size = 130;
  const strokeWidth = 14;
  const radius = (size - strokeWidth) / 2;
  const center = size / 2;
  const circumference = 2 * Math.PI * radius;

  const criticalPct = totalIncidents > 0 ? (critical / totalIncidents) : 0;
  const warningPct = totalIncidents > 0 ? (warning / totalIncidents) : 0;

  const criticalStroke = circumference * criticalPct;
  const warningStroke = circumference * warningPct;

  return (
    <div className="chart-card">
      <div className="chart-header">
        <div className="chart-title">
          <AlertTriangle size={15} className="chart-icon text-warning" />
          <span>SEVERITY PROFILE</span>
        </div>
      </div>

      <div className="donut-layout">
        <div className="donut-svg-wrapper">
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            {/* Background ring */}
            <circle
              cx={center}
              cy={center}
              r={radius}
              fill="transparent"
              stroke="var(--border-subtle)"
              strokeWidth={strokeWidth}
            />

            {totalIncidents > 0 ? (
              <>
                {/* Critical arc */}
                <circle
                  cx={center}
                  cy={center}
                  r={radius}
                  fill="transparent"
                  stroke="#ef4444"
                  strokeWidth={strokeWidth}
                  strokeDasharray={`${criticalStroke} ${circumference}`}
                  strokeDashoffset={0}
                  transform={`rotate(-90 ${center} ${center})`}
                  style={{ transition: 'stroke-dasharray 0.3s ease' }}
                />
                {/* Warning arc */}
                <circle
                  cx={center}
                  cy={center}
                  r={radius}
                  fill="transparent"
                  stroke="#f59e0b"
                  strokeWidth={strokeWidth}
                  strokeDasharray={`${warningStroke} ${circumference}`}
                  strokeDashoffset={-criticalStroke}
                  transform={`rotate(-90 ${center} ${center})`}
                  style={{ transition: 'stroke-dasharray 0.3s ease' }}
                />
              </>
            ) : null}

            {/* Center Summary */}
            <text
              x={center}
              y={center - 2}
              textAnchor="middle"
              className="donut-center-total mono"
              fill="var(--text-primary)"
              fontSize="18"
              fontWeight="bold"
            >
              {totalIncidents}
            </text>
            <text
              x={center}
              y={center + 14}
              textAnchor="middle"
              fill="var(--text-muted)"
              fontSize="9"
              letterSpacing="0.08em"
            >
              BREACHES
            </text>
          </svg>
        </div>

        {/* Legend */}
        <div className="donut-legend">
          <div className="donut-legend-item">
            <span className="legend-dot bg-critical" />
            <div className="legend-info">
              <span className="legend-name text-xs">Critical</span>
              <span className="legend-val mono font-semibold text-critical">
                {critical} <span className="text-muted text-2xs">({Math.round(criticalPct * 100)}%)</span>
              </span>
            </div>
          </div>
          <div className="donut-legend-item">
            <span className="legend-dot bg-warning" />
            <div className="legend-info">
              <span className="legend-name text-xs">Warning</span>
              <span className="legend-val mono font-semibold text-warning">
                {warning} <span className="text-muted text-2xs">({Math.round(warningPct * 100)}%)</span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

/**
 * 4. Camera Node Distribution
 */
export const CameraDistributionChart: React.FC<{
  cameraCounts: Record<string, number>;
  totalIncidents: number;
  loading?: boolean;
}> = ({ cameraCounts, totalIncidents, loading }) => {
  if (loading) {
    return (
      <div className="chart-card">
        <div className="chart-header">
          <div className="chart-title">
            <Camera size={15} className="chart-icon text-cyan" />
            <span>INCIDENTS BY SURVEILLANCE NODE</span>
          </div>
        </div>
        <div className="chart-loading-skeleton" />
      </div>
    );
  }

  const entries = Object.entries(cameraCounts);
  const maxVal = Math.max(...Object.values(cameraCounts), 1);

  return (
    <div className="chart-card">
      <div className="chart-header">
        <div className="chart-title">
          <Camera size={15} className="chart-icon text-cyan" />
          <span>INCIDENTS BY SURVEILLANCE NODE</span>
        </div>
        <span className="mono text-xs text-muted">
          NODES: {entries.length}
        </span>
      </div>

      <div className="bars-container">
        {entries.length > 0 ? (
          entries.map(([camId, count]) => {
            const pct = Math.round((count / (totalIncidents || 1)) * 100);
            const barWidth = Math.round((count / maxVal) * 100);
            return (
              <div key={camId} className="bar-group">
                <div className="bar-label-row">
                  <div className="bar-label-name">
                    <span className="legend-dot bg-cyan" />
                    <span className="mono text-primary font-medium">{camId}</span>
                  </div>
                  <div className="bar-metrics mono">
                    <span className="font-bold text-cyan">{count}</span>
                    <span className="text-muted text-xs">({pct}%)</span>
                  </div>
                </div>
                <div className="bar-track">
                  <div className="bar-fill bg-cyan" style={{ width: `${barWidth}%` }} />
                </div>
              </div>
            );
          })
        ) : (
          <div className="chart-empty-notice mono text-muted text-xs">
            NO CAMERA SENSOR ACTIVITY RECORDED IN SELECTED INTERVAL
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * Unified Analytics Section with Time-Range Selector
 */
export const AnalyticsDashboardSection: React.FC<AnalyticsChartsProps> = ({
  analytics,
  timeRange,
  onTimeRangeChange,
  loading,
}) => {
  return (
    <section className="analytics-section" aria-label="Surveillance Analytics">
      {/* Analytics Toolbar */}
      <div className="analytics-toolbar">
        <div className="analytics-toolbar-title">
          <Activity size={16} className="text-cyan" />
          <h2 className="section-title">REAL-TIME SURVEILLANCE ANALYTICS</h2>
        </div>

        {/* Time Range Filter Controls */}
        <div className="time-range-group" role="tablist" aria-label="Time Window Range">
          <button
            type="button"
            className={`time-range-btn ${timeRange === '24h' ? 'active' : ''}`}
            onClick={() => onTimeRangeChange('24h')}
            aria-selected={timeRange === '24h'}
          >
            24 Hours
          </button>
          <button
            type="button"
            className={`time-range-btn ${timeRange === '7d' ? 'active' : ''}`}
            onClick={() => onTimeRangeChange('7d')}
            aria-selected={timeRange === '7d'}
          >
            7 Days
          </button>
          <button
            type="button"
            className={`time-range-btn ${timeRange === 'all' ? 'active' : ''}`}
            onClick={() => onTimeRangeChange('all')}
            aria-selected={timeRange === 'all'}
          >
            All Time
          </button>
        </div>
      </div>

      {/* Grid of Charts */}
      <div className="analytics-grid">
        <div className="chart-col-lg">
          <IncidentsOverTimeChart
            points={analytics?.incidents_over_time || []}
            loading={loading}
          />
        </div>
        <div className="chart-col-sm">
          <SeverityDonutChart
            severityCounts={analytics?.incidents_by_severity || {}}
            totalIncidents={analytics?.total_incidents || 0}
            loading={loading}
          />
        </div>
        <div className="chart-col-half">
          <EventTypeBarChart
            typeCounts={analytics?.incidents_by_type || {}}
            totalIncidents={analytics?.total_incidents || 0}
            loading={loading}
          />
        </div>
        <div className="chart-col-half">
          <CameraDistributionChart
            cameraCounts={analytics?.incidents_by_camera || {}}
            totalIncidents={analytics?.total_incidents || 0}
            loading={loading}
          />
        </div>
      </div>
    </section>
  );
};
