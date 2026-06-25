import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { RefreshCcw } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import AlertPanel from '../components/AlertPanel';
import AssistantPanel from '../components/AssistantPanel';
import DashboardSummary from '../components/DashboardSummary';
import HistoryChart, { SavedVariablesChart } from '../components/HistoryChart';
import MachineMap from '../components/MachineMap';
import RecipeSelector from '../components/RecipeSelector';
import SectionPanel from '../components/SectionPanel';
import type { LiveValue, SavedHistoryVariable } from '../types';

interface DashboardPageProps {
  machineId: number;
  refreshSeconds: number;
  assistantEnabled: boolean;
}

function DashboardPage({ machineId, refreshSeconds, assistantEnabled }: DashboardPageProps) {
  const queryClient = useQueryClient();
  const [selectedSectionKey, setSelectedSectionKey] = useState<string | null>(null);
  const [numericValues, setNumericValues] = useState<LiveValue[]>([]);
  const [savedVariables, setSavedVariables] = useState<SavedHistoryVariable[]>([]);
  const refreshMs = Math.max(refreshSeconds, 10) * 1000;

  const dashboardQuery = useQuery({
    queryKey: ['dashboard', machineId],
    queryFn: () => api.getDashboard(machineId),
    refetchInterval: refreshMs
  });
  const summaryQuery = useQuery({
    queryKey: ['summary', machineId],
    queryFn: () => api.getSummary(machineId),
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
    setSavedVariables([]);
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

  const handleSaveVariable = useCallback((value: LiveValue) => {
    if (!value.is_numeric) return;
    setSavedVariables((prev) => {
      if (prev.some((item) => item.tag_id === value.tag_id)) {
        return prev;
      }
      return [
        ...prev,
        {
          tag_id: value.tag_id,
          label: value.label,
          section_key: value.section_key,
          current_value: value.current_value
        }
      ];
    });
  }, []);

  const handleRemoveSavedVariable = useCallback((tagId: number) => {
    setSavedVariables((prev) => prev.filter((item) => item.tag_id !== tagId));
  }, []);

  const handleClearSavedVariables = useCallback(() => {
    setSavedVariables([]);
  }, []);

  const state = dashboardQuery.data;
  const machine = state?.machine;
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

      {(dashboardQuery.isError || summaryQuery.isError) && (
        <div className="error-banner">{((dashboardQuery.error || summaryQuery.error) as Error).message}</div>
      )}

      <div className="dashboard-grid">
        <div className="dashboard-summary-row">
          <DashboardSummary machineId={machineId} summary={summaryQuery.data} />
        </div>
        <div className="dashboard-assistant-row">
          <AssistantPanel enabled={assistantEnabled} />
        </div>
        <div className="dashboard-map-row">
          <MachineMap
            machine={machine}
            sections={sections}
            selectedSectionKey={selectedSectionKey}
            onSelect={handleSelectSection}
          />
        </div>
        {selectedSectionKey && (
          <div className="dashboard-live-history-row">
            <SectionPanel
              machineId={machineId}
              sectionKey={selectedSectionKey}
              refreshMs={refreshMs}
              onNumericValuesChange={setNumericValues}
              onSaveVariable={handleSaveVariable}
              savedVariableIds={savedVariables.map((item) => item.tag_id)}
            />
            <HistoryChart
              machineId={machineId}
              sectionKey={selectedSectionKey}
              numericValues={numericValues}
              refreshMs={refreshMs}
            />
          </div>
        )}
        {savedVariables.length > 0 && (
          <div className="dashboard-saved-history-row">
            <SavedVariablesChart
              machineId={machineId}
              refreshMs={refreshMs}
              savedVariables={savedVariables}
              onRemoveSavedVariable={handleRemoveSavedVariable}
              onClearSavedVariables={handleClearSavedVariables}
            />
          </div>
        )}
        {alerts.length > 0 && (
          <div className="dashboard-alerts-row">
            <AlertPanel machineId={machineId} alerts={alerts} onSelectSection={handleSelectSection} />
          </div>
        )}
      </div>
    </div>
  );
}

export default DashboardPage;
