import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { CameraPanel } from '../components/CameraPanel';
import { CameraResponse } from '../types/api';
import { WsTelemetryMessage } from '../types/events';

describe('CameraPanel Component', () => {
  const mockCameras: CameraResponse[] = [
    {
      camera_id: 'CAM-01',
      name: 'Border Perimeter',
      source_type: 'file',
      status: 'online',
      operational_status: 'ONLINE / PROCESSING',
      resolution: '1280x720',
      source_fps: 25.0,
      details: {},
    },
    {
      camera_id: 'CAM-02',
      name: 'Highway Surveillance',
      source_type: 'file',
      status: 'online',
      operational_status: 'READY',
      resolution: '3840x2160',
      source_fps: 30.0,
      details: {},
    },
    {
      camera_id: 'CAM-03',
      name: 'Overhead Traffic',
      source_type: 'file',
      status: 'online',
      operational_status: 'READY',
      resolution: '2160x3840',
      source_fps: 60.0,
      details: {},
    },
  ];

  const mockTelemetry: WsTelemetryMessage = {
    message_type: 'TELEMETRY',
    camera_id: 'CAM-01',
    camera_name: 'Border Perimeter',
    camera_status: 'ONLINE / PROCESSING',
    processing_fps: 10.4,
    source_fps: 60.0,
    active_tracks: 12,
    persons: 3,
    vehicles: 9,
    cars: 5,
    motorcycles: 3,
    buses: 1,
    trucks: 0,
    total_incidents: 4,
    zone_intrusions: 2,
    tripwire_crossings: 2,
    loop_count: 1,
  };

  it('renders all three demo cameras in selector tabs', () => {
    render(
      <CameraPanel
        cameras={mockCameras}
        selectedCameraId="CAM-01"
      />
    );

    expect(screen.getAllByText('CAM-01').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('CAM-02')).toBeInTheDocument();
    expect(screen.getByText('CAM-03')).toBeInTheDocument();
    expect(screen.getByText('LIVE SURVEILLANCE')).toBeInTheDocument();
  });

  it('calls onSelectCamera when a camera tab is clicked', () => {
    const handleSelectCamera = vi.fn();
    render(
      <CameraPanel
        cameras={mockCameras}
        selectedCameraId="CAM-01"
        onSelectCamera={handleSelectCamera}
      />
    );

    const cam2Btn = screen.getByRole('tab', { name: /CAM-02/i });
    fireEvent.click(cam2Btn);
    expect(handleSelectCamera).toHaveBeenCalledWith('CAM-02');
  });

  it('displays real-time telemetry metrics and honest dual FPS', () => {
    render(
      <CameraPanel
        cameras={mockCameras}
        selectedCameraId="CAM-01"
        telemetry={mockTelemetry}
      />
    );

    // Source vs processing FPS
    expect(screen.getByText(/60 FPS/i)).toBeInTheDocument();
    expect(screen.getByText(/10.4 FPS/i)).toBeInTheDocument();

    // Persons, vehicles, tracks count
    expect(screen.getByText('12')).toBeInTheDocument(); // active tracks
    expect(screen.getByText('3')).toBeInTheDocument(); // persons
    expect(screen.getByText('9')).toBeInTheDocument(); // vehicles
    expect(screen.getByText(/Car: 5/i)).toBeInTheDocument();
    expect(screen.getByText(/Moto: 3/i)).toBeInTheDocument();
  });

  it('renders upload footage button and opens upload modal upon click', () => {
    render(
      <CameraPanel
        cameras={mockCameras}
        selectedCameraId="CAM-01"
      />
    );

    const uploadBtn = screen.getByRole('button', { name: /UPLOAD FOOTAGE/i });
    expect(uploadBtn).toBeInTheDocument();

    fireEvent.click(uploadBtn);
    expect(screen.getByText(/INGEST RECORDED FOOTAGE/i)).toBeInTheDocument();
  });

  it('renders uploaded camera sources in selector tabs and allows selection', () => {
    const handleSelectCamera = vi.fn();
    const camerasWithUploaded: CameraResponse[] = [
      ...mockCameras,
      {
        camera_id: 'CAM-UPLOAD-XYZ',
        name: 'Sector 5 Boundary',
        source_type: 'file',
        status: 'online',
        operational_status: 'READY',
        resolution: '1920x1080',
        source_fps: 30.0,
      },
    ];

    render(
      <CameraPanel
        cameras={camerasWithUploaded}
        selectedCameraId="CAM-01"
        onSelectCamera={handleSelectCamera}
      />
    );

    const uploadedTab = screen.getByRole('tab', { name: /CAM-UPLOAD-XYZ/i });
    expect(uploadedTab).toBeInTheDocument();

    fireEvent.click(uploadedTab);
    expect(handleSelectCamera).toHaveBeenCalledWith('CAM-UPLOAD-XYZ');
  });
});

