import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { Overview } from './pages/Overview';
import { api } from './services/api';
import { wsService } from './services/websocket';
import { WsConnectionStatus } from './types/events';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>('overview');
  const [systemStatus, setSystemStatus] = useState<string>('online');
  const [cameraCount, setCameraCount] = useState<number | string>(1);
  const [wsStatus, setWsStatus] = useState<WsConnectionStatus>('CONNECTING');

  useEffect(() => {
    // Initial fetch for top-bar status
    api.getHealth()
      .then((h) => setSystemStatus(h.status))
      .catch(() => setSystemStatus('offline'));

    api.getCameras()
      .then((cams) => setCameraCount(cams.length))
      .catch(() => setCameraCount(1));

    const unsubWs = wsService.onStatusChange(setWsStatus);
    return () => unsubWs();
  }, []);

  return (
    <div className="app-layout">
      {/* Left Sidebar */}
      <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Main Content Area */}
      <div className="main-wrapper">
        {/* Top Header */}
        <Header
          systemStatus={systemStatus}
          cameraCount={cameraCount}
          wsStatus={wsStatus}
        />

        {/* Central Command Center Dashboard */}
        <Overview />
      </div>
    </div>
  );
};

export default App;
