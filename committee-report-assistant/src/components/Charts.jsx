import { t, num } from '../i18n.js';
import { useId, useState } from 'react';
import { OPTIONS, PRICE_SERIES, CAPACITY, RISKS, MILESTONES } from '../data.js';

// Series colours follow the validated reference palette (slot 1 blue, slot 2 orange); text always uses ink tokens.
const A = 'var(--chart-1)';
const B = 'var(--chart-2)';
const MUTED = 'var(--chart-muted)';
const FONT = 'var(--f-sans)';
const txt = { fontFamily: FONT, fill: 'var(--ink-2)' };

function Legend({ items }) {
  return (
    <ul className="legend">
      {items.map((i) => (
        <li key={i.label}><span className="sw" style={{ background: i.color, ...(i.dashed ? { background: 'repeating-linear-gradient(90deg,var(--chart-muted) 0 4px,transparent 4px 7px)', height: 2 } : {}) }} />{t(i.label)}</li>
      ))}
    </ul>
  );
}

/* ----------------------------- Cost premium bars ----------------------------- */
export function CostChart() {
  const [hover, setHover] = useState(null);
  const x0 = 214, max = 2.5, w = 200;
  return (
    <figure className="chart">
      <figcaption>{t("Cost premium vs single source")} <span>{t("€ per kWh, average 2027–2032")}</span></figcaption>
      <svg viewBox="0 0 600 214" role="img" aria-label={t("Cost premium per option and supply risk score")}>
        <text x={x0} y="16" fontSize="11" {...txt}>{t("Premium")}</text>
        <text x="500" y="16" fontSize="11" {...txt}>{t("Supply risk (1–5)")}</text>
        {OPTIONS.map((o, i) => {
          const y = 34 + i * 58;
          const bw = Math.max(2, (o.premium || 0) / max * w);
          const on = hover === o.id;
          return (
            <g key={o.id} onMouseEnter={() => setHover(o.id)} onMouseLeave={() => setHover(null)} style={{ cursor: 'default' }}>
              <rect x="0" y={y - 8} width="600" height="52" rx="10" fill={on ? 'var(--accent-soft)' : 'transparent'} />
              <text x="12" y={y + 12} fontSize="14" fontWeight="600" style={{ fontFamily: FONT, fill: 'var(--ink)' }}>{o.id}. {t(o.name)}</text>
              <text x="12" y={y + 30} fontSize="11.5" {...txt}>{t(o.sub)}</text>
              <path d={`M${x0} ${y + 6} h${Math.max(0, bw - 4)} a4 4 0 0 1 4 4 v8 a4 4 0 0 1 -4 4 h${-Math.max(0, bw - 4)} z`} fill={o.recommended ? A : 'var(--chart-neutral)'} />
              <text x={x0 + bw + 8} y={y + 20} fontSize="12.5" fontWeight="500" style={{ fontFamily: FONT, fill: 'var(--ink)' }}>
                {o.premium == null ? t('Baseline') : `+${num(o.premium)} €`}
              </text>
              <text x="500" y={y + 20} fontSize="13" fontWeight="600" style={{ fontFamily: FONT, fill: 'var(--ink)' }}>{num(o.risk)}</text>
              <g>
                {[1, 2, 3, 4, 5].map((n) => (
                  <rect key={n} x={528 + n * 11} y={y + 10} width="8" height="12" rx="2" fill={n <= Math.round(o.risk) ? 'var(--ink-2)' : 'var(--line)'} />
                ))}
              </g>
              <title>{t('{name}: cell cost €{cost} per kWh, supply risk {risk}', { name: t(o.name), cost: num(o.cost), risk: num(o.risk) })}</title>
            </g>
          );
        })}
        <line x1={x0} x2={x0} y1="26" y2="200" stroke="var(--line-strong)" />
      </svg>
    </figure>
  );
}

