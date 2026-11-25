// Draws one slide from its stored spec on the 1280x720 canvas, with the same boxes, font sizes and colours the PowerPoint file uses
// (backend/app/core/slides). The page never re-fits text: the sizes come from the server, so the slide here and the downloaded slide match.
import { useEffect, useRef, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { api } from './client.js';

const TONE = { decision: 'primary', info: 'accent', warn: 'warn', good: 'good' };
const fmt = (v, lang) => {
  const s = Math.abs(v) >= 1000 ? Math.round(v).toLocaleString(lang === 'en' ? 'en-US' : 'de-DE') : String(+v.toFixed(2)).replace('.', lang === 'en' ? '.' : ',');
  return s;
};

/** A text that can be edited in place. Commits on blur; Escape puts the old text back. */
function Ed({ value, onCommit, editable, multiline = false, style, className, tag: Tag = 'div' }) {
  if (!editable) return <Tag className={className} style={style}>{value}</Tag>;
  return (
    <Tag
      key={value} className={`ed ${className || ''}`} style={style} contentEditable suppressContentEditableWarning spellCheck={false}
      onKeyDown={(e) => {
        if (e.key === 'Escape') { e.currentTarget.innerText = value; e.currentTarget.blur(); }
        else if (e.key === 'Enter' && !(multiline && e.shiftKey)) { e.preventDefault(); e.currentTarget.blur(); }
      }}
      onBlur={(e) => { const v = e.currentTarget.innerText.replace(/\s+/g, ' ').trim(); if (v !== value) onCommit(v); }}
    >{value}</Tag>
  );
}

// ---------------------------------------------------------------------------------------------- charts
function Chart({ b, box, th, lang }) {
  const ch = b.chart;
  const pal = th.palette;
  const head = ch.title ? 36 : 0;
  const W = box.w, H = box.h - head;
  const n = ch.labels.length;
  const multi = ch.series.length > 1;
  const legendH = multi || ch.type === 'donut' ? 34 : 0;
  const labelFont = 16;
  const unit = ch.unit && ch.title && !ch.title.includes(ch.unit) ? ` (${ch.unit})` : ch.unit && !ch.title ? ` (${ch.unit})` : '';
  const area = { x: 8, y: 22, w: W - 16, h: H - legendH - 22 - 34 };
  let body = null;

  if (ch.type === 'donut') {
    const vals = ch.series[0].values; const tot = vals.reduce((a, v) => a + v, 0) || 1;
    const r = Math.min(W, H - legendH) / 2 - 10; const cx = W / 2; const cy = (H - legendH) / 2; let a0 = -Math.PI / 2;
    body = vals.map((v, i) => {
      const a1 = a0 + (v / tot) * Math.PI * 2; const big = a1 - a0 > Math.PI ? 1 : 0;
      const p = (rr, a) => [cx + rr * Math.cos(a), cy + rr * Math.sin(a)];
      const [x0, y0] = p(r, a0); const [x1, y1] = p(r, a1); const [x2, y2] = p(r * 0.55, a1); const [x3, y3] = p(r * 0.55, a0);
      const d = `M${x0},${y0} A${r},${r} 0 ${big} 1 ${x1},${y1} L${x2},${y2} A${r * 0.55},${r * 0.55} 0 ${big} 0 ${x3},${y3}Z`;
      const mid = (a0 + a1) / 2; const [lx, ly] = p(r * 0.775, mid); a0 = a1;
      return (
        <g key={i}><path d={d} fill={pal[i % pal.length]} stroke="#fff" strokeWidth="2" />
          {v / tot > 0.04 && <text x={lx} y={ly} textAnchor="middle" dominantBaseline="central" fontSize={labelFont} fontWeight="700" fill="#fff">{fmt(v, lang)}</text>}</g>
      );
    });
  } else if (ch.type === 'line') {
    const all = ch.series.flatMap((s) => s.values); const lo = Math.min(0, ...all); const hi = Math.max(...all, 1e-9); const span = hi - lo || 1;
    const X = (i) => area.x + (n === 1 ? area.w / 2 : (area.w * (i + 0.5)) / n); const Y = (v) => area.y + area.h - ((v - lo) / span) * area.h;
    body = (
      <>
        <line x1={area.x} x2={area.x + area.w} y1={Y(0)} y2={Y(0)} stroke={th.colors.line} />
        {ch.series.map((s, si) => (
          <g key={si}>
            <polyline fill="none" stroke={pal[si % pal.length]} strokeWidth="3" points={s.values.map((v, i) => `${X(i)},${Y(v)}`).join(' ')} />
            {s.values.map((v, i) => (
              <g key={i}><circle cx={X(i)} cy={Y(v)} r="5" fill={pal[si % pal.length]} />
                <text x={X(i)} y={si % 2 ? Y(v) + 24 : Y(v) - 11} textAnchor="middle" fontSize={labelFont} fontWeight="700" fill={th.colors.text}>{fmt(v, lang)}</text></g>
            ))}
          </g>
        ))}
        {ch.labels.map((l, i) => <text key={i} x={X(i)} y={area.y + area.h + 24} textAnchor="middle" fontSize={labelFont} fill={th.colors.text}>{l}</text>)}
      </>
    );
  } else if (ch.type === 'bar') {
    const barArea = { x: Math.min(190, W * 0.3), y: 4, w: W - Math.min(190, W * 0.3) - 70, h: H - legendH - 8 };
    const hi = Math.max(...ch.series.flatMap((s) => s.values), 1e-9);
    const rowH = barArea.h / n; const bh = Math.min(46, (rowH * 0.62) / ch.series.length);
    body = ch.labels.map((l, i) => (
      <g key={i}>
        <text x={barArea.x - 10} y={barArea.y + rowH * (i + 0.5)} textAnchor="end" dominantBaseline="central" fontSize={labelFont} fill={th.colors.text}>{l}</text>
        {ch.series.map((s, si) => {
          const w = Math.max(2, (Math.max(s.values[i], 0) / hi) * barArea.w); const y = barArea.y + rowH * (i + 0.5) + (si - (ch.series.length - 1) / 2) * bh;
          const col = multi ? pal[si % pal.length] : ch.highlight == null ? pal[0] : ch.highlight === i ? pal[0] : pal[2];
          return <g key={si}><rect x={barArea.x} y={y - bh / 2 + 1} width={w} height={bh - 2} fill={col} />
            <text x={barArea.x + w + 8} y={y} dominantBaseline="central" fontSize={labelFont} fontWeight="700" fill={th.colors.text}>{fmt(s.values[i], lang)}</text></g>;
        })}
      </g>
    ));
  } else { // column, stacked
    const stacked = ch.type === 'stacked';
    const tots = ch.labels.map((_, i) => ch.series.reduce((a, s) => a + Math.max(s.values[i], 0), 0));
    const hi = stacked ? Math.max(...tots, 1e-9) : Math.max(...ch.series.flatMap((s) => s.values), 1e-9);
    const lo = stacked ? 0 : Math.min(0, ...ch.series.flatMap((s) => s.values)); const span = hi - lo || 1;
    const slot = area.w / n; const gw = slot / 1.6; const bw = stacked ? gw : gw / ch.series.length;
    const Y = (v) => area.y + area.h - ((v - lo) / span) * area.h;
    body = (
      <>
        <line x1={area.x} x2={area.x + area.w} y1={Y(0)} y2={Y(0)} stroke={th.colors.line} />
        {ch.labels.map((l, i) => {
          const x0 = area.x + slot * i + (slot - gw) / 2; let acc = 0;
          return (
            <g key={i}>
              {ch.series.map((s, si) => {
                const v = s.values[i];
                if (stacked) {
                  const y1 = Y(acc + Math.max(v, 0)); const y0 = Y(acc); acc += Math.max(v, 0);
                  return <g key={si}><rect x={x0} y={y1} width={bw} height={Math.max(0, y0 - y1)} fill={pal[si % pal.length]} />
                    {y0 - y1 > 22 && <text x={x0 + bw / 2} y={(y0 + y1) / 2} textAnchor="middle" dominantBaseline="central" fontSize={labelFont} fontWeight="700" fill="#fff">{fmt(v, lang)}</text>}</g>;
                }
                const col = multi ? pal[si % pal.length] : ch.highlight == null ? pal[0] : ch.highlight === i ? pal[0] : pal[2];
                const y = v >= 0 ? Y(v) : Y(0); const h = Math.abs(Y(v) - Y(0));
                return <g key={si}><rect x={x0 + si * bw} y={y} width={bw - (multi ? 3 : 0)} height={Math.max(1, h)} fill={col} />
                  <text x={x0 + si * bw + bw / 2} y={v >= 0 ? y - 8 : y + h + 18} textAnchor="middle" fontSize={labelFont} fontWeight="700" fill={th.colors.text}>{fmt(v, lang)}</text></g>;
              })}
              {stacked && <text x={x0 + bw / 2} y={Y(tots[i]) - 8} textAnchor="middle" fontSize={labelFont} fontWeight="700" fill={th.colors.text}>{fmt(tots[i], lang)}</text>}
              <text x={x0 + gw / 2} y={area.y + area.h + 24} textAnchor="middle" fontSize={labelFont} fill={th.colors.text}>{l.length > 16 && n > 4 ? `${l.slice(0, 15)}…` : l}</text>
            </g>
          );
        })}
      </>
    );
  }

  const legend = multi || ch.type === 'donut'
    ? (ch.type === 'donut' ? ch.labels : ch.series.map((s) => s.name || ch.unit)).map((name, i) => ({ name, col: pal[i % pal.length] })) : [];
  let lx = 0;
  return (
    <div style={{ position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h }}>
      {ch.title && <div style={{ height: head, fontSize: 17, fontWeight: 700, color: th.colors.text, fontFamily: th.fonts.body }}>{ch.title}{unit}</div>}
      <svg width={W} height={H} style={{ fontFamily: th.fonts.body, display: 'block' }}>
        {body}
        {legend.map((l, i) => { const x = lx; lx += 38 + l.name.length * 9.4; return <g key={i} transform={`translate(${x + 8},${H - 14})`}><rect width="14" height="14" y="-10" fill={l.col} /><text x="22" fontSize="16" fill={th.colors.text}>{l.name}</text></g>; })}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- blocks
function Bullets({ b, box, th, edit }) {
  const set = (items) => edit?.((s) => { s.items = items; });
  return (
    <div className="sc-bullets" style={{ position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h, padding: 14 * 0.6, fontFamily: th.fonts.body, color: th.colors.text, overflow: 'hidden' }}>
      {b.items.map((it, i) => {
        const sz = b.size - (it.level ? 2 : 0); const ind = b.size * 1.1;
        return (
          <div key={i} className="sc-li" style={{ fontSize: sz, lineHeight: 1.2, marginBottom: b.size * 0.5, paddingLeft: ind * (1 + it.level), textIndent: -ind, position: 'relative' }}>
            <span style={{ display: 'inline-block', width: ind, textIndent: 0 }}>{it.level ? '–' : '•'}</span>
            <Ed tag="span" editable={!!edit} multiline value={it.text} onCommit={(v) => set(v ? b.items.map((x, j) => (j === i ? { ...x, text: v } : x)) : b.items.filter((_, j) => j !== i))} />
            {edit && <button className="sc-x" title="×" onClick={() => set(b.items.filter((_, j) => j !== i))}><X size={13} /></button>}
          </div>
        );
      })}
      {edit && b.items.length < 7 && <button className="sc-add" onClick={() => set([...b.items, { text: '…', claim_ids: [], level: 0 }])}><Plus size={14} /></button>}
    </div>
  );
}

function Kpis({ b, box, th, edit, lang }) {
  const n = b.items.length; const gap = 16; const tw = (box.w - gap * (n - 1)) / n;
  const set = (i, k, v) => edit?.((s) => { s.items = s.items.map((x, j) => (j === i ? { ...x, [k]: v } : x)); });
  return (
    <>
      {b.items.map((k, i) => (
        <div key={i} style={{ position: 'absolute', left: box.x + i * (tw + gap), top: box.y, width: tw, height: box.h, background: th.colors.soft, borderLeft: `5px solid ${th.colors.accent}`, padding: '10px 14px 6px 13px', boxSizing: 'border-box', overflow: 'hidden', fontFamily: th.fonts.body }}>
          <div style={{ lineHeight: 1.15 }}>
            <Ed tag="span" editable={!!edit} value={k.value} onCommit={(v) => set(i, 'value', v)} style={{ fontSize: b.size, fontWeight: 700, color: th.colors.primary, fontFamily: th.fonts.heading }} />
            {k.unit ? <span style={{ fontSize: Math.max(12, b.size * 0.4), color: th.colors.muted }}> {k.unit}</span> : null}
          </div>
          <Ed editable={!!edit} value={k.label} onCommit={(v) => set(i, 'label', v)} style={{ fontSize: b.label_size, color: th.colors.text, lineHeight: 1.2 }} />
          {k.delta ? <div style={{ fontSize: b.label_size, fontWeight: 700, color: k.tone === 'up' ? th.colors.good : k.tone === 'down' ? th.colors.crit : th.colors.muted }}>{k.delta}</div> : null}
        </div>
      ))}
    </>
  );
}

function Callout({ b, box, th, edit }) {
  const dark = b.tone === 'decision'; const tone = th.colors[TONE[b.tone] || 'accent'];
  const set = (k, v) => edit?.((s) => { s[k] = v; });
  return (
    <div style={{ position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h, background: dark ? th.colors.primary : th.colors.soft, borderLeft: `8px solid ${dark ? th.colors.accent : tone}`, boxSizing: 'border-box', padding: '14px 20px 14px 28px', display: 'flex', flexDirection: 'column', justifyContent: 'center', overflow: 'hidden' }}>
      {(b.title || edit) && <Ed editable={!!edit} value={b.title} onCommit={(v) => set('title', v)} style={{ fontSize: b.size * 0.7, fontWeight: 700, color: dark ? th.colors.accent : tone, fontFamily: th.fonts.heading, marginBottom: 6 }} />}
      <Ed editable={!!edit} multiline value={b.text} onCommit={(v) => set('text', v)} style={{ fontSize: b.size, color: dark ? th.colors.on_primary : th.colors.text, fontWeight: dark ? 700 : 400, fontFamily: dark ? th.fonts.heading : th.fonts.body, lineHeight: 1.25 }} />
    </div>
  );
}

const isNum = (t) => { const x = t.replace(/[.,\s%−+-]/g, ''); return x.length > 0 && /^\d+$/.test(x); };
function Table({ b, box, th, edit }) {
  const cols = (b.header[0] !== undefined ? b.header.length : b.rows[0].length);
  const numcol = Array.from({ length: cols }, (_, c) => b.rows.every((r) => isNum(r[c]) || !r[c]) && b.rows.some((r) => isNum(r[c])));
  const wsum = b.widths.reduce((a, v) => a + v, 0) || 1;
  const setCell = (ri, ci, v) => edit?.((s) => { s.rows = s.rows.map((r, i) => (i === ri ? r.map((c, j) => (j === ci ? v : c)) : r)); });
  const setHead = (ci, v) => edit?.((s) => { s.header = s.header.map((c, j) => (j === ci ? v : c)); });
  const cell = { padding: '7px 8px', borderBottom: `0.5px solid ${th.colors.line}`, fontSize: b.size, verticalAlign: 'middle', lineHeight: 1.25 };
  return (
    <div style={{ position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h, overflow: 'hidden', fontFamily: th.fonts.body }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
        <colgroup>{b.widths.map((w, i) => <col key={i} style={{ width: `${(w / wsum) * 100}%` }} />)}</colgroup>
        {b.header.length > 0 && <thead><tr>{b.header.map((h, ci) => <th key={ci} style={{ ...cell, background: th.colors.primary, color: th.colors.on_primary, textAlign: numcol[ci] && ci > 0 ? 'right' : 'left', fontWeight: 700 }}><Ed tag="span" editable={!!edit} value={h} onCommit={(v) => setHead(ci, v)} /></th>)}</tr></thead>}
        <tbody>
          {b.rows.map((r, ri) => {
            const hl = b.highlight_row === ri;
            return <tr key={ri} style={{ background: hl ? '#E3F4FD' : ri % 2 ? th.colors.soft : th.colors.bg }}>
              {r.map((c, ci) => <td key={ci} style={{ ...cell, color: th.colors.text, textAlign: numcol[ci] && ci > 0 ? 'right' : 'left', fontWeight: hl || ci === 0 ? 700 : 400 }}><Ed tag="span" editable={!!edit} value={c} onCommit={(v) => setCell(ri, ci, v)} /></td>)}
            </tr>;
          })}
        </tbody>
      </table>
    </div>
  );
}

function Image({ b, box, th, rid }) {
  return (
    <div style={{ position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <img src={api.assetUrl(rid, b.asset_id)} alt={b.caption || ''} style={{ maxWidth: '100%', maxHeight: b.caption ? box.h - 32 : box.h, objectFit: 'contain' }} />
      {b.caption && <div style={{ fontSize: 11, color: th.colors.muted, fontFamily: th.fonts.body, marginTop: 6 }}>{b.caption}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- the slide
/**
 * spec: normalised slide spec · layouts: /api/v1/slide-layouts · theme: deck theme (template or default) · page: shown number
 * onChange(nextSpec): given when the slide may be edited in place; it receives the whole new spec (the server fits it again).
 */
export default function SlideCanvas({ spec, layouts, theme, page, lang = 'de', rid, onChange, className = '' }) {
  const ref = useRef(null);
  const [scale, setScale] = useState(0.5);
  useEffect(() => {
    const el = ref.current; if (!el) return undefined;
    const ro = new ResizeObserver(() => setScale(el.clientWidth / layouts.canvas.w));
    ro.observe(el); setScale(el.clientWidth / layouts.canvas.w);
    return () => ro.disconnect();
  }, [layouts]);
  const th = { ...theme, colors: { ...theme.colors }, fonts: theme.fonts, palette: theme.palette };
  const L = layouts.layouts[spec.layout];
  const mut = (fn) => { const next = JSON.parse(JSON.stringify(spec)); fn(next); onChange(next); };
  const editTitle = (v) => mut((s) => { s.title = v || s.title; });
  const editSubtitle = (v) => mut((s) => { s.subtitle = v; });
  const editBlock = (slot) => (fn) => mut((s) => { const blk = s.blocks.find((x) => x.slot === slot); if (blk) fn(blk); });
  const editable = !!onChange;

  let inner;
  if (spec.kind === 'title') {
    inner = (
      <>
        <div style={{ position: 'absolute', inset: 0, background: th.colors.primary }} />
        <div style={{ position: 'absolute', left: 56, top: 250, width: 8, height: 190, background: th.colors.accent }} />
        <div style={{ position: 'absolute', left: 88, top: 240, width: 1100, height: 130, fontFamily: th.fonts.heading, fontWeight: 700, fontSize: (spec.title_size || 40) + 10, color: th.colors.on_primary, lineHeight: 1.1 }}>
          <Ed editable={editable} multiline value={spec.title} onCommit={editTitle} />
        </div>
        <div style={{ position: 'absolute', left: 88, top: 392, width: 1100, height: 60, fontFamily: th.fonts.body, fontSize: 22, color: '#C9D6E6' }}>
          <Ed editable={editable} value={spec.subtitle || ''} onCommit={editSubtitle} />
        </div>
      </>
    );
  } else {
    inner = (
      <>
        <div style={{ position: 'absolute', left: 56, top: 40, width: 6, height: 70, background: th.colors.accent }} />
        <div style={{ position: 'absolute', left: 76, top: layouts.title_box.y, width: 1148, height: layouts.title_box.h, display: 'flex', alignItems: 'center', fontFamily: th.fonts.heading, fontWeight: 700, fontSize: spec.title_size, color: th.colors.primary, lineHeight: 1.1 }}>
          <Ed editable={editable} multiline value={spec.title} onCommit={editTitle} />
        </div>
        {spec.blocks.map((b) => {
          const box = L.slots[b.slot]; const ed = editable ? editBlock(b.slot) : null;
          if (b.type === 'bullets') return <Bullets key={b.slot} b={b} box={box} th={th} edit={ed} />;
          if (b.type === 'kpis') return <Kpis key={b.slot} b={b} box={box} th={th} edit={ed} lang={lang} />;
          if (b.type === 'chart') return <Chart key={b.slot} b={b} box={box} th={th} lang={lang} />;
          if (b.type === 'table') return <Table key={b.slot} b={b} box={box} th={th} edit={ed} />;
          if (b.type === 'callout') return <Callout key={b.slot} b={b} box={box} th={th} edit={ed} />;
          if (b.type === 'image') return <Image key={b.slot} b={b} box={box} th={th} rid={rid} />;
          return null;
        })}
        <div style={{ position: 'absolute', left: layouts.footer_box.x, top: layouts.footer_box.y - 6, width: 1168, height: 0.5, background: th.colors.line }} />
        {spec.source_line && <div style={{ position: 'absolute', left: layouts.footer_box.x, top: layouts.footer_box.y, width: layouts.footer_box.w, fontSize: 11, color: th.colors.muted, fontFamily: th.fonts.body }}>{spec.source_line}</div>}
        <div style={{ position: 'absolute', left: layouts.page_box.x, top: layouts.page_box.y, width: layouts.page_box.w, textAlign: 'right', fontSize: 11, color: th.colors.muted, fontFamily: th.fonts.body }}>{page}</div>
      </>
    );
  }
  return (
    <div ref={ref} className={`sc-frame ${className}`} style={{ position: 'relative', width: '100%', aspectRatio: `${layouts.canvas.w} / ${layouts.canvas.h}`, overflow: 'hidden', background: th.colors.bg }}>
      <div className="sc-canvas" style={{ position: 'absolute', left: 0, top: 0, width: layouts.canvas.w, height: layouts.canvas.h, transform: `scale(${scale})`, transformOrigin: '0 0' }}>{inner}</div>
    </div>
  );
}
