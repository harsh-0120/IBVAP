import React, { useEffect, useState } from 'react';
import { Camera, Clock, Wifi, WifiOff } from 'lucide-react';
import { StatusIndicator } from './StatusIndicator';

interface HeaderProps {
  systemStatus: string;
  cameraCount: number | string;
  wsStatus?: string;
}

export const Header: React.FC<HeaderProps> = ({
  systemStatus,
  cameraCount,
  wsStatus = 'CONNECTED',
}) => {
  const [currentTime, setCurrentTime] = useState<string>('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const dateStr = now.toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      });
      const timeStr = now.toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      });
      setCurrentTime(`${dateStr}  ${timeStr} UTC`);
    };

    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const formattedCameraCount =
    typeof cameraCount === 'number'
      ? cameraCount < 10
        ? `0${cameraCount}`
        : `${cameraCount}`
      : cameraCount;

  const isWsConnected = wsStatus === 'CONNECTED';

  return (
    <header className="top-header" role="banner">
      {/* Left Branding & Station Identifier */}
      <div className="header-left">
        <div className="header-title-block">
          <h1>
            IBVAP Command &amp; Control
            <span className="header-title-badge">STATION 01</span>
          </h1>
          <div className="header-subtitle">
            Intelligent Border Video Analytics Platform
          </div>
        </div>
      </div>

      {/* Right Operational Status & Telemetry Indicators (Cohesive Command Cluster) */}
      <div className="header-right">
        {/* Active Cameras Count */}
        <div className="header-telemetry-item" title="Configured surveillance cameras">
          <Camera size={13} color="var(--accent-cyan)" />
          <span>CAMERAS {formattedCameraCount}</span>
        </div>

        <span style={{ color: 'var(--border-medium)' }}>│</span>

        {/* Real-time WebSocket Telemetry Indicator */}
        <div className="header-telemetry-item" title={`WebSocket telemetry stream: ${wsStatus}`}>
          {isWsConnected ? (
            <Wifi size={13} color="var(--status-online)" />
          ) : (
            <WifiOff size={13} color="var(--severity-warning)" />
          )}
          <span style={{ color: isWsConnected ? 'var(--status-online)' : 'var(--severity-warning)' }}>
            {isWsConnected ? 'WS CONNECTED' : `WS ${wsStatus}`}
          </span>
        </div>

        <span style={{ color: 'var(--border-medium)' }}>│</span>

        {/* Live Backend System Status */}
        <StatusIndicator status={systemStatus} />

        <span style={{ color: 'var(--border-medium)' }}>│</span>

        {/* Live UTC Master Clock */}
        <div className="header-clock" aria-label="System UTC Time">
          <Clock size={12} color="var(--text-muted)" />
          <span>{currentTime || 'SYNCING TIME...'}</span>
        </div>
      </div>
    </header>
  );
};
