import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { App } from '../App';

describe('App Shell Component', () => {
  beforeEach(() => {
    // Mock fetch for health and cameras
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/health')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: 'online', service: 'IBVAP', version: '0.1.0' }),
        } as Response);
      }
      if (url.includes('/api/cameras')) {
        return Promise.resolve({
          ok: true,
          json: async () => [{ camera_id: 'CAM-01', source_type: 'file', status: 'online', details: {} }],
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
          json: async () => [],
        } as Response);
      }
      if (url.includes('/api/zones')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ zones: [], tripwires: [] }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
    });
  });

  it('renders application navigation and header', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('IBVAP')).toBeInTheDocument();
      expect(screen.getByText('Overview')).toBeInTheDocument();
      expect(screen.getByText('Live Surveillance')).toBeInTheDocument();
      expect(screen.getByText('Incidents')).toBeInTheDocument();
      expect(screen.getByText('IBVAP Command & Control')).toBeInTheDocument();
    });
  });
});
