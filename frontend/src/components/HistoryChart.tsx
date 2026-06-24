import { useQuery } from '@tanstack/react-query';
import * as echarts from 'echarts';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/client';
import type { LiveValue } from '../types';

interface HistoryChartProps {
  machineId: number;
  sectionKey: string | null;
  numericValues: LiveValue[];
}

function toLocalInputValue(date: Date) {
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60_000);
  return local.toISOString().slice(0, 16);
}

function inputToIso(value: string) {
  return new Date(value).toISOString().slice(0, 19);
}

function defaultRange() {
  const end = new Date();
  const start = new Date(end.getTime() - 60 * 60_000);
  return { start: toLocalInputValue(start), end: toLocalInputValue(end) };
}

function HistoryChart({ machineId, sectionKey, numericValues }: HistoryChartProps) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);
  const [range, setRange] = useState(defaultRange);
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([]);

  useEffect(() => {
    const defaultIds = numericValues
      .filter((row) => Boolean(row.show_in_history_default))
      .slice(0, 8)
      .map((row) => row.tag_id);
    setSelectedTagIds(defaultIds);
  }, [sectionKey, numericValues]);

  const tagIds = useMemo(() => selectedTagIds.slice().sort((a, b) => a - b), [selectedTagIds]);

  const historyQuery = useQuery({
    queryKey: ['history', machineId, sectionKey, range.start, range.end, tagIds.join(',')],
    queryFn: () => api.getHistory(machineId, sectionKey as string, inputToIso(range.start), inputToIso(range.end), tagIds),
    enabled: Boolean(sectionKey && tagIds.length),
    staleTime: 10_000
  });

  useEffect(() => {
    if (!chartRef.current) return;
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }
    const chart = chartInstance.current;
    const data = historyQuery.data?.series ?? [];
    chart.setOption({
      animation: false,
      tooltip: { trigger: 'axis' },
      legend: { top: 0, type: 'scroll' },
      grid: { left: 48, right: 24, top: 48, bottom: 46 },
      xAxis: { type: 'time' },
      yAxis: { type: 'value', scale: true },
      dataZoom: [
        { type: 'inside' },
        { type: 'slider', height: 18, bottom: 8 }
      ],
      series: data.map((series) => ({
        name: series.label,
        type: 'line',
        showSymbol: false,
        connectNulls: false,
        data: series.points
      }))
    });
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    resize();
    return () => window.removeEventListener('resize', resize);
  }, [historyQuery.data]);

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
      <div className="panel-title-row">
        <div>
          <h2>Historical Trends</h2>
          <p>Section: {sectionKey}</p>
        </div>
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
          {numericValues.map((row) => (
            <label className="check-row" key={row.tag_id}>
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
          {historyQuery.isError && <div className="chart-message">{(historyQuery.error as Error).message}</div>}
          {!selectedTagIds.length && <div className="chart-message">Select one or more variables to chart.</div>}
          <div ref={chartRef} className="echart" />
        </div>
      </div>
    </section>
  );
}

export default HistoryChart;
