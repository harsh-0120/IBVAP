/**
 * IBVAP API Data Contracts
 * Corresponding strictly to FastAPI server Pydantic schemas.
 */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  timestamp?: string;
  database?: string;
  active_camera?: boolean;
}

export interface StatsResponse {
  total_incidents: number;
  zone_intrusions: number;
  tripwire_crossings: number;
  active_camera_count: number;
  camera_id: string;
}

export interface IncidentResponse {
  id: number;
  timestamp: number;
  iso_timestamp: string;
  camera_id: string;
  event_type: 'ZONE_INTRUSION' | 'TRIPWIRE_CROSSING' | string;
  track_id: number;
  object_type: string;
  zone_id: string;
  zone_name: string;
  direction: 'LEFT_TO_RIGHT' | 'RIGHT_TO_LEFT' | null;
  confidence: number | null;
  frame_index: number;
  feet_point: [number, number];
  snapshot_path: string;
}

export interface IncidentListResponse {
  total: number;
  limit: number;
  offset: number;
  incidents: IncidentResponse[];
}

export interface CameraResponse {
  camera_id: string;
  name?: string;
  source_type: string;
  status: 'online' | 'offline' | 'ready' | string;
  operational_status?: string;
  resolution?: string;
  source_fps?: number;
  processing_fps?: number;
  details?: {
    name?: string;
    resolution?: string;
    source_fps?: number;
    aspect_ratio?: string;
    operational_status?: string;
    source?: string;
    loop?: boolean;
    buffer_size?: number;
    [key: string]: unknown;
  };
}

export interface PolygonZoneSchema {
  id: string;
  name: string;
  type?: string;
  points: [number, number][];
}

export interface TripwireSchema {
  id: string;
  name: string;
  type?: string;
  start: [number, number];
  end: [number, number];
}

export interface ZoneResponse {
  zones: PolygonZoneSchema[];
  tripwires: TripwireSchema[];
}