/* ------------------------------ Price outlook lines --------------------------- */
export function PriceChart() {
  const [hi, setHi] = useState(null);
  const { years, a, b, market } = PRICE_SERIES;
  const W = 600, H = 250, L = 44, R = 70, T = 14, Bt = 34;
  const lo = 64, hiY = 76;
  const x = (i) => L + (i * (W - L - R)) / (years.length - 1);
  const y = (v) => T + ((hiY - v) * (H - T - Bt)) / (hiY - lo);
  const path = (s) => s.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    setHi(Math.max(0, Math.min(years.length - 1, Math.round(((px - L) / (W - L - R)) * (years.length - 1)))));
  };
  return (
    <figure className="chart">
      <figcaption>{t("Cell price outlook")} <span>{t("€ per kWh by supply year")}</span></figcaption>
      <Legend items={[{ label: 'Supplier A offer', color: A }, { label: 'Supplier B offer', color: B }, { label: 'Public market index', color: MUTED, dashed: true }]} />
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("Price outlook for Supplier A, Supplier B and the market index from 2027 to 2032")} onMouseMove={onMove} onMouseLeave={() => setHi(null)}>
        {[64, 68, 72, 76].map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--line)" />
            <text x={L - 8} y={y(t) + 4} textAnchor="end" fontSize="11" {...txt}>{t}</text>
          </g>
        ))}
        {years.map((yr, i) => <text key={yr} x={x(i)} y={H - 12} textAnchor="middle" fontSize="11" {...txt}>{yr}</text>)}
        <path d={path(market)} fill="none" stroke={MUTED} strokeWidth="2" strokeDasharray="5 4" strokeLinecap="round" />
        <path d={path(b)} fill="none" stroke={B} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d={path(a)} fill="none" stroke={A} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx={x(5)} cy={y(a[5])} r="4.5" fill={A} stroke="var(--surface)" strokeWidth="2" />
        <circle cx={x(5)} cy={y(b[5])} r="4.5" fill={B} stroke="var(--surface)" strokeWidth="2" />
        <text x={x(5) + 10} y={y(a[5]) + 15} fontSize="12" fontWeight="600" style={{ fontFamily: FONT, fill: 'var(--ink)' }}>A {num(a[5])}</text>
        <text x={x(5) + 10} y={y(b[5]) - 7} fontSize="12" fontWeight="600" style={{ fontFamily: FONT, fill: 'var(--ink)' }}>B {num(b[5])}</text>
        {hi != null && (
          <g pointerEvents="none">
            <line x1={x(hi)} x2={x(hi)} y1={T} y2={H - Bt} stroke="var(--ink-3)" />
            {[[a, A], [b, B], [market, MUTED]].map(([s, c], k) => <circle key={k} cx={x(hi)} cy={y(s[hi])} r="4" fill={c} stroke="var(--surface)" strokeWidth="2" />)}
            <g transform={`translate(${Math.min(x(hi) + 12, W - R - 110)},${T + 4})`}>
              <rect width="124" height="68" rx="8" fill="var(--ink)" />
              <text x="10" y="17" fontSize="11" fontWeight="600" style={{ fontFamily: FONT, fill: '#fff' }}>{years[hi]}</text>
              <text x="10" y="34" fontSize="11" style={{ fontFamily: FONT, fill: '#fff' }}>{t('Supplier A')}  {num(a[hi])}</text>
              <text x="10" y="48" fontSize="11" style={{ fontFamily: FONT, fill: '#fff' }}>{t('Supplier B')}  {num(b[hi])}</text>
              <text x="10" y="62" fontSize="11" style={{ fontFamily: FONT, fill: '#fff' }}>{t('Market')}  {num(market[hi])}</text>
            </g>
          </g>
        )}
        <rect x={L} y={T} width={W - L - R} height={H - T - Bt} fill="transparent" />
      </svg>
    </figure>
  );
}

