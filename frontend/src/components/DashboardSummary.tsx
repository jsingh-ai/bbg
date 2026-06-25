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

  useEffect(() => {
    if (!ref.current) return;
    if (!instance.current) {
      instance.current = echarts.init(ref.current);
    }
    const chart = instance.current;
    chart.setOption(
      {
        animation: false,
        color: colors,
        grid: { left: 4, right: 4, top: 8, bottom: 8 },
        xAxis: { type: 'time', show: false },
        yAxis: { type: 'value', show: false, scale: true },
        tooltip: { trigger: 'axis' },
        series: series.map((item) => ({
          name: item.name,
          type: 'line',
          showSymbol: false,
          smooth: true,
          lineStyle: { width: 2.2 },
          areaStyle: { opacity: 0.08 },
          data: item.points
        }))
      },
      { notMerge: true }
    );
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    resize();
    return () => window.removeEventListener('resize', resize);
  }, [series, colors]);

  useEffect(() => {
    return () => {
      instance.current?.dispose();
      instance.current = null;
    };
  }, []);

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
