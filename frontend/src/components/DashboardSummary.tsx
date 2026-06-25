import { useQuery } from '@tanstack/react-query';
import * as echarts from 'echarts';
import { Maximize2, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { api } from '../api/client';
import type { DashboardSummary as DashboardSummaryType, HistorySeries, SummaryMetric } from '../types';

interface DashboardSummaryProps {
  machineId: number;
  summary?: DashboardSummaryType;
}

type ProductionMode = 'shift' | 'job' | 'total';
type ExpandedMetric = 'speed' | 'production';
type TooltipValue = string | number | Date | null | undefined;

function toLocalInputValue(date: Date) {
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60_000);
  return local.toISOString().slice(0, 16);
}

function inputToQueryDateTime(value: string) {
  return value.length === 16 ? `${value}:00` : value;
}

function defaultExpandedRange() {
  const end = new Date();
  const start = new Date(end.getTime() - 60 * 60_000);
  return { start: toLocalInputValue(start), end: toLocalInputValue(end) };
}

function formatTooltipValue(value: TooltipValue | TooltipValue[]) {
  if (Array.isArray(value)) {
    const lastValue = value[value.length - 1];
    return lastValue == null ? '--' : `${lastValue}`;
  }
  if (typeof value === 'number') {
    return value.toLocaleString();
  }
  return value == null ? '--' : `${value}`;
}

function buildExpandedChartOption(data: Array<{ label: string; points: [string, number][] }>, title: string, yAxisName: string): echarts.EChartsOption {
  return {
    animation: false,
    color: ['#38bdf8', '#22c55e', '#ef4444'],
    backgroundColor: 'transparent',
    title: {
      text: title,
      left: 0,
      textStyle: {
        color: '#e5eefb',
        fontSize: 16,
        fontWeight: 700
      }
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15, 23, 42, 0.96)',
      borderColor: 'rgba(148, 163, 184, 0.28)',
      textStyle: { color: '#e5eefb' },
      valueFormatter: formatTooltipValue
    },
    legend: {
      top: 34,
      type: 'scroll',
      data: data.map((series) => series.label),
      textStyle: { color: '#cbd5e1' },
      inactiveColor: '#64748b',
      pageTextStyle: { color: '#cbd5e1' }
    },
    grid: { left: 64, right: 28, top: 84, bottom: 58 },
    xAxis: {
      type: 'time',
      name: 'Timestamp',
      nameLocation: 'middle',
      nameGap: 36,
      axisLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.35)' } },
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.10)' } },
      nameTextStyle: { color: '#64748b' }
    },
    yAxis: {
      type: 'value',
      name: yAxisName,
      nameLocation: 'middle',
      nameGap: 50,
      scale: true,
      axisLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.35)' } },
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.10)' } },
      nameTextStyle: { color: '#64748b' }
    },
    dataZoom: [
      { type: 'inside' },
      {
        type: 'slider',
        height: 18,
        bottom: 14,
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
      smooth: true,
      lineStyle: { width: 2.8 },
      emphasis: { focus: 'series' },
      data: series.points
    }))
  };
}

