import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { RefreshCcw } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import AlertPanel from '../components/AlertPanel';
import AssistantPanel from '../components/AssistantPanel';
import DashboardSummary from '../components/DashboardSummary';
import HistoryChart, {
  MAX_SAVED_COMPARISON_TRENDS,
  MAX_SECTION_HISTORY_TRENDS,
  SavedVariablesChart
} from '../components/HistoryChart';
import MachineMap from '../components/MachineMap';
import RecipeSelector from '../components/RecipeSelector';
import SectionPanel from '../components/SectionPanel';
import type { LiveValue, SavedHistoryVariable } from '../types';
import type { ThemeMode } from '../hooks/useTheme';

interface DashboardPageProps {
  machineId: number;
  refreshSeconds: number;
  assistantEnabled: boolean;
  theme: ThemeMode;
}

function DashboardPage({ machineId, refreshSeconds, assistantEnabled, theme }: DashboardPageProps) {
  const queryClient = useQueryClient();
  const [selectedSectionKey, setSelectedSectionKey] = useState<string | null>(null);
  const [numericValues, setNumericValues] = useState<LiveValue[]>([]);
  const [savedVariables, setSavedVariables] = useState<SavedHistoryVariable[]>([]);
  const savedHistoryRef = useRef<HTMLDivElement | null>(null);
  const previousSavedCountRef = useRef(0);
  const isEvaluatingAlertsRef = useRef(false);
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
    },
    onSettled: () => {
      isEvaluatingAlertsRef.current = false;
    }
  });
  const evaluateAlerts = evaluateMutation.mutate;

  const runAlertEvaluation = useCallback(() => {
    if (isEvaluatingAlertsRef.current) return;
    isEvaluatingAlertsRef.current = true;
    evaluateAlerts();
  }, [evaluateAlerts]);

  useEffect(() => {
    runAlertEvaluation();
    const handle = window.setInterval(runAlertEvaluation, refreshMs);
    return () => window.clearInterval(handle);
  }, [machineId, refreshMs, runAlertEvaluation]);

  useEffect(() => {
    setSelectedSectionKey(null);
    setNumericValues([]);
    setSavedVariables([]);
    previousSavedCountRef.current = 0;
  }, [machineId]);

  useEffect(() => {
    if (savedVariables.length > previousSavedCountRef.current) {
      window.setTimeout(() => {
        savedHistoryRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 80);
    }
    previousSavedCountRef.current = savedVariables.length;
  }, [savedVariables.length]);

  const handleManualRefresh = async () => {
    await api.syncMachine(machineId);
    runAlertEvaluation();
    summaryQuery.refetch();
    queryClient.invalidateQueries({ queryKey: ['dashboard', machineId] });
    queryClient.invalidateQueries({ queryKey: ['section-live'] });
  };

  const handleSelectSection = useCallback((sectionKey: string) => {
    setSelectedSectionKey(sectionKey);
    window.setTimeout(() => {
      document.querySelector('.section-panel')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 50);
  }, []);

  const handleSaveVariable = useCallback((value: LiveValue) => {
    if (!(value.is_history_numeric ?? value.is_numeric)) return;
    setSavedVariables((prev) => {
      if (prev.some((item) => item.tag_id === value.tag_id)) {
        return prev;
      }
      if (prev.length >= MAX_SAVED_COMPARISON_TRENDS) {
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

  const handleToggleSpeedVariable = useCallback(() => {
    const speed = summaryQuery.data?.speed;
    const speedTagId = speed?.tag_id;
    if (!speedTagId) return;
    setSavedVariables((prev) => {
      if (prev.some((item) => item.tag_id === speedTagId)) {
        return prev.filter((item) => item.tag_id !== speedTagId);
      }
      if (prev.length >= MAX_SAVED_COMPARISON_TRENDS) {
        return prev;
      }
      return [
        ...prev,
        {
          tag_id: speedTagId,
          label: speed.label || 'Machine Speed',
          section_key: 'Machine',
          current_value: speed.current_value
        }
      ];
    });
  }, [summaryQuery.data?.speed]);

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
  const shouldShowSectionHistory = numericValues.length <= MAX_SECTION_HISTORY_TRENDS;

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
          <DashboardSummary machineId={machineId} summary={summaryQuery.data} theme={theme} />
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
              savedVariableLimitReached={savedVariables.length >= MAX_SAVED_COMPARISON_TRENDS}
            />
            {shouldShowSectionHistory && (
              <HistoryChart
                machineId={machineId}
                sectionKey={selectedSectionKey}
                numericValues={numericValues}
                refreshMs={refreshMs}
                theme={theme}
              />
            )}
          </div>
        )}
        {savedVariables.length > 0 && (
          <div className="dashboard-saved-history-row" ref={savedHistoryRef}>
            <SavedVariablesChart
              machineId={machineId}
              refreshMs={refreshMs}
              theme={theme}
              savedVariables={savedVariables}
              speedMetric={summaryQuery.data?.speed}
              onToggleSpeedVariable={handleToggleSpeedVariable}
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
