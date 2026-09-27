import React, { useEffect, useState, useCallback } from 'react';
import {
  ShieldAlert,
  ArrowRightLeft,
  Camera,
  Activity,
  AlertCircle,
} from 'lucide-react';
import { api } from '../services/api';
import { wsService } from '../services/websocket';
import {
  AnalyticsResponse,
  CameraResponse,
  HealthResponse,
  IncidentResponse,
  StatsResponse,
  VideoUploadResponse,
  ZoneResponse,
} from '../types/api';

import { WsConnectionStatus, WsIncidentEvent, WsTelemetryMessage } from '../types/events';
import { StatCard } from '../components/StatCard';
import { CameraPanel } from '../components/CameraPanel';
import { IncidentList } from '../components/IncidentList';
import { ZoneSummary } from '../components/ZoneSummary';
import { AnalyticsDashboardSection } from '../components/AnalyticsCharts';

export const Overview: React.FC = () => {
  // State
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [timeRange, setTimeRange] = useState<'24h' | '7d' | 'all'>('24h');
  const [analyticsLoading, setAnalyticsLoading] = useState<boolean>(true);
  const [incidents, setIncidents] = useState<IncidentResponse[]>([]);
  const [cameras, setCameras] = useState<CameraResponse[]>([]);
  const [zones, setZones] = useState<ZoneResponse | null>(null);
  const [selectedCameraId, setSelectedCameraId] = useState<string>('CAM-01');
  const [telemetry, setTelemetry] = useState<WsTelemetryMessage | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [wsStatus, setWsStatus] = useState<WsConnectionStatus>('DISCONNECTED');

  // Analytics Query Callback
  const loadAnalytics = useCallback(async (range: '24h' | '7d' | 'all') => {
    try {
      const data = await api.getAnalytics(range);
      if (data && data.total_incidents !== undefined) {
        setAnalytics(data);
      }
    } catch (err) {
      console.warn('Analytics fetch notice:', err);
    } finally {
      setAnalyticsLoading(false);
    }
  }, []);

  const handleTimeRangeChange = (newRange: '24h' | '7d' | 'all') => {
    setTimeRange(newRange);
    setAnalyticsLoading(true);
    loadAnalytics(newRange);
  };

  // Initial Data Fetch
  const loadData = useCallback(async () => {
    try {
      const [healthData, statsData, eventsData, camerasData, zonesData, analyticsData] =
        await Promise.allSettled([
          api.getHealth(),
          api.getStats(),
          api.getEvents({ limit: 20 }),
          api.getCameras(),
          api.getZones(),
          api.getAnalytics(timeRange),
        ]);

      if (healthData.status === 'fulfilled') {
        setHealth(healthData.value);
        setError(null);
      } else {
        setHealth({ status: 'offline', service: 'IBVAP', version: '0.1.0' });
        setError('Backend API unreachable');
      }

      if (statsData.status === 'fulfilled') {
        setStats(statsData.value);
      }

      if (eventsData.status === 'fulfilled') {
        const evList = Array.isArray(eventsData.value)
          ? eventsData.value
          : (eventsData.value as unknown as { incidents?: IncidentResponse[] })?.incidents || [];
        setIncidents(evList);
      }

      if (camerasData.status === 'fulfilled') {
        setCameras(camerasData.value);
        if (camerasData.value.length > 0) {
          setSelectedCameraId((prev) => prev || camerasData.value[0].camera_id);
        }
      }

      if (zonesData.status === 'fulfilled') {
        setZones(zonesData.value);
      }

      if (analyticsData.status === 'fulfilled') {
        setAnalytics(analyticsData.value);
        setAnalyticsLoading(false);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to connect to surveillance backend');
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    loadData();

    // Polling backup for statistics/health every 12 seconds
    const interval = setInterval(() => {
      api.getHealth().then(setHealth).catch(() => setHealth({ status: 'offline', service: 'IBVAP', version: '0.1.0' }));
      api.getStats().then(setStats).catch(() => {});
      api.getCameras().then(setCameras).catch(() => {});
      api.getAnalytics(timeRange).then(setAnalytics).catch(() => {});
    }, 12000);

    return () => clearInterval(interval);
  }, [loadData, timeRange]);

  // Handle camera selection change
  const handleSelectCamera = useCallback(async (cameraId: string) => {
    setSelectedCameraId(cameraId);
    try {
      await api.selectCamera(cameraId);
      // Fetch spatial boundaries calibrated for this camera
      const zonesData = await api.getZones(cameraId);
      setZones(zonesData);
    } catch (err) {
      console.warn(`Camera switch notice for ${cameraId}:`, err);
    }
  }, []);

  // Handle newly uploaded and registered surveillance footage
  const handleUploadSuccess = useCallback(async (newCam: VideoUploadResponse) => {
    try {
      const refreshedCameras = await api.getCameras();
      setCameras(refreshedCameras);
      await handleSelectCamera(newCam.camera_id);
    } catch (err) {
      console.warn('Camera refresh after upload notice:', err);
    }
  }, [handleSelectCamera]);


  // WebSocket Live Events & Telemetry
  useEffect(() => {
    wsService.connect();

    const unsubscribeStatus = wsService.onStatusChange((status) => {
      setWsStatus(status);
    });

    // Real-time confirmed incidents
    const unsubscribeIncidents = wsService.onIncident((event: WsIncidentEvent) => {
      setIncidents((prev) => {
        if (prev.some((item) => item.id === event.id)) {
          return prev;
        }
        return [event, ...prev];
      });

      // Update local stat counts dynamically
      setStats((prev) => {
        if (!prev) return prev;
        const isZone = event.event_type === 'ZONE_INTRUSION';
        return {
          ...prev,
          total_incidents: prev.total_incidents + 1,
          zone_intrusions: isZone ? prev.zone_intrusions + 1 : prev.zone_intrusions,
          tripwire_crossings: !isZone ? prev.tripwire_crossings + 1 : prev.tripwire_crossings,
        };
      });

      // Update real analytics charts
      loadAnalytics(timeRange);
    });

    // Real-time AI surveillance telemetry
    const unsubscribeTelemetry = wsService.onTelemetry((telemetryData: WsTelemetryMessage) => {
      setTelemetry(telemetryData);

      // Keep stats synchronised with backend telemetry
      setStats({
        total_incidents: telemetryData.total_incidents,
        zone_intrusions: telemetryData.zone_intrusions,
        tripwire_crossings: telemetryData.tripwire_crossings,
        active_camera_count: 1,
        camera_id: telemetryData.camera_id,
      });
    });

    return () => {
      unsubscribeStatus();
      unsubscribeIncidents();
      unsubscribeTelemetry();
      wsService.disconnect();
    };
  }, []);

  const systemStatus = health?.status || 'offline';
  const currentCam = cameras.find((c) => c.camera_id === selectedCameraId) ||
    cameras[0] || { camera_id: 'CAM-01', source_type: 'file', status: 'online' };

  return (
    <div className="content-area">
      {/* Backend Offline Warning Banner */}
      {error && (
        <div
          style={{
            background: 'var(--severity-critical-bg)',
            border: '1px solid var(--severity-critical-border)',
            padding: '8px 14px',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            color: 'var(--severity-critical)',
            fontSize: '12px',
          }}
          role="alert"
        >
          <AlertCircle size={14} />
          <span>SURVEILLANCE BACKEND OFFLINE — Live connection to FastAPI server unavailable. Retrying...</span>
        </div>
      )}

      {/* Row 1: Operational Telemetry Strip (Unified Metric Bar) */}
      <section className="telemetry-bar stats-grid" aria-label="System Metrics Summary">
        <StatCard
          label="Total Incidents"
          value={stats?.total_incidents ?? 'N/A'}
          subtext={`CAM: ${selectedCameraId}`}
          icon={ShieldAlert}
          variant="critical"
          loading={loading}
        />
        <StatCard
          label="Zone Intrusions"
          value={stats?.zone_intrusions ?? 'N/A'}
          subtext="RESTRICTED SECTORS"
          icon={ShieldAlert}
          variant="critical"
          loading={loading}
        />
        <StatCard
          label="Tripwire Crossings"
          value={stats?.tripwire_crossings ?? 'N/A'}
          subtext="PERIMETER BOUNDARIES"
          icon={ArrowRightLeft}
          variant="warning"
          loading={loading}
        />
        <StatCard
          label="Active Cameras"
          value={stats?.active_camera_count ?? 1}
          subtext={`ACTIVE: ${selectedCameraId}`}
          icon={Camera}
          variant="online"
          loading={loading}
        />
        <StatCard
          label="System Status"
          value={systemStatus.toUpperCase()}
          subtext={
            telemetry?.processing_fps
              ? `AI: ${telemetry.processing_fps.toFixed(1)} FPS • ${wsStatus}`
              : `TELEMETRY: ${wsStatus}`
          }
          icon={Activity}
          variant={systemStatus.toLowerCase() === 'online' ? 'online' : 'default'}
          loading={loading}
        />
      </section>

      {/* Row 2: Main Operational Grid (70% Surveillance / 30% Incident Feed) */}
      <div className="dashboard-main-grid">
        {/* Left Column: Video Feed & Configured Boundaries */}
        <div className="surveillance-workspace-col">
          <CameraPanel
            cameras={cameras}
            selectedCameraId={selectedCameraId}
            onSelectCamera={handleSelectCamera}
            onUploadSuccess={handleUploadSuccess}
            telemetry={telemetry}
            isOnline={currentCam.status === 'online' && systemStatus === 'online'}
          />


          <ZoneSummary zonesData={zones} loading={loading} incidents={incidents} />
        </div>

        {/* Right Column: Real-time Incident Feed */}
        <div style={{ minWidth: 0, height: '100%', overflow: 'hidden' }}>
          <IncidentList
            incidents={incidents}
            loading={loading}
            totalCount={stats?.total_incidents}
          />
        </div>
      </div>

      {/* Row 3: Real Surveillance Analytics & SVG Charts */}
      <AnalyticsDashboardSection
        analytics={analytics}
        timeRange={timeRange}
        onTimeRangeChange={handleTimeRangeChange}
        loading={analyticsLoading}
      />
    </div>
  );
};
