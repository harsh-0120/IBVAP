import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api, API_BASE_URL } from '../services/api';

describe('ApiService', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('correctly constructs snapshot and demo video URLs', () => {
    expect(api.getSnapshotUrl(42)).toBe(`${API_BASE_URL}/api/events/42/snapshot`);
    expect(api.getDemoVideoUrl()).toBe(`${API_BASE_URL}/api/video/demo`);
  });

  it('fetches health status successfully', async () => {
    const mockHealth = { status: 'online', service: 'IBVAP', version: '0.1.0' };
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockHealth,
    } as Response);

    const result = await api.getHealth();
    expect(result.status).toBe('online');
    expect(global.fetch).toHaveBeenCalledWith(`${API_BASE_URL}/api/health`);
  });

  it('fetches stats and correctly formats query params for events', async () => {
    const mockEvents = [{ id: 1, event_type: 'ZONE_INTRUSION' }];
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockEvents,
    } as Response);

    const result = await api.getEvents({ limit: 5, eventType: 'ZONE_INTRUSION' });
    expect(result).toHaveLength(1);
    expect(global.fetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/api/events?limit=5&event_type=ZONE_INTRUSION`
    );
  });

  it('unpacks paginated incidents response correctly', async () => {
    const mockPaginated = {
      total: 15,
      limit: 20,
      offset: 0,
      incidents: [
        { id: 1, event_type: 'ZONE_INTRUSION' },
        { id: 2, event_type: 'TRIPWIRE_CROSSING' },
      ],
    };
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockPaginated,
    } as Response);

    const result = await api.getEvents();
    expect(result).toHaveLength(2);
    expect(result[0].id).toBe(1);
  });
});
