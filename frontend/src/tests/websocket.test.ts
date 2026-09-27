import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { WebSocketService } from '../services/websocket';
import { WsIncidentEvent } from '../types/events';

describe('WebSocketService', () => {
  let mockWsInstance: any;

  beforeEach(() => {
    mockWsInstance = {
      readyState: 1, // OPEN
      send: vi.fn(),
      close: vi.fn(),
      onopen: null,
      onmessage: null,
      onclose: null,
      onerror: null,
    };

    // Mock global WebSocket
    (global as any).WebSocket = vi.fn().mockImplementation(() => mockWsInstance);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('connects and notifies status listeners of connection state', () => {
    const ws = new WebSocketService('ws://127.0.0.1:8000/ws/events');
    const statuses: string[] = [];

    ws.onStatusChange((s) => statuses.push(s));
    ws.connect();

    expect(statuses).toContain('CONNECTING');

    // Simulate open
    mockWsInstance.onopen();
    expect(statuses).toContain('CONNECTED');

    ws.disconnect();
    expect(statuses).toContain('DISCONNECTED');
  });

  it('dispatches parsed incident messages to incident listeners', () => {
    const ws = new WebSocketService('ws://127.0.0.1:8000/ws/events');
    const received: WsIncidentEvent[] = [];

    ws.onIncident((inc) => received.push(inc));
    ws.connect();
    mockWsInstance.onopen();

    const samplePayload: WsIncidentEvent = {
      message_type: 'NEW_INCIDENT',
      id: 99,
      timestamp: 1725624000,
      iso_timestamp: '2026-09-06T12:00:00.000Z',
      camera_id: 'CAM-01',
      event_type: 'ZONE_INTRUSION',
      track_id: 12,
      object_type: 'person',
      zone_id: 'Z1',
      zone_name: 'Zone Alpha',
      direction: null,
      confidence: 0.9,
      frame_index: 33,
      feet_point: [200, 300],
      snapshot_path: 'snap.jpg',
    };

    mockWsInstance.onmessage({ data: JSON.stringify(samplePayload) });

    expect(received).toHaveLength(1);
    expect(received[0].id).toBe(99);
    expect(received[0].event_type).toBe('ZONE_INTRUSION');

    ws.disconnect();
  });

  it('correctly constructs WebSocket URL without duplicate slashes from API_BASE_URL', () => {
    const ws = new WebSocketService();
    expect(ws['url']).toMatch(/^ws:\/\/.*\/ws\/events$/);
    expect(ws['url']).not.toContain('//ws/events');
  });
});

