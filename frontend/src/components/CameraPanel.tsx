import React, { useRef, useState, useEffect } from 'react';
import { Play, Pause, Maximize2, Layers, Video, RefreshCw, AlertTriangle, ShieldCheck, Upload } from 'lucide-react';
import { api } from '../services/api';
import { CameraResponse, VideoUploadResponse } from '../types/api';
import { WsTelemetryMessage } from '../types/events';
import { VideoUploadModal } from './VideoUploadModal';

interface CameraPanelProps {
  cameras?: CameraResponse[];
  selectedCameraId?: string;
  onSelectCamera?: (cameraId: string) => void;
  onUploadSuccess?: (uploadedCamera: VideoUploadResponse) => void;
  telemetry?: WsTelemetryMessage | null;
  cameraId?: string;
  sourceType?: string;
  isOnline?: boolean;
}


const DEFAULT_DEMO_CAMERAS: CameraResponse[] = [
  {
    camera_id: 'CAM-01',
    name: 'Border Perimeter',
    source_type: 'file',
    status: 'online',
    operational_status: 'ONLINE / PROCESSING',
    resolution: '1280x720',
    source_fps: 25.0,
    details: { name: 'Border Perimeter', resolution: '1280x720', source_fps: 25.0 },
  },
  {
    camera_id: 'CAM-02',
    name: 'Highway Surveillance',
    source_type: 'file',
    status: 'online',
    operational_status: 'READY',
    resolution: '3840x2160',
    source_fps: 30.0,
    details: { name: 'Highway Surveillance', resolution: '3840x2160', source_fps: 30.0 },
  },
  {
    camera_id: 'CAM-03',
    name: 'Overhead Traffic',
    source_type: 'file',
    status: 'online',
    operational_status: 'READY',
    resolution: '2160x3840',
    source_fps: 60.0,
    details: { name: 'Overhead Traffic', resolution: '2160x3840', source_fps: 60.0 },
  },
];

