import { useQuery } from '@tanstack/react-query';
import { Activity, Bell, Blocks, ChefHat, LayoutDashboard } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';
import { api } from './api/client';
import DashboardPage from './pages/DashboardPage';
import LayoutEditorPage from './pages/LayoutEditorPage';
import RecipePage from './pages/RecipePage';
import AlertHistoryPage from './pages/AlertHistoryPage';

type PageKey = 'dashboard' | 'layout' | 'recipes' | 'alerts';

const navItems: { key: PageKey; label: string; icon: ReactNode }[] = [
  { key: 'dashboard', label: 'Live Dashboard', icon: <LayoutDashboard size={19} /> },
  { key: 'layout', label: 'Machine Layout', icon: <Blocks size={19} /> },
  { key: 'recipes', label: 'Recipes', icon: <ChefHat size={19} /> },
  { key: 'alerts', label: 'Alert History', icon: <Bell size={19} /> }
];

function App() {
  const [page, setPage] = useState<PageKey>('dashboard');
  const configQuery = useQuery({ queryKey: ['config'], queryFn: api.getConfig });
  const machinesQuery = useQuery({ queryKey: ['machines'], queryFn: api.listMachines });
  const [machineOverride, setMachineOverride] = useState<number | null>(null);

  const defaultMachineId = configQuery.data?.default_machine_id ?? 1;
  const machineId = machineOverride ?? defaultMachineId;
  const machine = useMemo(
    () => machinesQuery.data?.find((item) => item.machine_id === machineId),
    [machinesQuery.data, machineId]
  );

  const title = configQuery.data?.app_name ?? 'BBG OPC Dashboard';

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-icon"><Activity size={24} /></div>
          <div>
            <div className="brand-title">{title}</div>
            <div className="brand-subtitle">Production Monitor</div>
          </div>
        </div>

        <div className="machine-picker">
          <label>Machine</label>
          <select
            value={machineId}
            onChange={(event) => setMachineOverride(Number(event.target.value))}
          >
            {machinesQuery.data?.map((item) => (
              <option value={item.machine_id} key={item.machine_id}>
                {item.machine_name}
              </option>
            ))}
            {!machinesQuery.data?.length && <option value={machineId}>Machine {machineId}</option>}
          </select>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <button
              className={page === item.key ? 'nav-item active' : 'nav-item'}
              key={item.key}
              onClick={() => setPage(item.key)}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div>{machine?.machine_name ?? `Machine ${machineId}`}</div>
          <small>Refresh: {configQuery.data?.live_refresh_seconds ?? 60}s</small>
        </div>
      </aside>

      <main className="main-content">
        {page === 'dashboard' && <DashboardPage machineId={machineId} refreshSeconds={configQuery.data?.live_refresh_seconds ?? 60} />}
        {page === 'layout' && <LayoutEditorPage machineId={machineId} />}
        {page === 'recipes' && <RecipePage machineId={machineId} />}
        {page === 'alerts' && <AlertHistoryPage machineId={machineId} />}
      </main>
    </div>
  );
}

export default App;
