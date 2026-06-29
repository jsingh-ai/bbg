import { useQuery } from '@tanstack/react-query';
import * as echarts from 'echarts';
import { X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { api } from '../api/client';
import { readThemeColor, type ThemeMode } from '../hooks/useTheme';
import type { LiveValue, SavedHistoryVariable } from '../types';

export const MAX_SECTION_HISTORY_TRENDS = 15;
export const MAX_SAVED_COMPARISON_TRENDS = 25;

const CHART_COLORS = ['#38bdf8', '#22c55e', '#f59e0b', '#f97316', '#ef4444', '#a78bfa', '#14b8a6', '#f43f5e'];

interface SectionHistoryChartProps {
  machineId: number;
  sectionKey: string | null;
  numericValues: LiveValue[];
  refreshMs: number;
  theme: ThemeMode;
}

interface SavedVariablesChartProps {
  machineId: number;
  refreshMs: number;
  theme: ThemeMode;
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
  theme: ThemeMode,
  titlePrefix?: string
): echarts.EChartsOption {
  const tooltipBackground = readThemeColor('--chart-tooltip-bg', theme === 'light' ? 'rgba(248, 250, 252, 0.96)' : 'rgba(15, 23, 42, 0.94)');
  const tooltipBorder = readThemeColor('--chart-tooltip-border', 'rgba(148, 163, 184, 0.25)');
  const textStrong = readThemeColor('--chart-text-strong', theme === 'light' ? '#0f172a' : '#e5eefb');
  const textMuted = readThemeColor('--chart-text-muted', theme === 'light' ? '#475569' : '#cbd5e1');
  const axisText = readThemeColor('--chart-axis-text', theme === 'light' ? '#64748b' : '#94a3b8');
  const axisName = readThemeColor('--chart-axis-name', theme === 'light' ? '#64748b' : '#64748b');
  const axisLine = readThemeColor('--chart-axis-line', theme === 'light' ? 'rgba(100, 116, 139, 0.34)' : 'rgba(148, 163, 184, 0.35)');
  const gridLine = readThemeColor('--chart-grid-line', theme === 'light' ? 'rgba(148, 163, 184, 0.18)' : 'rgba(148, 163, 184, 0.10)');
  const zoomBackground = readThemeColor('--chart-zoom-bg', theme === 'light' ? 'rgba(226, 232, 240, 0.9)' : 'rgba(15, 23, 42, 0.55)');
  const zoomFill = readThemeColor('--chart-zoom-fill', theme === 'light' ? 'rgba(56, 189, 248, 0.22)' : 'rgba(56, 189, 248, 0.18)');
  return {
    animation: false,
    color: CHART_COLORS,
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: tooltipBackground,
      borderColor: tooltipBorder,
      textStyle: { color: textStrong }
    },
    legend: {
      top: 0,
      type: 'scroll',
      data: data.map((series) => series.label),
      selected: Object.fromEntries(data.map((series) => [series.label, true])),
      textStyle: { color: textMuted },
      inactiveColor: axisName,
      pageTextStyle: { color: textMuted }
    },
    grid: { left: 56, right: 24, top: 56, bottom: 46 },
    xAxis: {
      type: 'time',
      name: titlePrefix,
      nameLocation: 'middle',
      nameGap: 34,
      axisLine: { lineStyle: { color: axisLine } },
      splitLine: { lineStyle: { color: gridLine } },
      axisLabel: { color: axisText },
      nameTextStyle: { color: axisName }
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: { lineStyle: { color: axisLine } },
      splitLine: { lineStyle: { color: gridLine } },
      axisLabel: { color: axisText }
    },
    dataZoom: [
      { type: 'inside' },
      {
        type: 'slider',
        height: 18,
        bottom: 8,
        borderColor: tooltipBorder,
        backgroundColor: zoomBackground,
        fillerColor: zoomFill,
        moveHandleStyle: { color: '#38bdf8' },
        textStyle: { color: axisText }
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
  theme: ThemeMode,
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
    chart.setOption(buildChartOption(series, theme, titlePrefix), { notMerge: true });
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    resize();
    return () => window.removeEventListener('resize', resize);
  }, [ref, loading, enabled, series, theme, titlePrefix]);

  useEffect(() => {
    return () => {
      instance.current?.dispose();
      instance.current = null;
    };
  }, []);
}

function HistoryChart({ machineId, sectionKey, numericValues, refreshMs, theme }: SectionHistoryChartProps) {
  const mainChartRef = useRef<HTMLDivElement | null>(null);
  const tagIds = useMemo(() => numericValues.map((row) => row.tag_id).sort((a, b) => a - b), [numericValues]);
  const exceedsTrendLimit = tagIds.length > MAX_SECTION_HISTORY_TRENDS;
  const historyEnabled = Boolean(sectionKey && tagIds.length && !exceedsTrendLimit);
  const { range, setRange } = useAutoUpdatingRange(historyEnabled, refreshMs);

  const mainHistoryQuery = useQuery({
    queryKey: ['history', 'main', machineId, sectionKey, range.start, range.end, tagIds.join(',')],
    queryFn: () => api.getHistory(machineId, inputToQueryDateTime(range.start), inputToQueryDateTime(range.end), tagIds, sectionKey),
    enabled: historyEnabled,
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

  useChart(mainChartRef, mainHistoryQuery.isFetching, historyEnabled, mainSeries, theme);

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
      <div className="panel-title-row panel-header history-header">
        <div className="panel-title-block">
          <span className="panel-eyebrow">History</span>
          <h2 className="panel-title">Historical Trends</h2>
          <p className="panel-subtitle">Trend of live values.</p>
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

      <div className="panel-body history-panel-body">
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
      </div>
    </section>
  );
}

export function SavedVariablesChart({
  machineId,
  refreshMs,
  theme,
  savedVariables,
  onRemoveSavedVariable,
  onClearSavedVariables
}: SavedVariablesChartProps) {
  const compareChartRef = useRef<HTMLDivElement | null>(null);
  const savedTagIds = useMemo(() => savedVariables.map((item) => item.tag_id).sort((a, b) => a - b), [savedVariables]);
  const exceedsTrendLimit = savedTagIds.length > MAX_SAVED_COMPARISON_TRENDS;
  const historyEnabled = Boolean(savedTagIds.length && !exceedsTrendLimit);
  const { range, setRange } = useAutoUpdatingRange(historyEnabled, refreshMs);

  const compareHistoryQuery = useQuery({
    queryKey: ['history', 'compare', machineId, range.start, range.end, savedTagIds.join(',')],
    queryFn: () => api.getHistory(machineId, inputToQueryDateTime(range.start), inputToQueryDateTime(range.end), savedTagIds),
    enabled: historyEnabled,
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

  useChart(compareChartRef, compareHistoryQuery.isFetching, historyEnabled, compareSeries, theme, 'Saved comparison');

  return (
    <section className="history-panel history-saved-panel panel-fill">
      <div className="panel-title-row panel-header history-saved-header">
        <div className="panel-title-block">
          <span className="panel-eyebrow">Troubleshooting</span>
          <h2 className="panel-title">Saved Variables</h2>
          <p className="panel-subtitle">Use saved variables to compare values from different sections.</p>
        </div>
      </div>
      <div className="panel-body history-saved-body">
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
              {exceedsTrendLimit && (
                <div className="chart-message">
                  Saved comparison has {savedTagIds.length} variables. Remove variables until 25 or fewer are saved to load historical trends.
                </div>
              )}
              {!compareHistoryQuery.isError && compareHistoryQuery.data && !hasCompareSeriesData && (
                <div className="chart-message">No history data found for the saved comparison variables.</div>
              )}
              <div ref={compareChartRef} className="echart compare-echart" />
            </div>
            <div className="compare-table-wrap">
              <table className="value-table compare-table">
                <thead>
                  <tr>
                    <th className="action-col" aria-label="Remove saved variable column"></th>
                    <th>Section</th>
                    <th>Variable</th>
                    <th>Current Value</th>
                  </tr>
                </thead>
                <tbody>
                  {savedVariables.map((item) => (
                    <tr key={item.tag_id}>
                      <td className="action-col">
                        <button className="icon-button" onClick={() => onRemoveSavedVariable(item.tag_id)} title="Remove saved variable">
                          <X size={16} />
                        </button>
                      </td>
                      <td>{item.section_key}</td>
                      <td>{item.label}</td>
                      <td className="current-value-cell"><span className="current-value-pill">{item.current_value}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default HistoryChart;
