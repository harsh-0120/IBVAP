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

  it('uploads video footage successfully via XMLHttpRequest', async () => {
    const mockFile = new File(['fake-video-content'], 'patrol.mp4', { type: 'video/mp4' });
    const mockResponse = {
      camera_id: 'CAM-UPLOAD-TEST',
      name: 'Patrol Cam',
      file_path: 'data/uploads/patrol.mp4',
      resolution: '1280x720',
      source_fps: 25.0,
      frame_count: 300,
      duration_sec: 12.0,
      file_size_bytes: 18,
      message: 'Video uploaded and registered successfully.',
    };

    let progressCalled = false;
    const progressCallback = (pct: number) => {
      progressCalled = true;
      expect(pct).toBeGreaterThanOrEqual(0);
    };

    const mockXhr: Record<string, any> = {
      open: vi.fn(),
      send: vi.fn(function (this: any) {
        if (this.upload && this.upload.onprogress) {
          this.upload.onprogress({ lengthComputable: true, loaded: 50, total: 100 });
        }
        this.status = 200;
        this.responseText = JSON.stringify(mockResponse);
        if (this.onload) this.onload();
      }),
      upload: {
        onprogress: null as any,
      },
      status: 200,
      responseText: '',
      onload: null as any,
      onerror: null as any,
      onabort: null as any,
    };

    const originalXHR = global.XMLHttpRequest;
    (global as any).XMLHttpRequest = vi.fn(() => mockXhr);

    try {
      const res = await api.uploadVideo(mockFile, 'Patrol Cam', progressCallback);
      expect(res.camera_id).toBe('CAM-UPLOAD-TEST');
      expect(res.resolution).toBe('1280x720');
      expect(progressCalled).toBe(true);
      expect(mockXhr.open).toHaveBeenCalledWith('POST', `${API_BASE_URL}/api/videos/upload`);
    } finally {
      global.XMLHttpRequest = originalXHR;
    }
  });

  it('handles video upload failure with server error detail', async () => {
    const mockFile = new File(['fake-video-content'], 'invalid.mp4', { type: 'video/mp4' });

    const mockXhr: Record<string, any> = {
      open: vi.fn(),
      send: vi.fn(function (this: any) {
        this.status = 400;
        this.responseText = JSON.stringify({ detail: 'Invalid video file header' });
        if (this.onload) this.onload();
      }),
      upload: {},
      status: 400,
      responseText: '',
      onload: null as any,
      onerror: null as any,
      onabort: null as any,
    };

    const originalXHR = global.XMLHttpRequest;
    (global as any).XMLHttpRequest = vi.fn(() => mockXhr);

    try {
      await expect(api.uploadVideo(mockFile)).rejects.toThrow('Invalid video file header');
    } finally {
      global.XMLHttpRequest = originalXHR;
    }
  });
});

