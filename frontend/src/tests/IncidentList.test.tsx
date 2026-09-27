import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { IncidentList } from '../components/IncidentList';
import { IncidentResponse } from '../types/api';

describe('IncidentList Component', () => {
  const sampleIncidents: IncidentResponse[] = [
    {
      id: 10,
      timestamp: 1725624000,
      iso_timestamp: '2026-09-06T12:00:00.000Z',
      camera_id: 'CAM-01',
      event_type: 'ZONE_INTRUSION',
      track_id: 11,
      object_type: 'person',
      zone_id: 'zone_alpha',
      zone_name: 'Restricted Sector Alpha',
      direction: null,
      confidence: 0.94,
      frame_index: 45,
      feet_point: [700.0, 350.0],
      snapshot_path: 'data/snapshots/test.jpg',
    },
    {
      id: 11,
      timestamp: 1725624050,
      iso_timestamp: '2026-09-06T12:00:50.000Z',
      camera_id: 'CAM-01',
      event_type: 'TRIPWIRE_CROSSING',
      track_id: 4,
      object_type: 'person',
      zone_id: 'wire_01',
      zone_name: 'Perimeter Demarcation Wire',
      direction: 'RIGHT_TO_LEFT',
      confidence: 0.88,
      frame_index: 70,
      feet_point: [800.0, 360.0],
      snapshot_path: 'data/snapshots/test2.jpg',
    },
  ];

  it('renders list of incidents with severity badges and details', () => {
    render(<IncidentList incidents={sampleIncidents} totalCount={2} />);

    expect(screen.getByText('RECENT INCIDENTS')).toBeInTheDocument();
    expect(screen.getByText('TOTAL: 2')).toBeInTheDocument();
    expect(screen.getByText('ZONE INTRUSION')).toBeInTheDocument();
    expect(screen.getByText('TRIPWIRE CROSSING')).toBeInTheDocument();
    expect(screen.getByText('Track #11')).toBeInTheDocument();
    expect(screen.getByText('Track #4')).toBeInTheDocument();
    expect(screen.getByText('Restricted Sector Alpha')).toBeInTheDocument();
  });

  it('renders empty state when no incidents are present', () => {
    render(<IncidentList incidents={[]} />);

    expect(screen.getByText('NO PERIMETER BREACHES DETECTED')).toBeInTheDocument();
  });
});
