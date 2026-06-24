import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';

interface AlertHistoryPageProps {
  machineId: number;
}

function fmt(value?: number | null) {
  if (value === null || value === undefined) return '--';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 5 });
}

function AlertHistoryPage({ machineId }: AlertHistoryPageProps) {
  const queryClient = useQueryClient();
  const alertsQuery = useQuery({ queryKey: ['alerts', machineId, false], queryFn: () => api.listAlerts(machineId, false, 500) });
  const ackMutation = useMutation({
    mutationFn: (alertId: number) => api.acknowledgeAlert(alertId, 'dashboard', 'Acknowledged from alert history page'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alerts', machineId, false] })
  });

  return (
    <div className="page alerts-page">
      <header className="page-header">
        <div>
          <h1>Alert History</h1>
          <p>Alerts are stored permanently. Acknowledging hides them from the active dashboard but does not delete them.</p>
        </div>
      </header>

      <section className="panel-fill">
        <div className="value-table-wrap">
          <table className="value-table alert-history-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Section</th>
                <th>Variable</th>
                <th>Current</th>
                <th>Min</th>
                <th>Max</th>
                <th>Triggered</th>
                <th>Acknowledged</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {alertsQuery.data?.map((alert) => (
                <tr key={alert.alert_id}>
                  <td>
                    {Boolean(alert.is_acknowledged)
                      ? 'Acknowledged'
                      : Boolean(alert.is_currently_out_of_range)
                        ? 'Open - out of range'
                        : 'Open - returned'}
                  </td>
                  <td>{alert.section_key}</td>
                  <td>{alert.display_name ?? `Tag ${alert.tag_id}`}</td>
                  <td>{fmt(alert.current_value)}</td>
                  <td>{fmt(alert.min_value)}</td>
                  <td>{fmt(alert.max_value)}</td>
                  <td>{new Date(alert.triggered_at).toLocaleString()}</td>
                  <td>{alert.acknowledged_at ? new Date(alert.acknowledged_at).toLocaleString() : '--'}</td>
                  <td>
                    {!Boolean(alert.is_acknowledged) && (
                      <button className="secondary-button small-button" onClick={() => ackMutation.mutate(alert.alert_id)}>Acknowledge</button>
                    )}
                  </td>
                </tr>
              ))}
              {!alertsQuery.data?.length && <tr><td colSpan={9} className="muted-cell">No alerts found.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

export default AlertHistoryPage;
