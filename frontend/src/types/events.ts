/**
 * IBVAP Real-time WebSocket Protocol Types
 */

import { IncidentResponse } from './api';

export interface WsHandshakeMessage {
  message_type: 'CONNECTED';
  service: string;
  active_clients: number;
}

export interface WsIncidentEvent extends IncidentResponse {
  message_type: 'NEW_INCIDENT' | string;
  incident_id?: number;
}

export interface WsTelemetryMessage {
  message_type: 'TELEMETRY';
  camera_id: string;
  camera_name: string;
  camera_status: string;
  processing_fps: number;
  source_fps: number;
  active_tracks: number;
  persons: number;
  vehicles: number;
  cars: number;
  motorcycles: number;
  buses: number;
  trucks: number;
  total_incidents: number;
  zone_intrusions: number;
  tripwire_crossings: number;
  loop_count?: number;
}

export type WsServerMessage = WsHandshakeMessage | WsIncidentEvent | WsTelemetryMessage;

export type WsConnectionStatus = 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED' | 'RECONNECTING';