function Sparkline({
  series,
  colors,
  className,
  yAxisName
}: {
  series: { name: string; points: [string, number][] }[];
  colors: string[];
  className?: string;
  yAxisName?: string;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const instance = useRef<echarts.ECharts | null>(null);
  const hasPoints = series.some((item) => item.points.length > 0);

  useEffect(() => {
    if (!ref.current) return;
    if (!instance.current) {
      instance.current = echarts.init(ref.current);
    }
    const chart = instance.current;
    if (!hasPoints) {
      chart.clear();
      return;
    }
    chart.setOption(
      {
        animation: false,
        color: colors,
        backgroundColor: 'transparent',
        grid: { left: 46, right: 14, top: 16, bottom: 30 },
        xAxis: {
          type: 'time',
          axisLine: { show: true, lineStyle: { color: 'rgba(148, 163, 184, 0.24)' } },
          axisTick: { show: false },
          axisLabel: {
            show: true,
            color: '#94a3b8',
            fontSize: 10,
            hideOverlap: true,
            formatter: (value: number) =>
              new Date(value).toLocaleTimeString([], {
                hour: 'numeric',
                minute: '2-digit'
              })
          },
          splitLine: { show: false }
        },
        yAxis: {
          type: 'value',
          name: yAxisName,
          nameLocation: 'middle',
          nameGap: 34,
          nameTextStyle: {
            color: '#94a3b8',
            fontSize: 10,
            padding: [0, 0, 8, 0]
          },
          scale: true,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            show: true,
            color: '#94a3b8',
            fontSize: 10
          },
          splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.10)' } }
        },
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(15, 23, 42, 0.94)',
          borderColor: 'rgba(148, 163, 184, 0.25)',
          textStyle: { color: '#e5eefb' },
          valueFormatter: formatTooltipValue
        },
        series: series.map((item) => ({
          name: item.name,
          type: 'line',
          showSymbol: true,
          symbol: 'circle',
          symbolSize: 5,
          smooth: true,
          lineStyle: { width: 2.8 },
          areaStyle: { opacity: 0.1 },
          endLabel: { show: false },
          data: item.points
        }))
      },
      { notMerge: true }
    );
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    resize();
    return () => window.removeEventListener('resize', resize);
  }, [series, colors, hasPoints, yAxisName]);

  useEffect(() => {
    return () => {
      instance.current?.dispose();
      instance.current = null;
    };
  }, []);

  if (!hasPoints) {
    return <div className={className ? `summary-sparkline summary-sparkline-empty ${className}` : 'summary-sparkline summary-sparkline-empty'}>No recent last-hour data</div>;
  }

  return <div ref={ref} className={className ? `summary-sparkline ${className}` : 'summary-sparkline'} />;
}

function metricValue(metric?: SummaryMetric) {
  return metric?.current_value ?? '--';
}

