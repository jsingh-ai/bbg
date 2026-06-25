import { useQuery } from '@tanstack/react-query';
import * as echarts from 'echarts';
import { useEffect, useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../api/client';
import type { LiveValue, SavedHistoryVariable } from '../types';

const CHART_COLORS = ['#38bdf8', '#22c55e', '#f59e0b', '#f97316', '#ef4444', '#a78bfa', '#14b8a6', '#f43f5e'];

interface HistoryChartProps {
  machineId: number;
  sectionKey: string | null;
  numericValues: LiveValue[];
  refreshMs: number;
  savedVariables: SavedHistoryVariable[];
  onRemoveSavedVariable: (tagId: number) => void;
  onClearSavedVariables: () => void;
}

function toLocalInputValue(date: Date) {
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60_000);
  return local.toISOString().slice(0, 16);
}

function inputToQueryDateTime(value: string) {
  return value.length === 16 ? `${value}:00` : value;
}

function defaultRange() {
  const end = new Date();
  const start = new Date(end.getTime() - 60 * 60_000);
  return { start: toLocalInputValue(start), end: toLocalInputValue(end) };
}

function HistoryChart({
  machineId,
  sectionKey,
  numericValues,
  refreshMs,
  savedVariables,
  onRemoveSavedVariable,
  onClearSavedVariables
}: HistoryChartProps) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);
  const [range, setRange] = useState(defaultRange);
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([]);

  const comparisonVariables = useMemo(
    () =>
      savedVariables.map((item) => ({
        tag_id: item.tag_id,
        label: item.label,
        section_key: item.section_key,
        current_value: item.current_value,
        is_saved: true
      })),
    [savedVariables]
  );

  const selectorVariables = useMemo(() => {
    const merged = [
      ...numericValues.map((row) => ({
        tag_id: row.tag_id,
        label: row.label,
        section_key: row.section_key,
        current_value: row.current_value,
        is_saved: false
      })),
      ...comparisonVariables
    ];
    const seen = new Set<number>();
    return merged.filter((item) => {
      if (seen.has(item.tag_id)) return false;
      seen.add(item.tag_id);
      return true;
    });
  }, [numericValues, comparisonVariables]);

  const variableMetaByTagId = useMemo(
    () =>
      new Map(
        selectorVariables.map((item) => [
          item.tag_id,
          {
            label: item.label,
            section_key: item.section_key,
            is_saved: item.is_saved
          }
        ])
      ),
    [selectorVariables]
  );

  useEffect(() => {
    const preferred = numericValues.filter((row) => Boolean(row.show_in_history_default));
    const source = preferred.length ? preferred : numericValues;
    const currentDefaults = source
      .slice(0, 8)
      .map((row) => row.tag_id);
    const savedIds = savedVariables.map((item) => item.tag_id);
    const nextIds = Array.from(new Set([...currentDefaults, ...savedIds]));
    setSelectedTagIds(nextIds);
  }, [sectionKey, numericValues, savedVariables]);

  useEffect(() => {
    if (!sectionKey) return;
    const handle = window.setInterval(() => {
      setRange((prev) => {
        const start = new Date(prev.start);
        const end = new Date(prev.end);
        const windowMs = Math.max(end.getTime() - start.getTime(), 60_000);
        const nextEnd = new Date();
        const nextStart = new Date(nextEnd.getTime() - windowMs);
        return {
          start: toLocalInputValue(nextStart),
          end: toLocalInputValue(nextEnd)
        };
      });
    }, refreshMs);
    return () => window.clearInterval(handle);
  }, [sectionKey, refreshMs]);

  const tagIds = useMemo(() => selectedTagIds.slice().sort((a, b) => a - b), [selectedTagIds]);

  const historyQuery = useQuery({
    queryKey: ['history', machineId, sectionKey, range.start, range.end, tagIds.join(',')],
    queryFn: () => api.getHistory(machineId, inputToQueryDateTime(range.start), inputToQueryDateTime(range.end), tagIds),
    enabled: Boolean(tagIds.length),
    staleTime: 10_000
  });

  const activeSeries = useMemo(
    () =>
      (historyQuery.data?.series ?? [])
        .filter((series) => selectedTagIds.includes(series.tag_id))
        .map((series) => {
          const meta = variableMetaByTagId.get(series.tag_id);
          const section = meta?.section_key || series.section_key || '';
          const label = meta?.label || series.label;
          return {
            ...series,
            display_name: section ? `${section} - ${label}` : label
          };
        }),
    [historyQuery.data, selectedTagIds, variableMetaByTagId]
  );

  const hasSeriesData = useMemo(
    () => activeSeries.some((series) => series.points.length > 0),
    [activeSeries]
  );

  useEffect(() => {
    if (!chartRef.current) return;
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }
    const chart = chartInstance.current;
    const data = activeSeries;
    if (historyQuery.isFetching) {
      chart.showLoading('default', {
        text: 'Loading trends...',
        color: '#38bdf8',
        textColor: '#cbd5e1',
        maskColor: 'rgba(15, 23, 42, 0.45)'
      });
    } else {
      chart.hideLoading();
    }
    if (!selectedTagIds.length) {
      chart.clear();
      return;
    }
    chart.clear();
    chart.setOption({
      animation: false,
        color: CHART_COLORS,
        backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(15, 23, 42, 0.94)',
        borderColor: 'rgba(148, 163, 184, 0.25)',
        textStyle: { color: '#e5eefb' }
      },
      legend: {
        top: 0,
        type: 'scroll',
        data: data.map((series) => series.display_name),
        selected: Object.fromEntries(data.map((series) => [series.display_name, true])),
        textStyle: { color: '#cbd5e1' },
        inactiveColor: '#64748b',
        pageTextStyle: { color: '#cbd5e1' }
      },
      grid: { left: 56, right: 24, top: 56, bottom: 46 },
      xAxis: {
        type: 'time',
        axisLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.35)' } },
        splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.10)' } },
        axisLabel: { color: '#94a3b8' }
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.35)' } },
        splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.10)' } },
        axisLabel: { color: '#94a3b8' }
      },
      dataZoom: [
        { type: 'inside' },
        {
          type: 'slider',
          height: 18,
          bottom: 8,
          borderColor: 'rgba(148, 163, 184, 0.22)',
          backgroundColor: 'rgba(15, 23, 42, 0.55)',
          fillerColor: 'rgba(56, 189, 248, 0.18)',
          moveHandleStyle: { color: '#38bdf8' },
          textStyle: { color: '#94a3b8' }
        }
      ],
      series: data.map((series) => ({
        name: series.display_name,
        type: 'line',
        showSymbol: false,
        connectNulls: false,
        smooth: true,
        lineStyle: { width: 2.5 },
        emphasis: { focus: 'series' },
        data: series.points
      }))
    }, { notMerge: true });
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    resize();
    return () => window.removeEventListener('resize', resize);
  }, [activeSeries, historyQuery.isFetching, selectedTagIds]);

  useEffect(() => {
    return () => {
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
  }, []);

  function setLastHour() {
    setRange(defaultRange());
  }

  function setLastMinutes(minutes: number) {
    const end = new Date();
    const start = new Date(end.getTime() - minutes * 60_000);
    setRange({ start: toLocalInputValue(start), end: toLocalInputValue(end) });
  }

  if (!sectionKey) {
    return (
      <section className="history-panel panel-fill">
        <h2>Historical Trends</h2>
        <div className="empty-state">Select a machine section to load the last hour of numeric history.</div>
      </section>
    );
  }

  return (
    <section className="history-panel panel-fill">
      <div className="panel-title-row history-header">
        <div>
          <h2>Historical Trends</h2>
          <p>Section: {sectionKey}</p>
        </div>
      </div>
      <div className="history-controls-bar">
        <div className="history-controls">
          <button onClick={() => setLastMinutes(15)}>15 min</button>
          <button onClick={setLastHour}>Last hour</button>
          <button onClick={() => setLastMinutes(240)}>4 hours</button>
          <label>
            Start
            <input type="datetime-local" value={range.start} onChange={(event) => setRange((prev) => ({ ...prev, start: event.target.value }))} />
          </label>
          <label>
            End
            <input type="datetime-local" value={range.end} onChange={(event) => setRange((prev) => ({ ...prev, end: event.target.value }))} />
          </label>
        </div>
      </div>

      <div className="history-body">
        <aside className="history-selector">
          <h3>Variables</h3>
          {selectorVariables.map((row) => (
            <label className="check-row history-check-row" key={row.tag_id}>
              <input
                type="checkbox"
                checked={selectedTagIds.includes(row.tag_id)}
                onChange={(event) => {
                  setSelectedTagIds((prev) =>
                    event.target.checked ? [...prev, row.tag_id] : prev.filter((id) => id !== row.tag_id)
                  );
                }}
              />
              <span>{row.section_key ? `${row.section_key} - ${row.label}` : row.label}</span>
            </label>
          ))}
          {!selectorVariables.length && <p className="empty-state small">No numeric visible variables found for this section.</p>}
        </aside>
        <div className="chart-stage">
          {historyQuery.isError && <div className="chart-message">{(historyQuery.error as Error).message}</div>}
          {!selectedTagIds.length && <div className="chart-message">Select one or more variables to chart.</div>}
          {!historyQuery.isError && selectedTagIds.length > 0 && historyQuery.data && !hasSeriesData && (
            <div className="chart-message">No history data found for the selected variables and time range.</div>
          )}
          <div ref={chartRef} className="echart" />
        </div>
      </div>
      <div className="history-chip-bar">
        <div className="history-chip-header">
          <h3>Saved Variables</h3>
          <button className="secondary-button small-button" disabled={!savedVariables.length} onClick={onClearSavedVariables}>
            Clear All
          </button>
        </div>
        <div className="history-chip-list">
          {savedVariables.map((item) => (
            <button className="history-chip" key={item.tag_id} onClick={() => onRemoveSavedVariable(item.tag_id)}>
              <span>{item.section_key} - {item.label}</span>
              <X size={14} />
            </button>
          ))}
          {!savedVariables.length && <div className="empty-state small">Save variables from live values to compare sections here.</div>}
        </div>
      </div>
    </section>
  );
}

export default HistoryChart;
