import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { StatCard } from '../components/StatCard';
import { ShieldAlert } from 'lucide-react';

describe('StatCard Component', () => {
  it('renders label and value correctly', () => {
    render(
      <StatCard
        label="Total Incidents"
        value={15}
        subtext="CAM: CAM-01"
        icon={ShieldAlert}
        variant="critical"
      />
    );

    expect(screen.getByText('Total Incidents')).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText('CAM: CAM-01')).toBeInTheDocument();
  });

  it('renders loading state when loading prop is true', () => {
    render(
      <StatCard
        label="Active Cameras"
        value={2}
        loading={true}
      />
    );

    expect(screen.getByText('Active Cameras')).toBeInTheDocument();
    expect(screen.getByText('...')).toBeInTheDocument();
  });
});
