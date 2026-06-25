import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { RefreshCcw } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import AlertPanel from '../components/AlertPanel';
import HistoryChart from '../components/HistoryChart';
import MachineMap from '../components/MachineMap';
import RecipeSelector from '../components/RecipeSelector';
import SectionPanel from '../components/SectionPanel';
import type { LiveValue } from '../types';

interface DashboardPageProps {
  machineId: number;
  refreshSeconds: number;
}

function DashboardPage({ machineId, refreshSeconds }: DashboardPageProps) {
  const queryClient = useQueryClient();
  const [selectedSectionKey, setSelectedSectionKey] = useState<string | null>(null);
  const [numericValues, setNumericValues] = useState<LiveValue[]>([]);
  const refreshMs = Math.max(refreshSeconds, 10) * 1000;

  const dashboardQuery = useQuery({
    queryKey: ['dashboard', machineId],
    queryFn: () => api.getDashboard(machineId),
    refetchInterval: refreshMs
  });

  const evaluateMutation = useMutation({
    mutationFn: () => api.evaluateAlerts(machineId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard', machineId] });
      queryClient.invalidateQueries({ queryKey: ['sections', machineId] });
    }
  });

  useEffect(() => {
    evaluateMutation.mutate();
    const handle = window.setInterval(() => evaluateMutation.mutate(), refreshMs);
    return () => window.clearInterval(handle);
  }, [machineId, refreshMs]);

  useEffect(() => {
    setSelectedSectionKey(null);
    setNumericValues([]);
  }, [machineId]);

  const handleManualRefresh = () => {
    evaluateMutation.mutate();
    dashboardQuery.refetch();
    queryClient.invalidateQueries({ queryKey: ['section-live'] });
  };

  const handleSelectSection = useCallback((sectionKey: string) => {
    setSelectedSectionKey(sectionKey);
    window.setTimeout(() => {
      document.querySelector('.section-panel')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 50);
  }, []);

  const state = dashboardQuery.data;
  const machine = state?.machine;
  const activeRecipe = state?.active_recipe;
  const sections = state?.sections ?? [];
  const alerts = state?.alerts ?? [];

  return (
    <div className="page dashboard-page">
      <header className="page-header">
        <div>
          <h1>{machine?.machine_name ?? `Machine ${machineId}`}</h1>
          <p>Live OPC values, recipe limits, persistent alerts, and section history.</p>
        </div>
        <div className="header-actions">
          <RecipeSelector machineId={machineId} />
          <button className="secondary-button" onClick={handleManualRefresh}>
            <RefreshCcw size={16} /> Refresh
          </button>
        </div>
      </header>

      <div className="status-strip">
        <div className="status-pill"><span>Selected Recipe</span><strong>{activeRecipe?.recipe_name ?? 'None'}</strong></div>
        <div className="status-pill"><span>Open Alerts</span><strong>{alerts.length}</strong></div>
        <div className="status-pill"><span>Mapped Sections</span><strong>{sections.filter((s) => s.has_box).length}</strong></div>
        <div className="status-pill"><span>Selected Section</span><strong>{selectedSectionKey ?? 'None'}</strong></div>
      </div>

      {dashboardQuery.isError && <div className="error-banner">{(dashboardQuery.error as Error).message}</div>}

      <div className="dashboard-grid">
        <div className="dashboard-map-row">
          <MachineMap
            machine={machine}
            sections={sections}
            selectedSectionKey={selectedSectionKey}
            onSelect={handleSelectSection}
          />
        </div>
        <div className="dashboard-middle-row">
          <SectionPanel
            machineId={machineId}
            sectionKey={selectedSectionKey}
            refreshMs={refreshMs}
            onNumericValuesChange={setNumericValues}
          />
          <AlertPanel machineId={machineId} alerts={alerts} onSelectSection={handleSelectSection} />
        </div>
        <div className="dashboard-history-row">
          <HistoryChart
            machineId={machineId}
            sectionKey={selectedSectionKey}
            numericValues={numericValues}
            refreshMs={refreshMs}
          />
        </div>
      </div>
    </div>
  );
}

export default DashboardPage;
