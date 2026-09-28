import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Overview } from '../pages/Overview';

describe('Overview Page', () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/health')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: 'online', service: 'IBVAP', version: '0.1.0' }),
        } as Response);
      }
      if (url.includes('/api/stats')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            total_incidents: 15,
            zone_intrusions: 9,
            tripwire_crossings: 6,
            active_camera_count: 1,
            camera_id: 'CAM-01',
          }),
        } as Response);
      }
      if (url.includes('/api/events')) {
        return Promise.resolve({
          ok: true,
          json: async () => [
            {
              id: 1,
              timestamp: 1725624000,
              iso_timestamp: '2026-09-06T12:00:00.000Z',
              camera_id: 'CAM-01',
              event_type: 'ZONE_INTRUSION',
              track_id: 10,
              object_type: 'person',
              zone_id: 'Z1',
              zone_name: 'Bunker Alpha',
              direction: null,
              confidence: 0.92,
              frame_index: 40,
              feet_point: [500, 300],
              snapshot_path: 'snap.jpg',
            },
          ],
        } as Response);
      }
      if (url.includes('/api/cameras')) {
        return Promise.resolve({
          ok: true,
          json: async () => [{ camera_id: 'CAM-01', source_type: 'file', status: 'online', details: {} }],
        } as Response);
      }
      if (url.includes('/api/zones')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            zones: [{ id: 'Z1', name: 'Restricted Sector Alpha', points: [] }],
            tripwires: [{ id: 'TW1', name: 'Perimeter Demarcation', start: [0, 0], end: [1, 1] }],
          }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
    });
  });

  it('renders operational stats cards populated from backend responses', async () => {
    render(<Overview />);

    await waitFor(() => {
      expect(screen.getByText('Total Incidents')).toBeInTheDocument();
      expect(screen.getByText('15')).toBeInTheDocument();
      expect(screen.getByText('Zone Intrusions')).toBeInTheDocument();
      expect(screen.getByText('9')).toBeInTheDocument();
      expect(screen.getByText('Tripwire Crossings')).toBeInTheDocument();
      expect(screen.getByText('6')).toBeInTheDocument();
      expect(screen.getByText('ONLINE')).toBeInTheDocument();
    });

    // Check camera panel
    expect(screen.getByText('LIVE SURVEILLANCE', { exact: false })).toBeInTheDocument();

    // Check zones summary
    expect(screen.getByText('RESTRICTED VIRTUAL FENCES')).toBeInTheDocument();
    expect(screen.getByText('DIRECTIONAL TRIPWIRES')).toBeInTheDocument();
  });

  it('displays the offline warning banner when health check fails initially', async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/health')) {
        return Promise.reject(new Error('Failed to fetch'));
      }
      if (url.includes('/api/cameras')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response);
      }
      if (url.includes('/api/zones')) {
        return Promise.resolve({ ok: true, json: async () => ({ zones: [], tripwires: [] }) } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
    });

    render(<Overview />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText(/SURVEILLANCE BACKEND OFFLINE/i)).toBeInTheDocument();
      expect(screen.getByText('Retry Now')).toBeInTheDocument();
      expect(screen.getAllByText('OFFLINE').length).toBeGreaterThan(0);
    });
  });

  it('recovers from offline state and clears warning banner when health check recovers', async () => {
    let callCount = 0;
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/health')) {
        callCount++;
        if (callCount === 1) {
          return Promise.reject(new Error('Failed to fetch'));
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: 'online', service: 'IBVAP', version: '0.1.0' }),
        } as Response);
      }
      if (url.includes('/api/stats')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            total_incidents: 10,
            zone_intrusions: 6,
            tripwire_crossings: 4,
            active_camera_count: 1,
            camera_id: 'CAM-01',
          }),
        } as Response);
      }
      if (url.includes('/api/cameras')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response);
      }
      if (url.includes('/api/zones')) {
        return Promise.resolve({ ok: true, json: async () => ({ zones: [], tripwires: [] }) } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
    });

    render(<Overview />);

    // Initially offline banner is displayed
    await waitFor(() => {
      expect(screen.getByText(/SURVEILLANCE BACKEND OFFLINE/i)).toBeInTheDocument();
    });

    // User clicks "Retry Now" to recover
    const retryBtn = screen.getByText('Retry Now');
    retryBtn.click();

    // After retry, banner is cleared and status is ONLINE
    await waitFor(() => {
      expect(screen.queryByText(/SURVEILLANCE BACKEND OFFLINE/i)).not.toBeInTheDocument();
      expect(screen.getByText('ONLINE')).toBeInTheDocument();
    });
  });
});