function metricNumber(metric?: SummaryMetric) {
  const value = metric?.value_num;
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function formatPercent(value?: number) {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)}%` : '--';
}

function ExpandedTrendModal({
  open,
  title,
  yAxisName,
  series,
  loading,
  error,
  range,
  onRangeChange,
  onClose
}: {
  open: boolean;
  title: string;
  yAxisName: string;
  series: HistorySeries[];
  loading: boolean;
  error?: Error | null;
  range: { start: string; end: string };
  onRangeChange: Dispatch<SetStateAction<{ start: string; end: string }>>;
  onClose: () => void;
}) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);
  const chartData = useMemo(() => series.map((item) => ({ label: item.label, points: item.points })), [series]);
  const hasData = chartData.some((item) => item.points.length > 0);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) {
      chartInstance.current?.dispose();
      chartInstance.current = null;
      return;
    }
  }, [open]);

  useEffect(() => {
    if (!open || !chartRef.current) return;
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }
    const chart = chartInstance.current;
    if (loading) {
      chart.showLoading('default', {
        text: 'Loading trend...',
        color: '#38bdf8',
        textColor: '#cbd5e1',
        maskColor: 'rgba(15, 23, 42, 0.45)'
      });
    } else {
      chart.hideLoading();
    }
    chart.clear();
    if (hasData) {
      chart.setOption(buildExpandedChartOption(chartData, title, yAxisName), { notMerge: true });
    }
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    resize();
    return () => window.removeEventListener('resize', resize);
  }, [open, loading, chartData, title, yAxisName, hasData]);

  useEffect(() => {
    return () => {
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
  }, []);

  if (!open) return null;

  return (
    <div className="trend-modal-overlay" onClick={onClose} role="presentation">
      <div className="trend-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
        <div className="trend-modal-header">
          <div>
            <span className="summary-kicker">Expanded Trend</span>
            <h2>{title}</h2>
            <p>Configure a custom time window without changing the one-hour summary cards.</p>
          </div>
          <button className="icon-button trend-modal-close" onClick={onClose} aria-label="Close expanded trend">
            <X size={18} />
          </button>
        </div>
        <div className="trend-modal-controls">
          <label>
            Start
            <input type="datetime-local" value={range.start} onChange={(event) => onRangeChange((prev) => ({ ...prev, start: event.target.value }))} />
          </label>
          <label>
            End
            <input type="datetime-local" value={range.end} onChange={(event) => onRangeChange((prev) => ({ ...prev, end: event.target.value }))} />
          </label>
        </div>
        <div className="trend-modal-body">
          {error && <div className="chart-message trend-modal-message">{error.message}</div>}
          {!error && !loading && !hasData && <div className="chart-message trend-modal-message">No data found for the selected time range.</div>}
          <div ref={chartRef} className="trend-modal-chart" />
        </div>
      </div>
    </div>
  );
}

function DashboardSummary({ machineId, summary }: DashboardSummaryProps) {
  const [mode, setMode] = useState<ProductionMode>('shift');
  const [expandedMetric, setExpandedMetric] = useState<ExpandedMetric | null>(null);
  const [expandedRange, setExpandedRange] = useState(defaultExpandedRange);
  const production = summary?.production?.[mode];
  const uptime = summary?.uptime;
  const speedValue = metricNumber(summary?.speed);
  const speedPct = speedValue === null ? 0 : Math.max(0, Math.min(100, (speedValue / 150) * 100));

  const expandedTagIds = useMemo(() => {
    if (expandedMetric === 'speed') {
      return summary?.speed?.tag_id ? [summary.speed.tag_id] : [];
    }
    if (expandedMetric === 'production') {
      return [production?.good?.tag_id, production?.bad?.tag_id].filter((tagId): tagId is number => typeof tagId === 'number');
    }
    return [];
  }, [expandedMetric, summary, production]);

  const expandedTrendQuery = useQuery({
    queryKey: ['summary-expanded-history', machineId, expandedMetric, mode, expandedRange.start, expandedRange.end, expandedTagIds.join(',')],
    queryFn: () => api.getHistory(machineId, inputToQueryDateTime(expandedRange.start), inputToQueryDateTime(expandedRange.end), expandedTagIds),
    enabled: Boolean(expandedMetric && expandedTagIds.length)
  });

  const expandedSeries = useMemo(() => {
    if (expandedMetric === 'speed') {
      return (expandedTrendQuery.data?.series ?? []).map((series) => ({ ...series, label: 'Machine Speed' }));
    }
    if (expandedMetric === 'production') {
      return (expandedTrendQuery.data?.series ?? []).map((series) => ({
        ...series,
        label: series.tag_id === production?.good?.tag_id ? 'Good' : series.tag_id === production?.bad?.tag_id ? 'Bad' : series.label
      }));
    }
    return [];
  }, [expandedMetric, expandedTrendQuery.data, production]);

  const expandedTitle = expandedMetric === 'speed' ? 'Machine Speed Trend' : `Production Trend - ${mode[0].toUpperCase()}${mode.slice(1)}`;
  const expandedYAxisName = expandedMetric === 'speed' ? 'Speed' : 'Bags';

  return (
    <>
      <div className="dashboard-summary-grid">
        <section className="summary-card panel-fill">
          <div className="summary-card-header panel-header">
            <div className="panel-title-block">
              <span className="summary-kicker panel-eyebrow">Production</span>
              <h2 className="panel-title">Good / Bad Bags</h2>
              <small className="summary-trend-label panel-subtitle">Last Hour Trend</small>
            </div>
            <div className="summary-card-actions panel-actions">
              <div className="summary-mode-toggle">
                {(['shift', 'job', 'total'] as ProductionMode[]).map((item) => (
                  <button
                    key={item}
                    className={mode === item ? 'summary-mode-button active' : 'summary-mode-button'}
                    onClick={() => setMode(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
              <button className="secondary-button small-button" onClick={() => setExpandedMetric('production')}>
                <Maximize2 size={14} /> Expand
              </button>
            </div>
          </div>
          <div className="panel-body summary-card-body">
            <div className="summary-production-layout">
              <div className="summary-production-values">
                <div className="summary-production-pill good">
                  <span>Good</span>
                  <strong>{metricValue(production?.good)}</strong>
                </div>
                <div className="summary-production-pill bad">
                  <span>Bad</span>
                  <strong>{metricValue(production?.bad)}</strong>
                </div>
              </div>
              <div className="summary-production-trend">
                <Sparkline
                  series={[
                    { name: 'Good', points: production?.good?.points ?? [] },
                    { name: 'Bad', points: production?.bad?.points ?? [] }
                  ]}
                  colors={['#22c55e', '#ef4444']}
                  yAxisName="Bags"
                />
              </div>
            </div>
          </div>
        </section>

        <section className="summary-card panel-fill">
          <div className="summary-card-header panel-header">
            <div className="panel-title-block">
              <span className="summary-kicker panel-eyebrow">Machine</span>
              <h2 className="panel-title">Speed</h2>
              <small className="summary-trend-label panel-subtitle">Last Hour Trend</small>
            </div>
            <button className="secondary-button small-button" onClick={() => setExpandedMetric('speed')}>
              <Maximize2 size={14} /> Expand
            </button>
          </div>
          <div className="panel-body summary-card-body">
            <div className="summary-speed-layout">
              <div className="summary-speed-kpi">
                <span className="summary-speed-value">{metricValue(summary?.speed)}</span>
                <div className="summary-speed-scale">
                  <div className="summary-speed-scale-fill" style={{ width: `${speedPct}%` }} />
                </div>
                <div className="summary-speed-range">
                  <span>0</span>
                  <span>150</span>
                </div>
              </div>
              <div className="summary-speed-trend">
                <Sparkline
                  series={[{ name: 'Machine Speed', points: summary?.speed?.points ?? [] }]}
                  colors={['#38bdf8']}
                  yAxisName="Speed"
                />
              </div>
            </div>
          </div>
        </section>

        <section className="summary-card panel-fill">
          <div className="summary-card-header panel-header">
            <div className="panel-title-block">
              <span className="summary-kicker panel-eyebrow">Availability</span>
              <h2 className="panel-title">Uptime</h2>
              <small className="summary-trend-label panel-subtitle">Last 24 Hr</small>
            </div>
          </div>
          <div className="panel-body summary-card-body">
            <div className="summary-uptime-layout">
              <div className="summary-uptime-kpi">
                <span className="summary-uptime-pct">{formatPercent(uptime?.uptime_pct)}</span>
                <span className="summary-uptime-caption">Machine uptime</span>
              </div>
              <div className="summary-uptime-breakdown">
                <div className="summary-uptime-row online">
                  <span>Online</span>
                  <strong>{uptime?.online_minutes ?? 0} min</strong>
                </div>
                <div className="summary-uptime-row offline">
                  <span>Offline</span>
                  <strong>{uptime?.offline_minutes ?? 0} min</strong>
                </div>
                <div className="summary-uptime-row down">
                  <span>Down</span>
                  <strong>{uptime?.down_minutes ?? 0} min</strong>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <ExpandedTrendModal
        open={expandedMetric !== null}
        title={expandedTitle}
        yAxisName={expandedYAxisName}
        series={expandedSeries}
        loading={expandedTrendQuery.isFetching}
        error={expandedTrendQuery.isError ? (expandedTrendQuery.error as Error) : null}
        range={expandedRange}
        onRangeChange={setExpandedRange}
        onClose={() => setExpandedMetric(null)}
      />
    </>
  );
}

export default DashboardSummary;
