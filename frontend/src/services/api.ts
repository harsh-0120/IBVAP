/**
 * IBVAP Centralized REST API Service
 * Interacts with FastAPI backend endpoints.
 */

import {
  AnalyticsResponse,
  CameraResponse,
  HealthResponse,
  IncidentResponse,
  StatsResponse,
  VideoUploadResponse,
  ZoneResponse,
} from '../types/api';

// Configurable base URL with fallback to local FastAPI development server
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

class ApiService {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  /**
   * Health check query
   */
  async getHealth(): Promise<HealthResponse> {
    const res = await fetch(`${this.baseUrl}/api/health`);
    if (!res.ok) {
      throw new Error(`Health check failed with status ${res.status}`);
    }
    return res.json();
  }

  /**
   * System statistics query
   */
  async getStats(): Promise<StatsResponse> {
    const res = await fetch(`${this.baseUrl}/api/stats`);
    if (!res.ok) {
      throw new Error(`Stats fetch failed with status ${res.status}`);
    }
    return res.json();
  }

  /**
   * Surveillance analytics aggregation query
   */
  async getAnalytics(timeRange: string = 'all'): Promise<AnalyticsResponse> {
    const res = await fetch(`${this.baseUrl}/api/analytics?time_range=${encodeURIComponent(timeRange)}`);
    if (!res.ok) {
      throw new Error(`Analytics fetch failed with status ${res.status}`);
    }
    return res.json();
  }

  /**
   * Query recent security incidents
   */
  async getEvents(options: {
    limit?: number;
    eventType?: string;
    cameraId?: string;
  } = {}): Promise<IncidentResponse[]> {
    const query = new URLSearchParams();
    if (options.limit !== undefined) {
      query.set('limit', String(options.limit));
    }
    if (options.eventType) {
      query.set('event_type', options.eventType);
    }
    if (options.cameraId) {
      query.set('camera_id', options.cameraId);
    }

    const qs = query.toString();
    const url = `${this.baseUrl}/api/events${qs ? `?${qs}` : ''}`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`Events fetch failed with status ${res.status}`);
    }
    const data = await res.json();
    if (Array.isArray(data)) {
      return data;
    }
    if (data && Array.isArray(data.incidents)) {
      return data.incidents;
    }
    return [];
  }

  /**
   * List configured surveillance cameras
   */
  async getCameras(): Promise<CameraResponse[]> {
    const res = await fetch(`${this.baseUrl}/api/cameras`);
    if (!res.ok) {
      throw new Error(`Cameras fetch failed with status ${res.status}`);
    }
    return res.json();
  }

  /**
   * List configured spatial boundaries (zones and tripwires)
   */
  async getZones(cameraId?: string): Promise<ZoneResponse> {
    const url = cameraId
      ? `${this.baseUrl}/api/zones?camera_id=${encodeURIComponent(cameraId)}`
      : `${this.baseUrl}/api/zones`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`Zones fetch failed with status ${res.status}`);
    }
    return res.json();
  }

  /**
   * Select active surveillance camera node
   */
  async selectCamera(cameraId: string): Promise<CameraResponse> {
    const res = await fetch(`${this.baseUrl}/api/cameras/${encodeURIComponent(cameraId)}/select`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Failed to select camera ${cameraId}: status ${res.status}`);
    }
    return res.json();
  }

  /**
   * Build authorized URL for downloading forensic snapshot
   */
  getSnapshotUrl(incidentId: number): string {
    return `${this.baseUrl}/api/events/${incidentId}/snapshot`;
  }

  /**
   * Build URL for strictly read-only demo video stream
   */
  getDemoVideoUrl(): string {
    return `${this.baseUrl}/api/video/demo`;
  }

  /**
   * Build URL for real-time annotated surveillance MJPEG stream
   */
  getAnnotatedStreamUrl(): string {
    return `${this.baseUrl}/api/video/annotated`;
  }

  /**
   * Build URL for live AI surveillance stream for a specific camera
   */
  getLiveStreamUrl(cameraId: string): string {
    return `${this.baseUrl}/api/video/live/${encodeURIComponent(cameraId)}`;
  }

  /**
   * Upload video footage to be processed by the surveillance pipeline.
   * Streams upload in chunks and reports progress via XMLHttpRequest.
   */
  uploadVideo(
    file: File,
    cameraName?: string,
    onProgress?: (percent: number) => void
  ): Promise<VideoUploadResponse> {
    return new Promise((resolve, reject) => {
      const formData = new FormData();
      formData.append('file', file);
      if (cameraName && cameraName.trim()) {
        formData.append('name', cameraName.trim());
      }

      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${this.baseUrl}/api/videos/upload`);

      if (xhr.upload && onProgress) {
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable && event.total > 0) {
            const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
            onProgress(percent);
          }
        };
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText) as VideoUploadResponse;
            resolve(data);
          } catch {
            reject(new Error('Invalid response received from server.'));
          }
        } else {
          let errorMsg = `Upload failed with status ${xhr.status}`;
          try {
            const errData = JSON.parse(xhr.responseText);
            if (errData && errData.detail) {
              errorMsg = typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail);
            }
          } catch {
            // response was not JSON
          }
          reject(new Error(errorMsg));
        }
      };

      xhr.onerror = () => {
        reject(new Error('Network error during video upload. Please check connection.'));
      };

      xhr.onabort = () => {
        reject(new Error('Video upload was cancelled.'));
      };

      xhr.send(formData);
    });
  }
}


export const api = new ApiService();