/* ------------------------- Supplier B capacity (extracted) ------------------------ */
export function CapacityChart({ assumed }) {
  const id = useId().replace(/:/g, '');
  const W = 420, H = 250, L = 38, T = 22, Bt = 34, max = 20;
  const bw = 40, step = (W - L - 10) / CAPACITY.length;
  const y = (v) => T + ((max - v) * (H - T - Bt)) / max;
  return (
    <figure className="chart">
      <figcaption>{t("Supplier B stated capacity")} <span>{t("GWh per year")}</span></figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("Supplier B capacity 6, 12 and 18 GWh for 2027 to 2029, not stated afterwards")}>
        <defs>
          <pattern id={`h${id}`} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="7" stroke="var(--chart-neutral)" strokeWidth="2" />
          </pattern>
        </defs>
        {[0, 10, 20].map((t) => (
          <g key={t}><line x1={L} x2={W - 6} y1={y(t)} y2={y(t)} stroke="var(--line)" /><text x={L - 8} y={y(t) + 4} textAnchor="end" fontSize="11" {...txt}>{t}</text></g>
        ))}
        {CAPACITY.map((c, i) => {
          const cx = L + step * i + step / 2 - bw / 2;
          if (c.gwh == null) {
            const top = assumed ? y(18) : y(18);
            return (
              <g key={c.year}>
                <rect x={cx} y={top} width={bw} height={y(0) - top} rx="4" fill={assumed ? 'none' : `url(#h${id})`} stroke="var(--chart-neutral)" strokeDasharray={assumed ? '4 3' : '0'} />
                <text x={cx + bw / 2} y={top - 6} textAnchor="middle" fontSize="11" {...txt}>{assumed ? t('assumed') : t('not stated')}</text>
                <text x={cx + bw / 2} y={H - 12} textAnchor="middle" fontSize="11" {...txt}>{c.year}</text>
              </g>
            );
          }
          return (
            <g key={c.year}>
              <path d={`M${cx} ${y(0)} V${y(c.gwh) + 4} a4 4 0 0 1 4 -4 h${bw - 8} a4 4 0 0 1 4 4 V${y(0)} z`} fill={A} />
              <text x={cx + bw / 2} y={y(c.gwh) - 6} textAnchor="middle" fontSize="12" fontWeight="600" style={{ fontFamily: FONT, fill: 'var(--ink)' }}>{c.gwh}</text>
              <text x={cx + bw / 2} y={H - 12} textAnchor="middle" fontSize="11" {...txt}>{c.year}</text>
            </g>
          );
        })}
        <line x1={L} x2={W - 6} y1={y(12.8)} y2={y(12.8)} stroke="var(--ink-2)" strokeDasharray="5 4" />
        <text x={W - 8} y={y(12.8) - 6} textAnchor="end" fontSize="11" {...txt}>{t("40% share = 12.8 GWh")}</text>
      </svg>
    </figure>
  );
}

/* ---------------------------------- Risk matrix --------------------------------- */
const level = (l, i) => (l * i >= 6 ? 'High' : l * i >= 3 ? 'Medium' : 'Low');
const TINT = { High: 'var(--risk-high)', Medium: 'var(--risk-med)', Low: 'var(--risk-low)' };
export function RiskMatrix() {
  const cell = 92, L = 76, T = 8;
  const labels = ['Low', 'Medium', 'High'];
  return (
    <figure className="chart">
      <figcaption>{t("Risk matrix")} <span>{t("likelihood and impact, 5 risks")}</span></figcaption>
      <svg viewBox="0 0 372 340" role="img" aria-label={t("Risk matrix with five risks")}>
        {[1, 2, 3].map((i) => [1, 2, 3].map((l) => {
          const x = L + (l - 1) * cell, y = T + (3 - i) * cell;
          const lv = level(l, i);
          const here = RISKS.filter((r) => r.l === l && r.i === i);
          return (
            <g key={`${l}${i}`}>
              <rect x={x + 1} y={y + 1} width={cell - 2} height={cell - 2} rx="8" fill={TINT[lv]} />
              <text x={x + 8} y={y + 16} fontSize="10.5" {...txt}>{t(lv)}</text>
              {here.map((r, k) => (
                <g key={r.id}>
                  <circle cx={x + cell / 2 + (k - (here.length - 1) / 2) * 34} cy={y + cell / 2 + 6} r="15" fill="var(--ink)" stroke="#fff" strokeWidth="2" />
                  <text x={x + cell / 2 + (k - (here.length - 1) / 2) * 34} y={y + cell / 2 + 10.5} textAnchor="middle" fontSize="11.5" fontWeight="600" style={{ fontFamily: FONT, fill: '#fff' }}>{r.id}</text>
                  <title>{`${r.id}: ${t(r.name)}`}</title>
                </g>
              ))}
            </g>
          );
        }))}
        {labels.map((lb, k) => <text key={lb} x={L + k * cell + cell / 2} y={T + 3 * cell + 18} textAnchor="middle" fontSize="11" {...txt}>{t(lb)}</text>)}
        {labels.map((lb, k) => <text key={lb} x={L - 8} y={T + (2 - k) * cell + cell / 2 + 4} textAnchor="end" fontSize="11" {...txt}>{t(lb)}</text>)}
        <text x={L + (3 * cell) / 2} y={T + 3 * cell + 36} textAnchor="middle" fontSize="11.5" fontWeight="500" {...txt}>{t("Likelihood")}</text>
        <text transform={`translate(12 ${T + (3 * cell) / 2}) rotate(-90)`} textAnchor="middle" fontSize="11.5" fontWeight="500" {...txt}>{t("Impact")}</text>
      </svg>
    </figure>
  );
}
export const riskLevel = (r) => level(r.l, r.i);

