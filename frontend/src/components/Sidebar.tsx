import React from 'react';
import {
  ShieldCheck,
  LayoutDashboard,
  Video,
  AlertTriangle,
  Camera,
  MapPin,
} from 'lucide-react';

interface SidebarProps {
  activeTab?: string;
  onTabChange?: (tab: string) => void;
}

interface NavItem {
  id: string;
  label: string;
  icon: React.ElementType;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab = 'overview',
  onTabChange,
}) => {
  const operationsNav: NavItem[] = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'surveillance', label: 'Live Surveillance', icon: Video },
    { id: 'incidents', label: 'Incidents', icon: AlertTriangle },
  ];

  const monitoringNav: NavItem[] = [
    { id: 'cameras', label: 'Cameras', icon: Camera },
    { id: 'zones', label: 'Zones & Wires', icon: MapPin },
  ];

  const renderNavList = (items: NavItem[]) => (
    <>
      {items.map((item) => {
        const Icon = item.icon;
        const isActive = activeTab === item.id;

        return (
          <button
            key={item.id}
            type="button"
            className={`sidebar-nav-item ${isActive ? 'active' : ''}`}
            onClick={() => onTabChange && onTabChange(item.id)}
            title={item.label}
          >
            <Icon size={14} />
            <span>{item.label}</span>
          </button>
        );
      })}
    </>
  );

  return (
    <aside className="sidebar" aria-label="Command Center Navigation">
      {/* Branding Header */}
      <div className="sidebar-branding">
        <ShieldCheck className="sidebar-logo-icon" />
        <div>
          <div className="sidebar-brand-title">IBVAP</div>
          <div className="sidebar-brand-sub">Border Analytics</div>
        </div>
      </div>

      {/* Operations & Monitoring Navigation Groups */}
      <nav className="sidebar-nav">
        <div className="sidebar-section-title">Operations</div>
        {renderNavList(operationsNav)}

        <div className="sidebar-section-title" style={{ marginTop: '8px' }}>Monitoring</div>
        {renderNavList(monitoringNav)}
      </nav>

      {/* Footer Info */}
      <div className="sidebar-footer mono">
        <div className="sidebar-footer-row">
          <span>SYSTEM</span>
          <span className="sidebar-system-badge">
            <span className="status-dot status-dot-pulse" style={{ backgroundColor: 'var(--status-online)' }} />
            ONLINE
          </span>
        </div>
        <div className="sidebar-footer-row" style={{ color: 'var(--text-muted)' }}>
          <span>SEC-LEVEL</span>
          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>ALPHA</span>
        </div>
        <div className="sidebar-footer-row" style={{ color: 'var(--text-dim)', fontSize: '9px' }}>
          <span>PS-26187</span>
          <span>STATION 01</span>
        </div>
      </div>
    </aside>
  );
};
