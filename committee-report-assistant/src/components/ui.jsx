import { t } from '../i18n.js';
import { useEffect, useRef, useState } from 'react';
import {
  Presentation, FileText, Table2, Mail, MessageSquare, BookOpen, Ticket, Library, Globe, Link2, X, Check,
} from 'lucide-react';
import { PEOPLE } from '../data.js';

const KIND_ICON = {
  pptx: Presentation, pdf: FileText, xlsx: Table2, mail: Mail, chat: MessageSquare,
  confluence: BookOpen, jira: Ticket, wiki: Library, web: Globe, link: Link2,
};
export function SourceIcon({ kind, size = 16 }) {
  const I = KIND_ICON[kind] || FileText;
  return <I size={size} strokeWidth={1.6} aria-hidden="true" />;
}

export function Avatar({ id, size = 28, ring = true }) {
  const p = PEOPLE.find((x) => x.id === id);
  if (!p) return null;
  return (
    <span className={`avatar${ring ? ' ring' : ''}`} style={{ width: size, height: size, background: p.color, fontSize: size * 0.38 }} title={p.name}>
      {p.initials}
    </span>
  );
}
export function Avatars({ ids, size = 28 }) {
  return <span className="avatars">{ids.map((id) => <Avatar key={id} id={id} size={size} />)}</span>;
}

/** Text with {n} citation tokens and %QC% placeholder. */
export function RichText({ text, qc, onCite, active }) {
  const parts = t(text).replace(/%QC%/g, qc).split(/(\{\d+\})/);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\{(\d+)\}$/);
        if (!m) return <span key={i}>{p}</span>;
        const n = Number(m[1]);
        return (
          <button key={i} type="button" className={`cite${active === n ? ' on' : ''}`} onClick={() => onCite?.(n)} aria-label={t('Source {n}', { n })}>
            {n}
          </button>
        );
      })}
    </>
  );
}

export function Modal({ title, onClose, children, width = 560, footer }) {
  useEffect(() => {
    const k = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [onClose]);
  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ width }} role="dialog" aria-modal="true" aria-label={title}>
        <header className="modal-head">
          <h2>{title}</h2>
          <button className="iconbtn" onClick={onClose} aria-label={t("Close")}><X size={18} /></button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>
  );
}

export function Drawer({ title, onClose, children, width = 460 }) {
  useEffect(() => {
    const k = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [onClose]);
  return (
    <div className="scrim right" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="drawer" style={{ width }} role="dialog" aria-modal="true" aria-label={title}>
        <header className="modal-head">
          <h2>{title}</h2>
          <button className="iconbtn" onClick={onClose} aria-label={t("Close")}><X size={18} /></button>
        </header>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}

export function Toasts({ items }) {
  return (
    <div className="toasts" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className="toast"><Check size={16} /> <span>{t.text}</span></div>
      ))}
    </div>
  );
}

export function useToasts() {
  const [items, setItems] = useState([]);
  const push = (text) => {
    const id = Math.random().toString(36).slice(2);
    setItems((x) => [...x, { id, text }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 3200);
  };
  return [items, push];
}

export function ActionBar({ children }) {
  return <div className="actionbar-wrap"><div className="actionbar">{children}</div></div>;
}

export function ProgressRing({ value, size = 96, stroke = 7 }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={t('{v} percent', { v: value })}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth={stroke} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--accent)" strokeWidth={stroke} strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={c * (1 - value / 100)} transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dashoffset .6s cubic-bezier(.2,.8,.2,1)' }}
      />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" className="ring-num">{value}</text>
    </svg>
  );
}

export function useInterval(fn, ms, on = true) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (!on) return undefined;
    const id = setInterval(() => ref.current(), ms);
    return () => clearInterval(id);
  }, [ms, on]);
}
