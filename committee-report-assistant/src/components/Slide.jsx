import { t } from '../i18n.js';
import { useLayoutEffect, useRef, useState } from 'react';
import { CapacityChart, CostChart, PriceChart, RiskMatrix, Gantt, OptionsTable, riskLevel } from './Charts.jsx';
import { RISKS, USER, fmtDate, slideText } from '../data.js';

/** Scales a fixed 960x540 slide to whatever width its container has. */
export function SlideFrame({ children, className = '' }) {
  const ref = useRef(null);
  const [w, setW] = useState(960);
  useLayoutEffect(() => {
    const el = ref.current;
    setW(el.getBoundingClientRect().width || 960);
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={ref} className={`frame ${className}`} style={{ height: (w * 9) / 16 }}>
      <div className="frame-in" style={{ transform: `scale(${w / 960})` }}>{children}</div>
    </div>
  );
}

function Ed({ as: Tag = 'div', value, editable, onCommit, className }) {
  if (!editable) return <Tag className={className}>{value}</Tag>;
  return (
    <Tag
      className={`${className || ''} editable`} contentEditable suppressContentEditableWarning spellCheck={false}
      onBlur={(e) => { const txt = e.currentTarget.textContent.trim(); if (txt !== value) onCommit(txt); }}
    >
      {value}
    </Tag>
  );
}

export function Slide({ slide, ctx, editable = false, onEdit = () => {} }) {
  const { qc, committee, date, n } = ctx;
  const show = (s) => slideText(s, slide.qcv);
  const bullets = (cls = '') => (
    <ul className={`sl-bullets ${cls}`}>
      {slide.bullets.map((b, i) => (
        <Ed as="li" key={`${slide.id}-${i}-${b}`} value={show(b)} editable={editable} onCommit={(txt) => onEdit({ bullets: slide.bullets.map((x, k) => (k === i ? txt : x)).filter(Boolean) })} />
      ))}
    </ul>
  );

  if (slide.layout === 'title') {
    return (
      <div className="slide sl-cover">
        <div className="cover-bar" />
        <p className="cover-kicker">{t(committee)} · {t('Committee report')}</p>
        <Ed as="h1" className="cover-title" value={t(slide.title)} editable={editable} onCommit={(txt) => onEdit({ title: txt })} />
        <p className="cover-sub">{t(committee)} · {fmtDate(date)} · {t(USER.dept)} · {slide.meta?.version}</p>
        <p className="cover-foot">{t("Confidential · For committee use only")}</p>
      </div>
    );
  }

  return (
    <div className={`slide sl-${slide.layout}`}>
      <div className="sl-top"><span>{t(committee)} · {fmtDate(date)}</span><i /></div>
      <Ed as="h2" className="sl-title" value={show(slide.title)} editable={editable} onCommit={(txt) => onEdit({ title: txt })} />
      <div className="sl-body">
        {slide.layout === 'summary' && (
          <>
            {bullets()}
            {slide.decision && <div className="sl-decision"><b>{t("Decision requested")}</b><span>{show(slide.decision).replace(/^[^:]+:\s*/, '')}</span></div>}
          </>
        )}
        {slide.layout === 'text' && bullets('wide')}
        {slide.layout === 'capacity' && (<>{bullets('half')}<div className="sl-chart"><CapacityChart /></div></>)}
        {slide.layout === 'table' && <div className="sl-wide"><OptionsTable qc={qc} /></div>}
        {slide.layout === 'charts' && (<><div className="sl-chart"><CostChart /></div><div className="sl-chart"><PriceChart /></div></>)}
        {slide.layout === 'risk' && (
          <>
            <div className="sl-chart narrow"><RiskMatrix /></div>
            <ul className="sl-risks">
              {RISKS.map((r) => <li key={r.id}><b>{r.id}</b><span>{t(r.name)}</span><em className={riskLevel(r).toLowerCase()}>{t(riskLevel(r))}</em></li>)}
            </ul>
          </>
        )}
        {slide.layout === 'timeline' && (<div className="sl-wide"><Gantt />{bullets('small')}</div>)}
      </div>
      <div className="sl-foot"><span>{t("Confidential · For committee use only")}</span><span>{n}</span></div>
    </div>
  );
}