/* ------------------------------------ Timeline ----------------------------------- */
export function Gantt() {
  const W = 680, Lc = 150, R = 20, rowH = 30, T = 30;
  const x = (m) => Lc + (m * (W - Lc - R)) / 30;
  return (
    <figure className="chart">
      <figcaption>{t("Timeline")} <span>{t("Q4 2026 to Q1 2029")}</span></figcaption>
      <svg viewBox={`0 0 ${W} ${T + MILESTONES.length * rowH + 8}`} role="img" aria-label={t("Timeline from decision in December 2026 to review gate in March 2029")}>
        {[[3, '2027'], [15, '2028'], [27, '2029']].map(([m, t]) => (
          <g key={t}><line x1={x(m)} x2={x(m)} y1={T - 8} y2={T + MILESTONES.length * rowH} stroke="var(--line)" /><text x={x(m) + 5} y="16" fontSize="11" fontWeight="500" {...txt}>{t}</text></g>
        ))}
        {MILESTONES.map((m, i) => {
          const cy = T + i * rowH + rowH / 2;
          const right = (m.at ?? m.to) < 22;
          const ex = m.type === 'ms' ? x(m.at) : x(m.to);
          const sx = m.type === 'ms' ? x(m.at) : x(m.from);
          return (
            <g key={m.id}>
              <text x="0" y={cy + 4} fontSize="12.5" style={{ fontFamily: FONT, fill: 'var(--ink)' }}>{t(m.label)}</text>
              {m.type === 'ms'
                ? <path d={`M${x(m.at)} ${cy - 8} l8 8 l-8 8 l-8 -8 z`} fill={m.id === 'm1' ? 'var(--ink)' : A} stroke="var(--surface)" strokeWidth="2" />
                : <rect x={x(m.from)} y={cy - 7} width={x(m.to) - x(m.from)} height="14" rx="4" fill={m.id === 'b1' ? A : 'var(--chart-neutral)'} />}
              <text x={right ? ex + 14 : sx - 14} y={cy + 4} textAnchor={right ? 'start' : 'end'} fontSize="11.5" {...txt}>{t(m.text)}</text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

/* ----------------------------------- Options table -------------------------------- */
export function OptionsTable({ qc }) {
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead>
          <tr><th>{t("Option")}</th><th className="num">{t("Cell cost")}<br /><small>{t("€ per kWh")}</small></th><th className="num">{t("Premium")}<br /><small>{t("€ per kWh")}</small></th><th className="num">{t("Qualification")}<br /><small>{t("one-time")}</small></th><th>{t("First volume")}</th><th className="num">{t("Supply risk")}<br /><small>{t("1–5, lower is better")}</small></th></tr>
        </thead>
        <tbody>
          {OPTIONS.map((o) => (
            <tr key={o.id} className={o.recommended ? 'rec' : ''}>
              <td><strong>{o.id}. {t(o.name)}</strong>{o.recommended && <em className="rec-tag">{t("Recommended")}</em>}<small>{t(o.sub)}</small></td>
              <td className="num">{num(o.cost)}</td>
              <td className="num">{o.premium == null ? '–' : `+${num(o.premium)}`}</td>
              <td className="num">{t(o.qual).replace('%QC%', qc)}</td>
              <td>{t(o.first)}</td>
              <td className="num">{num(o.risk)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const VISUALS = { cost: CostChart, price: PriceChart, capacity: CapacityChart, risk: RiskMatrix, timeline: Gantt };
