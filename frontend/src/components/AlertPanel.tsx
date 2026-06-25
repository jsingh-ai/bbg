import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2 } from 'lucide-react';
import { api } from '../api/client';
import type { AlertEvent } from '../types';

interface AlertPanelProps {
  machineId: number;
  alerts: AlertEvent[];
  onSelectSection: (sectionKey: string) => void;
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined) return '--';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 5 });
}

function AlertPanel({ machineId, alerts, onSelectSection }: AlertPanelProps) {
  const queryClient = useQueryClient();
  const ackMutation = useMutation({
    mutationFn: (alertId: number) => {
      const acknowledgedBy = window.prompt('Acknowledge as:', 'dashboard') || 'dashboard';
      const note = window.prompt('Optional note:', '') || '';
      return api.acknowledgeAlert(alertId, acknowledgedBy, note);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard', machineId] });
      queryClient.invalidateQueries({ queryKey: ['alerts', machineId] });
      queryClient.invalidateQueries({ queryKey: ['sections', machineId] });
    }
  });

  return (
    <section className="alerts-panel panel-fill">
      <div className="panel-title-row panel-header compact">
        <div className="panel-title-block">
          <span className="panel-eyebrow">Attention</span>
          <h2 className="panel-title">Active Alerts</h2>
          <p className="panel-subtitle">{alerts.length ? `${alerts.length} unacknowledged alert(s)` : 'No active alerts'}</p>
        </div>
      </div>
      <div className="panel-body alert-panel-body">
        <div className="alert-list">
          {alerts.map((alert) => {
            const current = Boolean(alert.is_currently_out_of_range);
            return (
              <article className={`alert-card ${current ? 'danger' : 'returned'}`} key={alert.alert_id}>
                <button className="alert-body" onClick={() => onSelectSection(alert.section_key)}>
                  <div className="alert-header-line">
                    <strong>{alert.section_key}</strong>
                    <span>{current ? 'Still out of range' : 'Back in range'}</span>
                  </div>
                  <div className="alert-title">{alert.display_name ?? `Tag ${alert.tag_id}`}</div>
                  <div className="alert-detail">
                    Current {formatNumber(alert.current_value)} | Min {formatNumber(alert.min_value)} | Max {formatNumber(alert.max_value)}
                  </div>
                  <small>Triggered {new Date(alert.triggered_at).toLocaleString()}</small>
                </button>
                <button className="ack-button" onClick={() => ackMutation.mutate(alert.alert_id)}>
                  <CheckCircle2 size={15} /> Acknowledge
                </button>
              </article>
            );
          })}
          {!alerts.length && <div className="empty-state">Alerts created from recipe limits will appear here until acknowledged.</div>}
        </div>
      </div>
    </section>
  );
}

export default AlertPanel;
