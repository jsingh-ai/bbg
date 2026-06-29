import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';
import { Eye, EyeOff, Plus } from 'lucide-react';
import { api } from '../api/client';
import type { LiveValue } from '../types';

type ValueGroupKey = 'para' | 'state' | 'temperature-control';

interface SectionPanelProps {
  machineId: number;
  sectionKey: string | null;
  refreshMs: number;
  onNumericValuesChange?: (values: LiveValue[]) => void;
  onSaveVariable?: (value: LiveValue) => void;
  savedVariableIds?: number[];
  savedVariableLimitReached?: boolean;
}

const VALUE_GROUPS: { key: ValueGroupKey; label: string }[] = [
  { key: 'para', label: 'Para' },
  { key: 'state', label: 'State' },
  { key: 'temperature-control', label: 'Temperature Control' }
];

function groupForValue(value: LiveValue): ValueGroupKey {
  const segments = String(value.opc_path || '')
    .toLowerCase()
    .split(/[\\/]/)
    .map((segment) => segment.trim())
    .filter(Boolean);

  if (segments.some((segment) => segment.includes('temperature control') || segment.includes('temperature_control'))) {
    return 'temperature-control';
  }
  if (segments.some((segment) => segment === 'para' || segment.startsWith('para '))) {
    return 'para';
  }
  if (segments.some((segment) => segment === 'state' || segment.startsWith('state '))) {
    return 'state';
  }
  return 'state';
}

function groupValues(values: LiveValue[]): Record<ValueGroupKey, LiveValue[]> {
  return values.reduce<Record<ValueGroupKey, LiveValue[]>>(
    (groups, value) => {
      groups[groupForValue(value)].push(value);
      return groups;
    },
    {
      para: [],
      state: [],
      'temperature-control': []
    }
  );
}

function ValueRows({
  machineId,
  values,
  visible,
  className,
  onSaveVariable,
  savedVariableIds = [],
  savedVariableLimitReached = false
}: {
  machineId: number;
  values: LiveValue[];
  visible: boolean;
  className?: string;
  onSaveVariable?: (value: LiveValue) => void;
  savedVariableIds?: number[];
  savedVariableLimitReached?: boolean;
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
            <th className="action-col" aria-label="Show toggle column"></th>
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
              <td className="current-value-cell"><span className="current-value-pill">{row.current_value}</span></td>
              <td className="action-col">
                {Boolean(row.is_history_numeric ?? row.is_numeric) ? (
                  <button
                    className="icon-button"
                    disabled={savedVariableIds.includes(row.tag_id) || savedVariableLimitReached}
                    onClick={() => onSaveVariable?.(row)}
                    title={
                      savedVariableIds.includes(row.tag_id)
                        ? 'Variable already saved'
                        : savedVariableLimitReached
                          ? 'Saved comparison is limited to 25 variables'
                          : 'Save variable for comparison'
                    }
                  >
                    <Plus size={16} />
                  </button>
                ) : (
                  <span className="muted-cell">--</span>
                )}
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

function GroupedValueRows({
  machineId,
  values,
  visible,
  onSaveVariable,
  savedVariableIds,
  savedVariableLimitReached,
  className
}: {
  machineId: number;
  values: LiveValue[];
  visible: boolean;
  onSaveVariable?: (value: LiveValue) => void;
  savedVariableIds: number[];
  savedVariableLimitReached: boolean;
  className?: string;
}) {
  const groups = useMemo(() => groupValues(values), [values]);

  return (
    <div className={className ? `value-groups ${className}` : 'value-groups'}>
      {VALUE_GROUPS.map((group) => (
        <details className="value-group" key={group.key} defaultOpen>
          <summary>
            <span>{group.label}</span>
            <strong>{groups[group.key].length}</strong>
          </summary>
          <ValueRows
            machineId={machineId}
            values={groups[group.key]}
            visible={visible}
            onSaveVariable={onSaveVariable}
            savedVariableIds={savedVariableIds}
            savedVariableLimitReached={savedVariableLimitReached}
          />
        </details>
      ))}
    </div>
  );
}

function SectionPanel({
  machineId,
  sectionKey,
  refreshMs,
  onNumericValuesChange,
  onSaveVariable,
  savedVariableIds = [],
  savedVariableLimitReached = false
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
  const numericShown = useMemo(
    () => values.filter((row) => Boolean(row.is_visible) && Boolean(row.is_history_numeric ?? row.is_numeric)),
    [values]
  );

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
      <div className="panel-title-row panel-header compact">
        <div className="panel-title-block">
          <span className="panel-eyebrow">Selected Section</span>
          <h2 className="panel-title">{liveQuery.data?.section.display_label ?? sectionKey}</h2>
          <p className="panel-subtitle">Live values refresh automatically every minute.</p>
        </div>
      </div>

      <div className="panel-body section-panel-body">
        <div className="section-content-row">
          <div className="section-media-column">
            <div className="section-photo-frame">
              <div className="section-photo-header">
                <span className="panel-eyebrow">Section View</span>
              </div>
              <div className="section-photo-stage">
            {liveQuery.data?.section.section_photo_url ? (
              <img className="section-photo" src={liveQuery.data.section.section_photo_url} alt={liveQuery.data.section.display_label} />
            ) : (
              <div className="section-photo-placeholder">No section photo found</div>
            )}
              </div>
            </div>
          </div>
          <div className="section-values-column">
            <h3 className="subheading">Shown Variables</h3>
            <GroupedValueRows
              machineId={machineId}
              values={shown}
              visible
              onSaveVariable={onSaveVariable}
              savedVariableIds={savedVariableIds}
              savedVariableLimitReached={savedVariableLimitReached}
              className="section-values-scroll"
            />
          </div>
        </div>
      </div>

      <details className="hidden-vars">
        <summary>Hidden Variables ({hidden.length})</summary>
        <GroupedValueRows
          machineId={machineId}
          values={hidden}
          visible={false}
          onSaveVariable={onSaveVariable}
          savedVariableIds={savedVariableIds}
          savedVariableLimitReached={savedVariableLimitReached}
        />
      </details>
    </section>
  );
}

export default SectionPanel;
