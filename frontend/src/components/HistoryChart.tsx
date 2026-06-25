import { useQuery } from '@tanstack/react-query';
import * as echarts from 'echarts';
import { X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
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

function buildChartOption(
  data: Array<{ label: string; points: [string, number][] }>,
  titlePrefix?: string
): echarts.EChartsOption {
  return {
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
      data: data.map((series) => series.label),
      selected: Object.fromEntries(data.map((series) => [series.label, true])),
      textStyle: { color: '#cbd5e1' },
      inactiveColor: '#64748b',
      pageTextStyle: { color: '#cbd5e1' }
    },
    grid: { left: 56, right: 24, top: 56, bottom: 46 },
    xAxis: {
      type: 'time',
      name: titlePrefix,
      nameLocation: 'middle',
      nameGap: 34,
      axisLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.35)' } },
      splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.10)' } },
      axisLabel: { color: '#94a3b8' },
      nameTextStyle: { color: '#64748b' }
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
      name: series.label,
      type: 'line',
      showSymbol: false,
      connectNulls: false,
      smooth: true,
      lineStyle: { width: 2.5 },
      emphasis: { focus: 'series' },
      data: series.points
    }))
  };
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
  const mainChartRef = useRef<HTMLDivElement | null>(null);
  const mainChartInstance = useRef<echarts.ECharts | null>(null);
  const compareChartRef = useRef<HTMLDivElement | null>(null);
  const compareChartInstance = useRef<echarts.ECharts | null>(null);
  const [range, setRange] = useState(defaultRange);
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([]);

  useEffect(() => {
    const preferred = numericValues.filter((row) => Boolean(row.show_in_history_default));
    const source = preferred.length ? preferred : numericValues;
    setSelectedTagIds(source.slice(0, 8).map((row) => row.tag_id));
  }, [sectionKey, numericValues]);

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
  const savedTagIds = useMemo(() => savedVariables.map((item) => item.tag_id).sort((a, b) => a - b), [savedVariables]);

  const mainHistoryQuery = useQuery({
    queryKey: ['history', 'main', machineId, sectionKey, range.start, range.end, tagIds.join(',')],
    queryFn: () => api.getHistory(machineId, inputToQueryDateTime(range.start), inputToQueryDateTime(range.end), tagIds, sectionKey),
    enabled: Boolean(sectionKey && tagIds.length),
    staleTime: 10_000
  });

  const compareHistoryQuery = useQuery({
    queryKey: ['history', 'compare', machineId, range.start, range.end, savedTagIds.join(',')],
    queryFn: () => api.getHistory(machineId, inputToQueryDateTime(range.start), inputToQueryDateTime(range.end), savedTagIds),
    enabled: Boolean(savedTagIds.length),
    staleTime: 10_000
  });

  const mainSeries = useMemo(
    () =>
      (mainHistoryQuery.data?.series ?? []).filter((series) => selectedTagIds.includes(series.tag_id)).map((series) => ({
        label: series.label,
        points: series.points
      })),
    [mainHistoryQuery.data, selectedTagIds]
  );

  const compareSeries = useMemo(
    () =>
      (compareHistoryQuery.data?.series ?? []).map((series) => {
        const saved = savedVariables.find((item) => item.tag_id === series.tag_id);
        return {
          label: saved ? `${saved.section_key} - ${saved.label}` : `${series.section_key ?? ''} - ${series.label}`.trim(),
          points: series.points
        };
      }),
    [compareHistoryQuery.data, savedVariables]
  );

  const hasMainSeriesData = useMemo(() => mainSeries.some((series) => series.points.length > 0), [mainSeries]);
  const hasCompareSeriesData = useMemo(() => compareSeries.some((series) => series.points.length > 0), [compareSeries]);

  useEffect(() => {
    if (!mainChartRef.current) return;
    if (!mainChartInstance.current) {
      mainChartInstance.current = echarts.init(mainChartRef.current);
    }
    const chart = mainChartInstance.current;
    if (mainHistoryQuery.isFetching) {
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
    chart.setOption(buildChartOption(mainSeries), { notMerge: true });
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    resize();
    return () => window.removeEventListener('resize', resize);
  }, [mainHistoryQuery.isFetching, mainSeries, selectedTagIds]);

  useEffect(() => {
    if (!savedVariables.length || !compareChartRef.current) return;
    if (!compareChartInstance.current) {
      compareChartInstance.current = echarts.init(compareChartRef.current);
    }
    const chart = compareChartInstance.current;
    if (compareHistoryQuery.isFetching) {
      chart.showLoading('default', {
        text: 'Loading saved comparisons...',
        color: '#38bdf8',
        textColor: '#cbd5e1',
        maskColor: 'rgba(15, 23, 42, 0.45)'
      });
    } else {
      chart.hideLoading();
    }
    chart.clear();
    chart.setOption(buildChartOption(compareSeries, 'Saved comparison'), { notMerge: true });
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    resize();
    return () => window.removeEventListener('resize', resize);
  }, [compareHistoryQuery.isFetching, compareSeries, savedVariables.length]);

  useEffect(() => {
    return () => {
      mainChartInstance.current?.dispose();
      mainChartInstance.current = null;
      compareChartInstance.current?.dispose();
      compareChartInstance.current = null;
    };
  }, []);

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
          {numericValues.map((row) => (
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
              <span>{row.label}</span>
            </label>
          ))}
          {!numericValues.length && <p className="empty-state small">No numeric visible variables found for this section.</p>}
        </aside>
        <div className="chart-stage">
          {mainHistoryQuery.isError && <div className="chart-message">{(mainHistoryQuery.error as Error).message}</div>}
          {!selectedTagIds.length && <div className="chart-message">Select one or more variables to chart.</div>}
          {!mainHistoryQuery.isError && selectedTagIds.length > 0 && mainHistoryQuery.data && !hasMainSeriesData && (
            <div className="chart-message">No history data found for the selected variables and time range.</div>
          )}
          <div ref={mainChartRef} className="echart" />
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

      {savedVariables.length > 0 && (
        <div className="history-compare-block">
          <div className="panel-title-row history-compare-header">
            <div>
              <h2>Saved Comparison Trends</h2>
              <p>Compare saved variables across sections.</p>
            </div>
          </div>
          <div className="history-controls-bar compare-controls-bar">
            <div className="history-controls">
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
          <div className="compare-layout">
            <div className="chart-stage compare-chart-stage">
              {compareHistoryQuery.isError && <div className="chart-message">{(compareHistoryQuery.error as Error).message}</div>}
              {!compareHistoryQuery.isError && compareHistoryQuery.data && !hasCompareSeriesData && (
                <div className="chart-message">No history data found for the saved comparison variables.</div>
              )}
              <div ref={compareChartRef} className="echart compare-echart" />
            </div>
            <div className="compare-table-wrap">
              <table className="value-table compare-table">
                <thead>
                  <tr>
                    <th>Section</th>
                    <th>Variable</th>
                    <th>Current Value</th>
                  </tr>
                </thead>
                <tbody>
                  {savedVariables.map((item) => (
                    <tr key={item.tag_id}>
                      <td>{item.section_key}</td>
                      <td>{item.label}</td>
                      <td className="current-value">{item.current_value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default HistoryChart;
