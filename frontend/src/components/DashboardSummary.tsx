import * as echarts from 'echarts';
import { useEffect, useRef, useState } from 'react';
import type { DashboardSummary as DashboardSummaryType, SummaryMetric } from '../types';

interface DashboardSummaryProps {
  summary?: DashboardSummaryType;
}

type ProductionMode = 'shift' | 'job' | 'total';

function Sparkline({
  series,
  colors,
  className
}: {
  series: { name: string; points: [string, number][] }[];
  colors: string[];
  className?: string;
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
        grid: { left: 10, right: 10, top: 12, bottom: 18 },
        xAxis: {
          type: 'time',
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { show: false },
          splitLine: { show: false }
        },
        yAxis: {
          type: 'value',
          show: false,
          scale: true,
          splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.10)' } }
        },
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(15, 23, 42, 0.94)',
          borderColor: 'rgba(148, 163, 184, 0.25)',
          textStyle: { color: '#e5eefb' }
        },
        series: series.map((item) => ({
          name: item.name,
          type: 'line',
          showSymbol: true,
          symbol: 'circle',
          symbolSize: 5,
          smooth: true,
          lineStyle: { width: 2.8 },
          areaStyle: { opacity: 0.10 },
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
  }, [series, colors, hasPoints]);

  useEffect(() => {
    return () => {
      instance.current?.dispose();
      instance.current = null;
    };
  }, []);

  if (!hasPoints) {
    return <div className={className ? `summary-sparkline summary-sparkline-empty ${className}` : 'summary-sparkline summary-sparkline-empty'}>No last-hour trend data</div>;
  }

  return <div ref={ref} className={className ? `summary-sparkline ${className}` : 'summary-sparkline'} />;
}

function metricValue(metric?: SummaryMetric) {
  return metric?.current_value ?? '--';
}

function DashboardSummary({ summary }: DashboardSummaryProps) {
  const [mode, setMode] = useState<ProductionMode>('shift');
  const production = summary?.production?.[mode];

  return (
    <div className="dashboard-summary-grid">
      <section className="summary-card panel-fill">
        <div className="summary-card-header">
          <div>
            <span className="summary-kicker">Machine</span>
            <h2>Speed</h2>
            <small className="summary-trend-label">Last hour trend</small>
          </div>
          <strong className="summary-live-value">{metricValue(summary?.speed)}</strong>
        </div>
        <Sparkline
          series={[{ name: 'Machine Speed', points: summary?.speed?.points ?? [] }]}
          colors={['#38bdf8']}
        />
      </section>

      <section className="summary-card panel-fill">
        <div className="summary-card-header">
          <div>
            <span className="summary-kicker">Production</span>
            <h2>Good / Bad Bags</h2>
            <small className="summary-trend-label">Last hour trend</small>
          </div>
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
        </div>
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
        <Sparkline
          series={[
            { name: 'Good', points: production?.good?.points ?? [] },
            { name: 'Bad', points: production?.bad?.points ?? [] }
          ]}
          colors={['#22c55e', '#ef4444']}
        />
      </section>
    </div>
  );
}

export default DashboardSummary;
