import { useQuery } from '@tanstack/react-query';
import * as echarts from 'echarts';
import { X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { api } from '../api/client';
import type { LiveValue, SavedHistoryVariable } from '../types';

const CHART_COLORS = ['#38bdf8', '#22c55e', '#f59e0b', '#f97316', '#ef4444', '#a78bfa', '#14b8a6', '#f43f5e'];

interface SectionHistoryChartProps {
  machineId: number;
  sectionKey: string | null;
  numericValues: LiveValue[];
  refreshMs: number;
}

interface SavedVariablesChartProps {
  machineId: number;
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

function useAutoUpdatingRange(enabled: boolean, refreshMs: number) {
  const [range, setRange] = useState(defaultRange);

  useEffect(() => {
    if (!enabled) return;
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
  }, [enabled, refreshMs]);

  return { range, setRange };
}

function useChart(
  ref: RefObject<HTMLDivElement | null>,
  loading: boolean,
  enabled: boolean,
  series: Array<{ label: string; points: [string, number][] }>,
  titlePrefix?: string
) {
  const instance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    if (!instance.current) {
      instance.current = echarts.init(ref.current);
    }
    const chart = instance.current;
    if (loading) {
      chart.showLoading('default', {
        text: 'Loading trends...',
        color: '#38bdf8',
        textColor: '#cbd5e1',
        maskColor: 'rgba(15, 23, 42, 0.45)'
      });
    } else {
      chart.hideLoading();
    }
    if (!enabled) {
      chart.clear();
      return;
    }
    chart.clear();
    chart.setOption(buildChartOption(series, titlePrefix), { notMerge: true });
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    resize();
    return () => window.removeEventListener('resize', resize);
  }, [ref, loading, enabled, series, titlePrefix]);

  useEffect(() => {
    return () => {
      instance.current?.dispose();
      instance.current = null;
    };
  }, []);
}

function HistoryChart({ machineId, sectionKey, numericValues, refreshMs }: SectionHistoryChartProps) {
  const mainChartRef = useRef<HTMLDivElement | null>(null);
  const { range, setRange } = useAutoUpdatingRange(Boolean(sectionKey), refreshMs);
  const tagIds = useMemo(() => numericValues.map((row) => row.tag_id).sort((a, b) => a - b), [numericValues]);

  const mainHistoryQuery = useQuery({
    queryKey: ['history', 'main', machineId, sectionKey, range.start, range.end, tagIds.join(',')],
    queryFn: () => api.getHistory(machineId, inputToQueryDateTime(range.start), inputToQueryDateTime(range.end), tagIds, sectionKey),
    enabled: Boolean(sectionKey && tagIds.length),
    staleTime: 10_000
  });

  const mainSeries = useMemo(
    () =>
      (mainHistoryQuery.data?.series ?? []).filter((series) => tagIds.includes(series.tag_id)).map((series) => ({
        label: series.label,
        points: series.points
      })),
    [mainHistoryQuery.data, tagIds]
  );

  const hasMainSeriesData = useMemo(() => mainSeries.some((series) => series.points.length > 0), [mainSeries]);

  useChart(mainChartRef, mainHistoryQuery.isFetching, Boolean(tagIds.length), mainSeries);

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
          <p>Section: {sectionKey}. Use the live variable show controls to add or remove trend lines here.</p>
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

      <div className="history-body history-body-single">
        <div className="chart-stage">
          {mainHistoryQuery.isError && <div className="chart-message">{(mainHistoryQuery.error as Error).message}</div>}
          {!tagIds.length && <div className="chart-message">Show one or more numeric live variables to chart them here.</div>}
          {!mainHistoryQuery.isError && tagIds.length > 0 && mainHistoryQuery.data && !hasMainSeriesData && (
            <div className="chart-message">No history data found for the shown variables and time range.</div>
          )}
          <div ref={mainChartRef} className="echart history-main-echart" />
        </div>
      </div>
    </section>
  );
}

export function SavedVariablesChart({
  machineId,
  refreshMs,
  savedVariables,
  onRemoveSavedVariable,
  onClearSavedVariables
}: SavedVariablesChartProps) {
  const compareChartRef = useRef<HTMLDivElement | null>(null);
  const { range, setRange } = useAutoUpdatingRange(true, refreshMs);
  const savedTagIds = useMemo(() => savedVariables.map((item) => item.tag_id).sort((a, b) => a - b), [savedVariables]);

  const compareHistoryQuery = useQuery({
    queryKey: ['history', 'compare', machineId, range.start, range.end, savedTagIds.join(',')],
    queryFn: () => api.getHistory(machineId, inputToQueryDateTime(range.start), inputToQueryDateTime(range.end), savedTagIds),
    enabled: Boolean(savedTagIds.length),
    staleTime: 10_000
  });

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

  const hasCompareSeriesData = useMemo(() => compareSeries.some((series) => series.points.length > 0), [compareSeries]);

  useChart(compareChartRef, compareHistoryQuery.isFetching, Boolean(savedVariables.length), compareSeries, 'Saved comparison');

  return (
    <section className="history-panel history-saved-panel panel-fill">
      <div className="panel-title-row history-saved-header">
        <div>
          <h2>Saved Variables</h2>
          <p>Use saved variables for troubleshooting and compare values from different sections together.</p>
        </div>
      </div>
      <div className="history-chip-bar history-chip-bar-standalone">
        <div className="history-chip-header">
          <h3>Saved Comparison Set</h3>
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
          {!savedVariables.length && (
            <div className="empty-state small">Save variables from live values to build a cross-section troubleshooting view here.</div>
          )}
        </div>
      </div>

      <div className="history-compare-block">
        <div className="panel-title-row history-compare-header">
          <div>
            <h2>Saved Comparison Trends</h2>
            <p>Trend the saved troubleshooting variables independently from the selected section history.</p>
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
    </section>
  );
}

export default HistoryChart;