export const CameraPanel: React.FC<CameraPanelProps> = ({
  cameras = DEFAULT_DEMO_CAMERAS,
  selectedCameraId = 'CAM-01',
  onSelectCamera,
  onUploadSuccess,
  telemetry,
  isOnline = true,
}) => {
  const [viewMode, setViewMode] = useState<'annotated' | 'raw'>('annotated');
  const [streamError, setStreamError] = useState<boolean>(false);
  const [isSwitching, setIsSwitching] = useState<boolean>(false);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState<boolean>(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);

  const handleUploadSuccess = (uploadedCam: VideoUploadResponse) => {
    setIsUploadModalOpen(false);
    if (onUploadSuccess) {
      onUploadSuccess(uploadedCam);
    }
    if (onSelectCamera) {
      onSelectCamera(uploadedCam.camera_id);
    }
  };


  const activeCamId = selectedCameraId || 'CAM-01';
  const currentCam = cameras.find((c) => c.camera_id === activeCamId) || cameras[0] || DEFAULT_DEMO_CAMERAS[0];

  const rawVideoUrl = api.getDemoVideoUrl();
  const liveStreamUrl = api.getLiveStreamUrl(activeCamId);

  // Handle switching transition
  useEffect(() => {
    setIsSwitching(true);
    setStreamError(false);
    const timer = setTimeout(() => setIsSwitching(false), 250);
    return () => clearTimeout(timer);
  }, [activeCamId]);

  const handleSelectMode = (mode: 'annotated' | 'raw') => {
    if (mode === 'annotated') {
      setStreamError(false);
    }
    setViewMode(mode);
  };

  const handleCameraChange = (camId: string) => {
    if (camId === activeCamId) return;
    if (onSelectCamera) {
      onSelectCamera(camId);
    }
  };

  const togglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      videoRef.current.play();
      setIsPlaying(true);
    }
  };

  const handleFullscreen = () => {
    if (!containerRef.current) return;
    if (containerRef.current.requestFullscreen) {
      containerRef.current.requestFullscreen();
    }
  };

  const handleStreamError = () => {
    setStreamError(true);
  };

  const handleRetryStream = () => {
    setStreamError(false);
    setIsSwitching(true);
    setTimeout(() => setIsSwitching(false), 200);
  };

  // Honest source FPS vs AI processing FPS
  const displaySourceFps = telemetry?.source_fps ?? currentCam?.source_fps ?? 60.0;
  const displayProcessingFps = telemetry?.processing_fps
    ? telemetry.processing_fps.toFixed(1)
    : currentCam?.processing_fps
    ? currentCam.processing_fps.toFixed(1)
    : '...';

  return (
    <section className="camera-panel" aria-label="Live Surveillance Viewport" ref={containerRef}>
      {/* Surveillance Camera Node Header & Camera Selector */}
      <div className="camera-panel-header" style={{ flexWrap: 'wrap', gap: '8px' }}>
        <div className="camera-header-left" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span className="camera-title-text" style={{ letterSpacing: '0.08em' }}>LIVE SURVEILLANCE</span>

          {/* Camera Selection Switcher */}
          <div
            className="camera-selector-group"
            style={{
              display: 'inline-flex',
              background: 'var(--bg-secondary)',
              borderRadius: 'var(--radius-sm)',
              padding: '2px',
              border: '1px solid var(--border-medium)',
              gap: '2px',
            }}
            role="tablist"
            aria-label="Surveillance Camera Selection"
          >
            {cameras.map((cam) => {
              const isSelected = cam.camera_id === activeCamId;
              const opStatus = isSelected ? 'ONLINE / PROCESSING' : cam.operational_status || 'READY';
              return (
                <button
                  key={cam.camera_id}
                  type="button"
                  role="tab"
                  aria-selected={isSelected}
                  className={`camera-btn mono ${isSelected ? 'active' : ''}`}
                  onClick={() => handleCameraChange(cam.camera_id)}
                  style={{
                    padding: '4px 10px',
                    fontSize: '11px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    background: isSelected ? 'var(--accent-blue-dim)' : 'transparent',
                    borderColor: isSelected ? 'var(--accent-blue)' : 'transparent',
                    color: isSelected ? '#fff' : 'var(--text-secondary)',
                  }}
                  title={`${cam.camera_id}: ${cam.name || 'CCTV Feed'} (${opStatus})`}
                >
                  <span
                    className={`status-dot ${isSelected ? 'status-dot-pulse' : ''}`}
                    style={{
                      backgroundColor: isSelected
                        ? 'var(--status-online)'
                        : cam.status === 'offline'
                        ? 'var(--status-offline)'
                        : 'var(--text-dim)',
                    }}
                  />
                  <span style={{ fontWeight: isSelected ? 700 : 500 }}>{cam.camera_id}</span>
                  <span style={{ opacity: 0.75, fontSize: '10px' }}>
                    {cam.name ? `— ${cam.name}` : ''}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Ingest Video / Add Camera Action */}
          <button
            type="button"
            className="camera-btn mono"
            onClick={() => setIsUploadModalOpen(true)}
            title="Upload recorded video to ingest into live surveillance pipeline"
            style={{
              padding: '4px 10px',
              fontSize: '11px',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              borderColor: 'var(--accent-cyan-border)',
              color: 'var(--accent-cyan)',
              background: 'var(--accent-cyan-dim)',
            }}
          >
            <Upload size={12} />
            <span>UPLOAD FOOTAGE</span>
          </button>

          <span className="camera-live-badge">

            <span
              className="status-dot status-dot-pulse"
              style={{ backgroundColor: isOnline ? 'var(--status-online)' : 'var(--text-muted)' }}
            />
            {isOnline ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>

        {/* Action Controls */}
        <div className="camera-controls-group">
          {/* AI Overlay Mode */}
          <button
            type="button"
            className={`camera-btn mono ${viewMode === 'annotated' && !streamError ? 'active' : ''}`}
            onClick={() => handleSelectMode('annotated')}
            title="Real-time multi-class detection (person + vehicle) + ByteTrack tracking overlay"
          >
            <Layers size={12} />
            <span>AI OVERLAY</span>
          </button>

          {/* Raw Optical Feed Mode */}
          <button
            type="button"
            className={`camera-btn mono ${viewMode === 'raw' || streamError ? 'active' : ''}`}
            onClick={() => handleSelectMode('raw')}
            title="Raw optical surveillance stream"
          >
            <Video size={12} />
            <span>RAW FEED</span>
          </button>

          {/* Play/Pause Control (Functional for raw video) */}
          {viewMode === 'raw' && (
            <button
              type="button"
              className="camera-btn mono"
              onClick={togglePlay}
              title={isPlaying ? 'Pause Video Stream' : 'Resume Video Stream'}
            >
              {isPlaying ? <Pause size={12} /> : <Play size={12} />}
              <span>{isPlaying ? 'PAUSE' : 'PLAY'}</span>
            </button>
          )}

          {/* Fullscreen Mode */}
          <button
            type="button"
            className="camera-btn mono"
            onClick={handleFullscreen}
            title="Toggle Fullscreen"
            aria-label="Fullscreen"
          >
            <Maximize2 size={12} />
          </button>
        </div>
      </div>

      {/* Primary Video Viewport */}
      <div className="camera-viewport" style={{ position: 'relative', minHeight: '380px', background: '#05070a' }}>
        {isSwitching ? (
          /* Smooth camera stream transition */
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              minHeight: '380px',
              color: 'var(--text-secondary)',
              gap: '12px',
            }}
          >
            <RefreshCw size={24} className="spin-animate" style={{ color: 'var(--accent-cyan)' }} />
            <span className="mono" style={{ fontSize: '12px', letterSpacing: '0.05em' }}>
              CONNECTING TO {activeCamId} SURVEILLANCE PIPELINE...
            </span>
          </div>
        ) : viewMode === 'annotated' && !streamError ? (
          /* MJPEG Real-Time Live Stream from Backend */
          <img
            key={liveStreamUrl}
            src={liveStreamUrl}
            alt={`Live AI surveillance feed for ${activeCamId} with YOLO11n multi-class detection and ByteTrack tracking`}
            className="surveillance-video"
            onError={handleStreamError}
            style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
          />
        ) : streamError ? (
          /* Stream Error Fallback with Retry */
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              minHeight: '380px',
              color: 'var(--severity-critical)',
              gap: '12px',
              padding: '20px',
              textAlign: 'center',
            }}
          >
            <AlertTriangle size={32} />
            <div style={{ fontWeight: 600, fontSize: '13px' }}>STREAM CONNECTION INTERRUPTED</div>
            <div className="mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Could not establish live MJPEG stream for {activeCamId}. Backend worker might be initializing.
            </div>
            <button
              type="button"
              className="camera-btn mono active"
              onClick={handleRetryStream}
              style={{ marginTop: '8px' }}
            >
              <RefreshCw size={12} />
              <span>RECONNECT STREAM</span>
            </button>
          </div>
        ) : (
          /* Raw Video Fallback */
          <video
            ref={videoRef}
            src={rawVideoUrl}
            className="surveillance-video"
            autoPlay
            loop
            muted
            playsInline
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          />
        )}

        {/* Clean Translucent HUD Overlay Top-Left */}
        <div className="camera-hud-top-left">
          <div className="hud-pill mono" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ color: 'var(--accent-cyan)', fontWeight: 700 }}>
              {activeCamId}
            </span>
            <span style={{ color: 'var(--text-dim)' }}>│</span>
            <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
              {currentCam?.name || 'SURVEILLANCE'}
            </span>
            <span style={{ color: 'var(--text-dim)' }}>│</span>
            <span style={{ color: 'var(--text-muted)' }}>
              {currentCam?.resolution || '1080P'}
            </span>
            <span style={{ color: 'var(--text-dim)' }}>│</span>
            <span style={{ color: 'var(--status-online)' }}>
              YOLO11n + ByteTrack
            </span>
          </div>
        </div>

        {/* Clean Translucent HUD Overlay Top-Right */}
        <div className="camera-hud-top-right">
          <div className="hud-pill mono" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              className="status-dot status-dot-pulse"
              style={{ backgroundColor: isOnline ? 'var(--status-online)' : 'var(--text-muted)' }}
            />
            <span style={{ color: 'var(--text-muted)' }}>
              SOURCE:{' '}
              <strong style={{ color: 'var(--text-primary)' }}>{displaySourceFps} FPS</strong>
            </span>
            <span style={{ color: 'var(--text-dim)' }}>│</span>
            <span style={{ color: 'var(--accent-cyan)' }}>
              AI PROC:{' '}
              <strong style={{ color: 'var(--status-online)' }}>{displayProcessingFps} FPS</strong>
            </span>
          </div>
        </div>
      </div>

      {/* Video Telemetry Strip with Real Vehicle & Person Counters */}
      <div className="camera-footer-bar mono" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
            {currentCam?.resolution || '1080P'} CCTV
          </span>
          <span className="footer-sep">│</span>
          <span style={{ color: 'var(--accent-cyan)' }}>
            TRACKS: <strong style={{ color: '#fff' }}>{telemetry?.active_tracks ?? 0}</strong>
          </span>
          <span className="footer-sep">│</span>
          <span style={{ color: 'var(--text-primary)' }}>
            PERSONS: <strong style={{ color: '#fff' }}>{telemetry?.persons ?? 0}</strong>
          </span>
          <span className="footer-sep">│</span>
          <span style={{ color: 'var(--status-online)' }}>
            VEHICLES: <strong style={{ color: '#fff' }}>{telemetry?.vehicles ?? 0}</strong>
          </span>
          {telemetry && (
            <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>
              (Car: {telemetry.cars} • Moto: {telemetry.motorcycles} • Bus: {telemetry.buses} • Truck: {telemetry.trucks})
            </span>
          )}
        </div>

        <div style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          {telemetry?.loop_count !== undefined && telemetry.loop_count > 0 && (
            <>
              <span style={{ color: 'var(--accent-blue)' }}>LOOP: {telemetry.loop_count}</span>
              <span className="footer-sep">│</span>
            </>
          )}
          <span style={{ color: 'var(--status-online)' }}>
            <ShieldCheck size={12} style={{ display: 'inline', marginRight: '4px', verticalAlign: '-1px' }} />
            ACTIVE C2 NODE
          </span>
        </div>
      </div>

      {/* Video Footage Ingestion Modal */}
      <VideoUploadModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onSuccess={handleUploadSuccess}
      />
    </section>
  );
};

