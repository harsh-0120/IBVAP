import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  IncidentsOverTimeChart,
  EventTypeBarChart,
  SeverityDonutChart,
  CameraDistributionChart,
  AnalyticsDashboardSection,
} from '../components/AnalyticsCharts';
import { AnalyticsResponse } from '../types/api';

describe('AnalyticsCharts Components', () => {
  const mockAnalytics: AnalyticsResponse = {
    time_range: '24h',
    total_incidents: 42,
    incidents_over_time: [
      {
        time_bucket: '12:00',
        iso_timestamp: '2026-09-27T12:00:00Z',
        timestamp: 1727438400,
        count: 10,
        intrusions: 6,
        tripwires: 4,
      },
      {
        time_bucket: '13:00',
        iso_timestamp: '2026-09-27T13:00:00Z',
        timestamp: 1727442000,
        count: 32,
        intrusions: 20,
        tripwires: 12,
      },
    ],
    incidents_by_type: {
      ZONE_INTRUSION: 26,
      TRIPWIRE_CROSSING: 16,
    },
    incidents_by_camera: {
      'CAM-01': 30,
      'CAM-02': 12,
    },
    incidents_by_severity: {
      critical: 26,
      warning: 16,
    },
    camera_status_distribution: {
      online: 1,
      ready: 2,
    },
    total_cameras: 3,
    online_cameras: 1,
  };

  it('renders IncidentsOverTimeChart with SVG elements', () => {
    const { container } = render(
      <IncidentsOverTimeChart points={mockAnalytics.incidents_over_time} />
    );
    expect(screen.getByText('INCIDENT TEMPORAL VELOCITY')).toBeInTheDocument();
    expect(screen.getByText('All Incidents')).toBeInTheDocument();
    expect(container.querySelector('svg')).toBeInTheDocument();
    expect(container.querySelector('path')).toBeInTheDocument();
  });

  it('renders EventTypeBarChart with correct counts and percentages', () => {
    render(
      <EventTypeBarChart
        typeCounts={mockAnalytics.incidents_by_type}
        totalIncidents={mockAnalytics.total_incidents}
      />
    );
    expect(screen.getByText('CLASSIFICATION BREAKDOWN')).toBeInTheDocument();
    expect(screen.getByText('26')).toBeInTheDocument();
    expect(screen.getByText('16')).toBeInTheDocument();
    expect(screen.getByText('Zone Intrusion (Polygon)')).toBeInTheDocument();
    expect(screen.getByText('Tripwire Crossing (Vector)')).toBeInTheDocument();
  });

  it('renders SeverityDonutChart with total count and legend', () => {
    render(
      <SeverityDonutChart
        severityCounts={mockAnalytics.incidents_by_severity}
        totalIncidents={mockAnalytics.total_incidents}
      />
    );
    expect(screen.getByText('SEVERITY PROFILE')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('BREACHES')).toBeInTheDocument();
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.getByText('Warning')).toBeInTheDocument();
  });

  it('renders CameraDistributionChart with camera nodes', () => {
    render(
      <CameraDistributionChart
        cameraCounts={mockAnalytics.incidents_by_camera}
        totalIncidents={mockAnalytics.total_incidents}
      />
    );
    expect(screen.getByText('INCIDENTS BY SURVEILLANCE NODE')).toBeInTheDocument();
    expect(screen.getByText('CAM-01')).toBeInTheDocument();
    expect(screen.getByText('CAM-02')).toBeInTheDocument();
    expect(screen.getByText('30')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('renders AnalyticsDashboardSection and handles time range toggle', () => {
    const handleTimeRange = vi.fn();
    render(
      <AnalyticsDashboardSection
        analytics={mockAnalytics}
        timeRange="24h"
        onTimeRangeChange={handleTimeRange}
      />
    );

    expect(screen.getByText('REAL-TIME SURVEILLANCE ANALYTICS')).toBeInTheDocument();
    const btn7d = screen.getByRole('button', { name: '7 Days' });
    fireEvent.click(btn7d);
    expect(handleTimeRange).toHaveBeenCalledWith('7d');

    const btnAll = screen.getByRole('button', { name: 'All Time' });
    fireEvent.click(btnAll);
    expect(handleTimeRange).toHaveBeenCalledWith('all');
  });

  it('handles empty data state cleanly without errors', () => {
    render(
      <AnalyticsDashboardSection
        analytics={null}
        timeRange="24h"
        onTimeRangeChange={vi.fn()}
      />
    );
    expect(screen.getByText('NO INCIDENTS RECORDED IN SELECTED INTERVAL')).toBeInTheDocument();
    expect(
      screen.getByText('NO CAMERA SENSOR ACTIVITY RECORDED IN SELECTED INTERVAL')
    ).toBeInTheDocument();
  });
});
