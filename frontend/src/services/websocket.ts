/**
 * IBVAP Real-time WebSocket Service
 * Connects to /ws/events to receive real-time incident broadcasts.
 */

import { API_BASE_URL } from './api';
import {
  WsConnectionStatus,
  WsIncidentEvent,
  WsServerMessage,
  WsTelemetryMessage,
} from '../types/events';

type IncidentListener = (event: WsIncidentEvent) => void;
type StatusListener = (status: WsConnectionStatus) => void;
type TelemetryListener = (telemetry: WsTelemetryMessage) => void;

export class WebSocketService {
  private url: string;
  private ws: WebSocket | null = null;
  private status: WsConnectionStatus = 'DISCONNECTED';
  private incidentListeners: Set<IncidentListener> = new Set();
  private statusListeners: Set<StatusListener> = new Set();
  private telemetryListeners: Set<TelemetryListener> = new Set();

  private reconnectAttempts = 0;
  private maxReconnectDelay = 10000;
  private reconnectTimeout: number | null = null;
  private pingInterval: number | null = null;
  private intentionallyClosed = false;

  constructor(customUrl?: string) {
    if (customUrl) {
      this.url = customUrl;
    } else {
      const base = API_BASE_URL.replace(/^http/, 'ws');
      this.url = `${base}/ws/events`;
    }
  }

  public getStatus(): WsConnectionStatus {
    return this.status;
  }

  public onIncident(listener: IncidentListener): () => void {
    this.incidentListeners.add(listener);
    return () => this.incidentListeners.delete(listener);
  }

  public onTelemetry(listener: TelemetryListener): () => void {
    this.telemetryListeners.add(listener);
    return () => this.telemetryListeners.delete(listener);
  }

  public onStatusChange(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => this.statusListeners.delete(listener);
  }

  private setStatus(newStatus: WsConnectionStatus) {
    this.status = newStatus;
    this.statusListeners.forEach((fn) => fn(newStatus));
  }

  public connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.intentionallyClosed = false;
    this.setStatus('CONNECTING');

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.setStatus('CONNECTED');
        this.reconnectAttempts = 0;
        this.startHeartbeat();
      };

      this.ws.onmessage = (event: MessageEvent) => {
        if (event.data === 'pong') {
          return;
        }

        try {
          const data: WsServerMessage = JSON.parse(event.data);
          if (data.message_type === 'TELEMETRY') {
            const telemetry = data as WsTelemetryMessage;
            this.telemetryListeners.forEach((fn) => fn(telemetry));
          } else if (data.message_type === 'NEW_INCIDENT' || ('event_type' in data && 'track_id' in data)) {
            const incident = data as WsIncidentEvent;
            this.incidentListeners.forEach((fn) => fn(incident));
          }
        } catch {
          // Ignored non-json frames
        }
      };

      this.ws.onclose = () => {
        this.stopHeartbeat();
        this.setStatus('DISCONNECTED');
        if (!this.intentionallyClosed) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = () => {
        if (this.ws) {
          this.ws.close();
        }
      };
    } catch {
      this.setStatus('DISCONNECTED');
      this.scheduleReconnect();
    }
  }

  public disconnect(): void {
    this.intentionallyClosed = true;
    this.stopHeartbeat();
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.setStatus('DISCONNECTED');
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.pingInterval = window.setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      }
    }, 15000);
  }

  private stopHeartbeat(): void {
    if (this.pingInterval !== null) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimeout !== null || this.intentionallyClosed) {
      return;
    }

    this.setStatus('RECONNECTING');
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    this.reconnectAttempts += 1;

    this.reconnectTimeout = window.setTimeout(() => {
      this.reconnectTimeout = null;
      this.connect();
    }, delay);
  }
}

export const wsService = new WebSocketService();
