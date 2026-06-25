import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';
import { Eye, EyeOff, Plus } from 'lucide-react';
import { api } from '../api/client';
import type { LiveValue } from '../types';

interface SectionPanelProps {
  machineId: number;
  sectionKey: string | null;
  refreshMs: number;
  onNumericValuesChange?: (values: LiveValue[]) => void;
  onSaveVariable?: (value: LiveValue) => void;
  savedVariableIds?: number[];
}

function ValueRows({
  machineId,
  values,
  visible,
  className,
  onSaveVariable,
  savedVariableIds = []
}: {
  machineId: number;
  values: LiveValue[];
  visible: boolean;
  className?: string;
  onSaveVariable?: (value: LiveValue) => void;
  savedVariableIds?: number[];
}) {
  const queryClient = useQueryClient();
  const toggleMutation = useMutation({
    mutationFn: (row: LiveValue) => api.updateTagConfig(machineId, row.tag_id, { is_visible: !Boolean(row.is_visible) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['section-live'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard', machineId] });
    }
  });

  return (
    <div className={className ? `value-table-wrap ${className}` : 'value-table-wrap'}>
      <table className="value-table">
        <thead>
          <tr>
            <th className="action-col">Show</th>
            <th>Display Name</th>
            <th>Current Value</th>
            <th className="action-col">Save</th>
          </tr>
        </thead>
        <tbody>
          {values.map((row) => (
            <tr key={row.tag_id}>
              <td className="action-col">
                <button className="icon-button" onClick={() => toggleMutation.mutate(row)} title={visible ? 'Hide variable' : 'Show variable'}>
                  {visible ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </td>
              <td>{row.label}</td>
              <td className="current-value">{row.current_value}</td>
              <td className="action-col">
                <button
                  className="icon-button"
                  disabled={!row.is_numeric || savedVariableIds.includes(row.tag_id)}
                  onClick={() => onSaveVariable?.(row)}
                  title={
                    !row.is_numeric
                      ? 'Only numeric variables can be saved for history comparison'
                      : savedVariableIds.includes(row.tag_id)
                        ? 'Variable already saved'
                        : 'Save variable for comparison'
                  }
                >
                  <Plus size={16} />
                </button>
              </td>
            </tr>
          ))}
          {!values.length && (
            <tr>
              <td colSpan={4} className="muted-cell">No variables in this group.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function SectionPanel({
  machineId,
  sectionKey,
  refreshMs,
  onNumericValuesChange,
  onSaveVariable,
  savedVariableIds = []
}: SectionPanelProps) {
  const liveQuery = useQuery({
    queryKey: ['section-live', machineId, sectionKey],
    queryFn: () => api.getSectionLive(machineId, sectionKey as string, true),
    enabled: Boolean(sectionKey),
    refetchInterval: sectionKey ? refreshMs : false
  });

  const values = liveQuery.data?.values ?? [];
  const shown = useMemo(() => values.filter((row) => Boolean(row.is_visible)), [values]);
  const hidden = useMemo(() => values.filter((row) => !Boolean(row.is_visible)), [values]);
  const numericShown = useMemo(() => values.filter((row) => row.is_numeric && Boolean(row.is_visible)), [values]);

  useEffect(() => {
    if (onNumericValuesChange && sectionKey) {
      onNumericValuesChange(numericShown);
    }
  }, [onNumericValuesChange, sectionKey, numericShown]);

  if (!sectionKey) {
    return (
      <section className="section-panel panel-fill">
        <div className="empty-section">
          <h2>No section selected</h2>
          <p>Click a box on the machine image or select an alert to view live values and history.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="section-panel panel-fill">
      <div className="panel-title-row compact">
        <div>
          <h2>{liveQuery.data?.section.display_label ?? sectionKey}</h2>
          <p>Live values refresh automatically every minute.</p>
        </div>
      </div>

      <div className="section-content-row">
        <div className="section-media-column">
          {liveQuery.data?.section.section_photo_url ? (
            <img className="section-photo" src={liveQuery.data.section.section_photo_url} alt={liveQuery.data.section.display_label} />
          ) : (
            <div className="section-photo-placeholder">No section photo found</div>
          )}
        </div>
        <div className="section-values-column">
          <h3 className="subheading">Shown Variables</h3>
          <ValueRows
            machineId={machineId}
            values={shown}
            visible
            className="section-values-scroll"
            onSaveVariable={onSaveVariable}
            savedVariableIds={savedVariableIds}
          />
        </div>
      </div>

      <details className="hidden-vars">
        <summary>Hidden Variables ({hidden.length})</summary>
        <ValueRows
          machineId={machineId}
          values={hidden}
          visible={false}
          onSaveVariable={onSaveVariable}
          savedVariableIds={savedVariableIds}
        />
      </details>
    </section>
  );
}

export default SectionPanel;
