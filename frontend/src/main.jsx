import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Area, ComposedChart, CartesianGrid, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Activity, ArrowDownRight, ArrowUpRight, CalendarDays, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, Download, RefreshCw, Wind, Zap } from 'lucide-react';
import './style.css';

const API = import.meta.env.VITE_API_URL || '';
const fmt = (n, digits = 0) => n == null || !Number.isFinite(Number(n)) ? '—' : Number(n).toLocaleString('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const dateLabel = (d) => new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });

function App() {
  const [month, setMonth] = useState('2026-01');
  const [supportedMonths, setSupportedMonths] = useState([
    '2025-10',
    '2025-11',
    '2025-12',
    '2026-01',
    '2026-02',
    '2026-03',
  ]);
  const [cutoff, setCutoff] = useState('10');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedDay, setSelectedDay] = useState('2026-01-15');
  const [demand, setDemand] = useState('32000');
  const [tab, setTab] = useState('overview');

  // Settlement periods tab navigation
  const [periodDayFilter, setPeriodDayFilter] = useState('all');
  const [periodPage, setPeriodPage] = useState(1);
  const [showAllInTable, setShowAllInTable] = useState(false);

  // Overview settlement review toggle
  const [showAllOverviewRows, setShowAllOverviewRows] = useState(false);

  const activeRequestId = React.useRef(0);

  // Fetch supported delivery months on mount
  useEffect(() => {
    let isMounted = true;
    fetch(`${API}/api/supported-months`)
      .then(r => r.ok ? r.json() : null)
      .then(res => {
        if (isMounted && res?.supportedMonths?.length) {
          setSupportedMonths(res.supportedMonths);
        }
      })
      .catch(() => {});
    return () => { isMounted = false; };
  }, []);

  const load = async (targetMonth = month, targetCutoff = cutoff, forceRefresh = false) => {
    const reqId = ++activeRequestId.current;
    setLoading(true);
    setError('');
    // Clear data immediately so stale data from the previous month is not shown
    setData(null);

    try {
      const url = `${API}/api/analysis?month=${encodeURIComponent(targetMonth)}&cutoff_hour=${encodeURIComponent(targetCutoff)}${forceRefresh ? '&refresh=true' : ''}`;
      const r = await fetch(url);
      if (reqId !== activeRequestId.current) return;

      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        let msg = `API request failed (${r.status})`;
        if (body.detail) {
          if (typeof body.detail === 'string') {
            msg = body.detail;
          } else if (Array.isArray(body.detail)) {
            msg = body.detail.map(e => e.msg || `${e.loc?.join('.')}: ${e.type}`).join('; ');
          } else {
            msg = JSON.stringify(body.detail);
          }
        }
        throw new Error(msg);
      }
      const json = await r.json();
      if (reqId !== activeRequestId.current) return;
      setData(json);
    } catch (e) {
      if (reqId !== activeRequestId.current) return;
      setError(e.message || 'Could not load Elexon data.');
      setData(null);
    } finally {
      if (reqId === activeRequestId.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    load(month, cutoff);
    setPeriodPage(1);
    setPeriodDayFilter('all');
    setShowAllInTable(false);
  }, [month, cutoff]);

  // When data for a new month arrives, update selectedDay to a valid day in that month
  useEffect(() => {
    if (data?.daily && data.daily.length > 0) {
      const dates = data.daily.map(d => d.date);
      if (!dates.includes(selectedDay)) {
        const mid = dates.find(d => d.endsWith('-15')) || dates[0];
        setSelectedDay(mid);
      }
    }
  }, [data, selectedDay]);

  const monthName = useMemo(() => {
    const cur = data?.month || month;
    const parts = cur.split('-').map(Number);
    if (parts.length === 2 && parts[0] && parts[1]) {
      const d = new Date(Date.UTC(parts[0], parts[1] - 1, 1));
      return d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' });
    }
    return cur;
  }, [data?.month, month]);

  const dataWindowText = useMemo(() => {
    if (data?.daily && data.daily.length > 0) {
      const firstDate = data.daily[0].date;
      const lastDate = data.daily[data.daily.length - 1].date;
      const fDay = firstDate.split('-')[2];
      const lDay = lastDate.split('-')[2];
      return `${fDay}–${lDay} ${monthName}`;
    }
    return monthName;
  }, [data?.daily, monthName]);

  const rows = data?.rows || [];
  const paired = useMemo(() => rows.filter(r => r.actualMW != null && r.forecastMW != null), [rows]);
  const dayRows = useMemo(() => paired.filter(r => r.settlementDate === selectedDay), [paired, selectedDay]);

  const chartRows = useMemo(() => {
    const groups = new Map();
    paired.forEach(r => {
      if (!groups.has(r.settlementDate)) {
        groups.set(r.settlementDate, { date: r.settlementDate, actual: 0, forecast: 0, periods: 0 });
      }
      const g = groups.get(r.settlementDate);
      g.actual += r.actualMW * 0.5;
      g.forecast += r.forecastMW * 0.5;
      g.periods++;
    });
    return [...groups.values()]
      .sort((a, b) => a.date.localeCompare(b.date))
      .map(r => ({
        ...r,
        label: dateLabel(r.date),
        delta: r.forecast - r.actual,
      }));
  }, [paired]);

  const metrics = data?.metrics || {};
  const residual = Math.max(
    0,
    Number(demand || 0) - (dayRows.length ? dayRows.reduce((s, r) => s + (r.forecastMW || 0), 0) / dayRows.length : 0)
  );

  // Settlement periods pagination logic
  const daysList = useMemo(() => {
    const set = new Set(rows.map(r => r.settlementDate));
    return Array.from(set).sort();
  }, [rows]);

  const filteredPeriods = useMemo(() => {
    if (periodDayFilter !== 'all') {
      return rows.filter(r => r.settlementDate === periodDayFilter);
    }
    if (showAllInTable) {
      return rows;
    }
    const startIndex = (periodPage - 1) * 48;
    return rows.slice(startIndex, startIndex + 48);
  }, [rows, periodDayFilter, periodPage, showAllInTable]);

  const totalPages = periodDayFilter === 'all' && !showAllInTable ? Math.ceil(rows.length / 48) || 31 : 1;

  const exportCsv = () => {
    if (!rows.length) return;
    const curMonth = data?.month || month;
    const meta = [
      `# Wind Procurement Intelligence - Forecast Accuracy Backtest`,
      `# Delivery Month: ${curMonth}`,
      `# Decision Cutoff: ${data?.cutoffHourLondon ?? cutoff}:00 Europe/London on D-1`,
      `# Data Source: ${data?.source || 'Elexon BMRS Insights API'}`,
      `# Generated At: ${data?.generatedAt || new Date().toISOString()}`,
      `# Accuracy Metrics: MAE=${data?.metrics?.maeMW != null ? data.metrics.maeMW.toFixed(2) : '—'} MW | RMSE=${data?.metrics?.rmseMW != null ? data.metrics.rmseMW.toFixed(2) : '—'} MW | Bias=${data?.metrics?.biasMW != null ? data.metrics.biasMW.toFixed(2) : '—'} MW | WAPE=${data?.metrics?.wapePercent != null ? data.metrics.wapePercent.toFixed(2) : '—'}%`,
      `# Matched Coverage: ${data?.counts?.pairedPeriods ?? rows.length} / ${data?.counts?.expectedPeriods ?? rows.length} settlement periods`,
    ];
    const cols = [
      'startTimeUtc',
      'localTimeLondon',
      'settlementDate',
      'settlementPeriod',
      'forecastMW',
      'actualMW',
      'errorMW',
      'absoluteErrorMW',
      'publishTimeUtc',
      'cutoffHourLondon'
    ];
    const dataLines = rows.map(r => [
      r.startTime ?? '',
      r.localTime ?? '',
      r.settlementDate ?? '',
      r.settlementPeriod ?? '',
      r.forecastMW ?? '',
      r.actualMW ?? '',
      r.errorMW ?? '',
      r.absoluteErrorMW ?? '',
      r.publishTime ?? '',
      data?.cutoffHourLondon ?? cutoff
    ].join(','));
    const csvContent = [...meta, cols.join(','), ...dataLines].join('\n');
    const url = URL.createObjectURL(new Blob([csvContent], { type: 'text/csv;charset=utf-8;' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `wind-forecast-accuracy-${curMonth}-cutoff-${data?.cutoffHourLondon ?? cutoff}h.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon"><Wind size={21} /></div>
          <div><b>Northstar</b><span>ENERGY INTELLIGENCE</span></div>
        </div>
        <div className="workspace">
          <span className="tiny-label">WORKSPACE</span>
          <div className="workspace-row">
            <div className="uk-mark">UK</div>
            <div><b>UK Power Desk</b><small>National portfolio</small></div>
            <ChevronDown size={15} />
          </div>
        </div>
        <div className="nav-label">ANALYTICS</div>
        <button className={`nav-item ${tab === 'overview' ? 'active' : ''}`} onClick={() => setTab('overview')}>
          <Activity size={17} /> Overview
        </button>
        <button className={`nav-item ${tab === 'periods' ? 'active' : ''}`} onClick={() => setTab('periods')}>
          <CalendarDays size={17} /> Settlement periods
        </button>
        <button className={`nav-item ${tab === 'method' ? 'active' : ''}`} onClick={() => setTab('method')}>
          <CircleHelp size={17} /> Methodology
        </button>
        <div className="sidebar-bottom">
          <div className="source-status">
            <span className="status-dot" />
            <div><b>Elexon BMRS</b><small>Optimized stream cache</small></div>
          </div>
          <div className="side-foot">PILOT ENVIRONMENT <span>v1.2.0</span></div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">Markets <span>/</span> Wind procurement <span>/</span> <b>{monthName}</b></div>
          <div className="top-actions">
            <div className="period-pill"><span className="status-dot" /> Historical backtest</div>
            <button className="icon-button" title="Force live refresh from Elexon" onClick={() => load(month, cutoff, true)}>
              <RefreshCw size={16} />
            </button>
            <div className="avatar">PD</div>
          </div>
        </header>

        <div className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow"><span className="eyebrow-line" /> DAY-AHEAD PROCUREMENT</div>
              <h1>Wind forecast intelligence</h1>
              <p>Quantify renewable generation uncertainty before committing to day-ahead power trades.</p>
            </div>
            <div className="heading-controls">
              <label>DELIVERY MONTH
                <select value={month} onChange={e => setMonth(e.target.value)}>
                  {supportedMonths.map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </label>
              <label>DECISION CUTOFF
                <select value={cutoff} onChange={e => setCutoff(e.target.value)}>
                  <option value="8">08:00 UK</option>
                  <option value="10">10:00 UK</option>
                  <option value="12">12:00 UK</option>
                  <option value="16">16:00 UK</option>
                </select>
              </label>
              <button className="primary-button" onClick={exportCsv}>
                <Download size={16} /> Export CSV
              </button>
            </div>
          </div>

          {error && (
            <div className="error-banner">
              <b>Unable to load live data</b>
              <span>{error}</span>
              <button onClick={() => load(month, cutoff, true)}>Retry</button>
            </div>
          )}

          {loading && (
            <div className="loading-banner">
              <span className="spinner" /> Retrieving {monthName} records from Elexon BMRS…
            </div>
          )}

          {tab === 'method' ? (
            <section className="panel methodology">
              <div className="panel-title">
                <div>
                  <h2>Methodology & assumptions</h2>
                  <p>How the numbers in this dashboard are calculated.</p>
                </div>
              </div>
              <div className="method-grid">
                <article>
                  <span>01</span>
                  <h3>Actual generation (FUELHH)</h3>
                  <p>National half-hourly outturn generation from Elexon FUELHH filtered to <code>fuelType = WIND</code>, representing metered half-hour average MW.</p>
                </article>
                <article>
                  <span>02</span>
                  <h3>Decision-time forecast (WINDFOR)</h3>
                  <p>For each delivery interval, choose the latest WINDFOR publication available at or before the configured cutoff on the preceding UK calendar day (D-1), eliminating hindsight bias.</p>
                </article>
                <article>
                  <span>03</span>
                  <h3>Accuracy metrics</h3>
                  <p>MAE and RMSE quantify typical and tail error magnitudes. Bias is forecast minus actual (positive indicates over-forecasting). WAPE is total absolute error divided by total actual generation.</p>
                </article>
                <article>
                  <span>04</span>
                  <h3>Resolution alignment</h3>
                  <p>Hourly WINDFOR records are associated with both 30-minute settlement periods within the hour. Daily energy is computed as MW × 0.5 h (MWh), preserving exact volume balance.</p>
                </article>
              </div>
              <div className="note">
                <b>Pilot caveat:</b> The selected cutoff defaults to 10:00 UK time on D-1. Confirm your desk's specific operational gate closure before live execution.
              </div>
              <p className="source-link">
                Source: <a href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream" target="_blank" rel="noreferrer">Elexon FUELHH</a> · <a href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream" target="_blank" rel="noreferrer">Elexon WINDFOR</a>
              </p>
            </section>
          ) : tab === 'periods' ? (
            <section className="panel periods-panel">
              <div className="panel-title">
                <div>
                  <h2>{monthName} settlement periods</h2>
                  <p>Complete historical backtest: latest forecast available at {cutoff.padStart(2, '0')}:00 UK cutoff on D-1 vs actual generation.</p>
                </div>
                <div className="table-controls-top">
                  <label className="compact-select">
                    <CalendarDays size={14} />
                    <select value={periodDayFilter} onChange={e => { setPeriodDayFilter(e.target.value); setPeriodPage(1); }}>
                      <option value="all">All Days (Paginated)</option>
                      {daysList.map(d => (
                        <option key={d} value={d}>
                          {new Date(`${d}T12:00:00`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={13} />
                  </label>
                  <button className="primary-button" onClick={exportCsv}>
                    <Download size={15} /> Export CSV
                  </button>
                </div>
              </div>

              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>DELIVERY DATE</th>
                      <th>TIME (UK)</th>
                      <th>SP</th>
                      <th>FORECAST MW</th>
                      <th>ACTUAL MW</th>
                      <th>ERROR MW</th>
                      <th>FORECAST PUBLISHED</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPeriods.map(r => (
                      <tr key={r.startTime}>
                        <td>{r.settlementDate}</td>
                        <td>{new Date(r.localTime).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/London' })}</td>
                        <td>{r.settlementPeriod}</td>
                        <td>{fmt(r.forecastMW)}</td>
                        <td>{fmt(r.actualMW)}</td>
                        <td className={r.errorMW > 0 ? 'error-positive' : r.errorMW < 0 ? 'error-negative' : ''}>
                          {r.errorMW == null ? '—' : `${r.errorMW > 0 ? '+' : ''}${fmt(r.errorMW)}`}
                        </td>
                        <td>{r.publishTime ? new Date(r.publishTime).toLocaleString('en-GB', { timeZone: 'Europe/London', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="table-foot-nav">
                <div className="table-foot-info">
                  {periodDayFilter !== 'all' ? (
                    <span>Showing all 48 settlement periods for {dateLabel(periodDayFilter)}</span>
                  ) : showAllInTable ? (
                    <span>Showing all {fmt(rows.length)} settlement periods for {monthName}</span>
                  ) : (
                    <span>
                      Showing settlement periods {(periodPage - 1) * 48 + 1}–{Math.min(periodPage * 48, rows.length)} of {rows.length} ({dateLabel(daysList[periodPage - 1] || `${month}-01`)})
                    </span>
                  )}
                </div>

                {periodDayFilter === 'all' && (
                  <div className="pagination-bar">
                    <button
                      className="page-button"
                      disabled={periodPage <= 1 || showAllInTable}
                      onClick={() => setPeriodPage(p => Math.max(1, p - 1))}
                    >
                      <ChevronLeft size={14} /> Prev Day
                    </button>
                    <span className="page-indicator">
                      Day {periodPage} of {totalPages}
                    </span>
                    <button
                      className="page-button"
                      disabled={periodPage >= totalPages || showAllInTable}
                      onClick={() => setPeriodPage(p => Math.min(totalPages, p + 1))}
                    >
                      Next Day <ChevronRight size={14} />
                    </button>
                    <button
                      className="toggle-all-button"
                      onClick={() => setShowAllInTable(v => !v)}
                    >
                      {showAllInTable ? 'Show Paginated (48/day)' : `Show All ${fmt(rows.length)} Rows`}
                    </button>
                  </div>
                )}
              </div>
            </section>
          ) : (
            <>
              <div className="kpi-grid">
                <Kpi
                  icon={<Wind size={17} />}
                  label="Mean absolute error"
                  value={fmt(metrics.maeMW, 0)}
                  unit="MW"
                  detail="Typical half-hour forecast miss"
                  tone="blue"
                />
                <Kpi
                  icon={<Activity size={17} />}
                  label="Forecast bias"
                  value={metrics.biasMW == null ? '—' : `${metrics.biasMW > 0 ? '+' : ''}${fmt(metrics.biasMW, 0)}`}
                  unit="MW"
                  detail={metrics.biasMW == null ? 'Awaiting matched data' : metrics.biasMW > 0 ? 'Tends to over-forecast' : 'Tends to under-forecast'}
                  tone={metrics.biasMW > 0 ? 'amber' : 'green'}
                />
                <Kpi
                  icon={<Zap size={17} />}
                  label="RMSE"
                  value={fmt(metrics.rmseMW, 0)}
                  unit="MW"
                  detail="Penalises larger misses"
                  tone="purple"
                />
                <Kpi
                  icon={<CalendarDays size={17} />}
                  label="Matched periods"
                  value={fmt(data?.counts?.pairedPeriods)}
                  unit={`/ ${fmt(data?.counts?.expectedPeriods ?? rows.length ?? 1488)}`}
                  detail={`${monthName} half-hours with both values`}
                  tone="green"
                />
              </div>

              <section className="panel chart-panel">
                <div className="panel-title">
                  <div>
                    <h2>Daily wind generation</h2>
                    <p>Forecast available at decision cutoff vs. metered outturn</p>
                  </div>
                  <div className="chart-legend">
                    <span><i className="legend-blue" /> Forecast (Area)</span>
                    <span><i className="legend-green" /> Actual (Line)</span>
                  </div>
                </div>

                <div className="chart-subline">
                  <div>
                    <b>{chartRows.length ? fmt(chartRows.reduce((s, r) => s + r.actual, 0), 0) : '—'} <small>MWh</small></b>
                    <span>Actual energy · matched periods</span>
                  </div>
                  <div>
                    <b>{fmt(metrics.wapePercent, 1)}<small>%</small></b>
                    <span>Weighted absolute percentage error</span>
                  </div>
                  <div>
                    <b>{data?.counts?.missingForecastPeriods == null ? '—' : fmt(data.counts.missingForecastPeriods)}</b>
                    <span>Intervals missing an eligible forecast</span>
                  </div>
                </div>

                <div className="chart-wrap">
                  {chartRows.length ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={chartRows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                        <defs>
                          <linearGradient id="forecastFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#6198ff" stopOpacity={0.20} />
                            <stop offset="95%" stopColor="#6198ff" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 5" vertical={false} stroke="#e9edf4" />
                        <XAxis dataKey="label" tick={{ fill: '#7e899d', fontSize: 11 }} axisLine={false} tickLine={false} interval={3} />
                        <YAxis tick={{ fill: '#7e899d', fontSize: 11 }} axisLine={false} tickLine={false} width={50} tickFormatter={v => `${Math.round(v / 1000)}k`} />
                        <Tooltip
                          formatter={(v, n) => [`${fmt(v, 0)} MWh`, n === 'actual' ? 'Actual energy' : 'Forecast energy']}
                          labelFormatter={l => `Delivery date: ${l}`}
                          contentStyle={{ border: '1px solid #e4e9f1', borderRadius: 12, boxShadow: '0 8px 24px #1e293b12' }}
                        />
                        <Area type="monotone" dataKey="forecast" name="forecast" stroke="#5289f7" strokeWidth={2.3} fill="url(#forecastFill)" dot={false} />
                        <Line type="monotone" dataKey="actual" name="actual" stroke="#18a77a" strokeWidth={2.4} dot={{ r: 2, fill: '#18a77a' }} activeDot={{ r: 5 }} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  ) : (
                    <Empty message="Matched daily observations will appear here when Elexon data loads." />
                  )}
                </div>

                <div className="chart-footer">
                  <span><span className="status-dot" /> Source: Elexon BMRS API (FUELHH & WINDFOR)</span>
                  <span>Daily totals are MW × 0.5 h, reported as MWh</span>
                  <span>Cutoff: previous day at {cutoff.padStart(2, '0')}:00 UK</span>
                </div>
              </section>

              <div className="lower-grid">
                <section className="panel periods-panel">
                  <div className="panel-title">
                    <div>
                      <h2>Settlement period review</h2>
                      <p>Inspect the forecast vintage used for a delivery day.</p>
                    </div>
                    <label className="compact-select">
                      <CalendarDays size={14} />
                      <select value={selectedDay} onChange={e => setSelectedDay(e.target.value)}>
                        {daysList.map(d => (
                          <option key={d} value={d}>
                            {new Date(`${d}T12:00:00`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}
                          </option>
                        ))}
                      </select>
                      <ChevronDown size={13} />
                    </label>
                  </div>

                  <div className="table-wrap" style={{ maxHeight: showAllOverviewRows ? '480px' : '320px' }}>
                    <table>
                      <thead>
                        <tr>
                          <th>TIME (UK)</th>
                          <th>FORECAST</th>
                          <th>ACTUAL</th>
                          <th>ERROR</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(showAllOverviewRows ? dayRows : dayRows.slice(0, 12)).map(r => (
                          <tr key={r.startTime}>
                            <td>{new Date(r.localTime).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/London' })}</td>
                            <td>{fmt(r.forecastMW)} <small>MW</small></td>
                            <td>{fmt(r.actualMW)} <small>MW</small></td>
                            <td className={r.errorMW > 0 ? 'error-positive' : r.errorMW < 0 ? 'error-negative' : ''}>
                              {r.errorMW > 0 ? '+' : ''}{fmt(r.errorMW)} <small>MW</small>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!dayRows.length && <Empty message="No matched records for this day in the current response." />}
                  </div>

                  <div className="table-foot">
                    Showing {Math.min(showAllOverviewRows ? 48 : 12, dayRows.length)} of {dayRows.length} matched half-hour periods
                    <span>·</span>
                    <button onClick={() => setShowAllOverviewRows(v => !v)}>
                      {showAllOverviewRows ? 'Show first 12 periods' : 'Show all 48 periods'}
                    </button>
                    <span>·</span>
                    <button onClick={() => { setPeriodDayFilter(selectedDay); setTab('periods'); }}>
                      Full table view
                    </button>
                  </div>
                </section>

                <section className="panel procurement-panel">
                  <div className="panel-title">
                    <div>
                      <h2>Residual procurement</h2>
                      <p>Illustrative planning calculation</p>
                    </div>
                    <div className="soft-icon"><Zap size={18} /></div>
                  </div>

                  <div className="assumption-tag">USER-PROVIDED ASSUMPTION</div>
                  <label className="field-label">Expected demand (MW)
                    <div className="input-wrap">
                      <input type="number" min="0" value={demand} onChange={e => setDemand(e.target.value)} />
                      <span>MW</span>
                    </div>
                  </label>

                  <div className="procurement-flow">
                    <div>
                      <span>Demand assumption</span>
                      <b>{fmt(Number(demand))} MW</b>
                    </div>
                    <div className="minus">−</div>
                    <div>
                      <span>Mean wind forecast</span>
                      <b>{dayRows.length ? fmt(dayRows.reduce((s, r) => s + r.forecastMW, 0) / dayRows.length) : '—'} MW</b>
                    </div>
                  </div>

                  <div className="residual-result">
                    <span>Indicative residual requirement</span>
                    <div>
                      <b>{dayRows.length ? fmt(residual) : '—'}</b>
                      <small>MW</small>
                    </div>
                    <p>Demand minus mean wind forecast for {dateLabel(selectedDay)}. Not a market order or full system balance.</p>
                  </div>

                  <div className="caution">
                    <CircleHelp size={15} />
                    <span>Excludes other generation, imports, storage, losses, demand response and portfolio constraints.</span>
                  </div>
                </section>
              </div>
            </>
          )}

          <footer className="page-footer">
            <span>Northstar Energy Intelligence <b>·</b> Pilot build</span>
            <span>Data window: {dataWindowText} <b>·</b> Europe/London decision clock</span>
            <span>For analytical demonstration only</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

function Kpi({ icon, label, value, unit, detail, tone }) {
  return (
    <div className="kpi-card">
      <div className={`kpi-icon ${tone}`}>{icon}</div>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}<small>{unit}</small></div>
      <div className="kpi-detail">{detail}</div>
    </div>
  );
}

function Empty({ message }) {
  return (
    <div className="empty-state">
      <Wind size={22} />
      <span>{message}</span>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
