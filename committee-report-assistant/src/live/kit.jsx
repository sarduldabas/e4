// Small shared pieces of the live screens.
import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { t } from '../i18n.js';
import { api } from './client.js';

export const errText = (e) => (e?.status === 0 ? t('The backend is not reachable. Is it running on port 8001?') : e?.message || String(e));

export function Spin({ size = 16 }) { return <Loader2 size={size} className="spin" aria-hidden="true" />; }

/** Runs `fn` with a busy flag and shows a failure as a toast, so every button handler stays one line. */
export function useAction(toast) {
  const [busy, setBusy] = useState(null);
  const run = useCallback(async (key, fn) => {
    setBusy(key || true);
    try { return await fn(); } catch (e) { if (e.name !== 'AbortError') toast?.(errText(e), 'warn'); return undefined; } finally { setBusy(null); }
  }, [toast]);
  return [busy, run];
}

const BUSY_STATES = ['COLLECTING', 'ANALYSING', 'GENERATING'];

/** The case of a report, kept fresh: polled while an agent job runs, otherwise only when `reload` is called. */
export function useCase(rid) {
  const [c, setC] = useState(null);
  const [err, setErr] = useState(null);
  const alive = useRef(true);
  const reload = useCallback(async () => {
    try { const v = await api.case(rid); if (alive.current) { setC(v); setErr(null); } return v; } catch (e) { if (alive.current) setErr(e); return null; }
  }, [rid]);
  useEffect(() => { alive.current = true; setC(null); reload(); return () => { alive.current = false; }; }, [reload]);
  const busy = !!c && (BUSY_STATES.includes(c.state) || c.job?.status === 'running' || c.job?.status === 'queued');
  useEffect(() => {
    if (!busy && !err) return undefined;
    const id = setInterval(reload, err ? 4000 : 1500);
    return () => clearInterval(id);
  }, [busy, err, reload]);
  return { c, err, reload, busy };
}

/** Calls `fn` shortly after `value` stopped changing. */
export function useDebouncedEffect(fn, deps, ms = 800, enabled = true) {
  const f = useRef(fn); f.current = fn;
  useEffect(() => {
    if (!enabled) return undefined;
    const id = setTimeout(() => f.current(), ms);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled]);
}

export const bytes = (n) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`);
export const nf = (n) => Number(n || 0).toLocaleString('de-DE');

export function Empty({ icon, title, children }) {
  return <div className="lv-empty">{icon}<strong>{title}</strong>{children && <span>{children}</span>}</div>;
}

export function ProgressBar({ done, total }) {
  const p = total ? Math.min(100, Math.round((done / total) * 100)) : 0;
  return <div className="lv-bar" role="progressbar" aria-valuenow={p} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${p}%` }} /></div>;
}
