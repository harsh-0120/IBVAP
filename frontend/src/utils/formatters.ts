/**
 * Formatting and display utilities for surveillance telemetry
 */

export function formatIncidentTime(
  timestamp?: number,
  isoTimestamp?: string,
  includeDate: boolean = false
): string {
  if (timestamp) {
    const d = new Date(timestamp * 1000);
    if (!isNaN(d.getTime())) {
      if (includeDate) {
        return d.toLocaleString('en-GB', {
          day: '2-digit',
          month: 'short',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        });
      }
      return d.toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      });
    }
  }

  if (isoTimestamp) {
    const d = new Date(isoTimestamp);
    if (!isNaN(d.getTime())) {
      if (includeDate) {
        return d.toLocaleString('en-GB', {
          day: '2-digit',
          month: 'short',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        });
      }
      return d.toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      });
    }
  }

  return 'N/A';
}

export function formatConfidence(conf: number | null | undefined): string {
  if (conf === null || conf === undefined || isNaN(conf)) {
    return 'N/A';
  }
  return `${(conf * 100).toFixed(1)}%`;
}

export function formatCoords(point?: [number, number]): string {
  if (!point || point.length < 2) {
    return 'N/A';
  }
  return `X: ${point[0].toFixed(1)}, Y: ${point[1].toFixed(1)}`;
}

export function formatEventTypeLabel(eventType: string): string {
  switch (eventType) {
    case 'ZONE_INTRUSION':
      return 'ZONE INTRUSION';
    case 'TRIPWIRE_CROSSING':
      return 'TRIPWIRE CROSSING';
    default:
      return eventType.replace(/_/g, ' ').toUpperCase();
  }
}
