import { t } from '../i18n.js';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, AlertTriangle, Loader2, CircleDashed, Bell } from 'lucide-react';
import { RUN_STEPS } from '../data.js';
import { ActionBar, useInterval } from './ui.jsx';

const toEditable = (txt, qc) => t(txt).replace(/%QC%/g, qc).replace(/\{(\d+)\}/g, '[$1]');
const fromEditable = (txt) => txt.replace(/\[(\d+)\]/g, '{$1}');
const CONF = { high: 'High confidence', medium: 'Medium confidence' };

/* =============================== Running view =============================== */
function RunView({ ws, setAnalysis, toast }) {
  const [step, setStep] = useState(0);
  const total = RUN_STEPS.length;
  const done = () => setAnalysis({ status: 'done' });
  useInterval(() => setStep((s) => s + 1), 1150, step < total);
  useEffect(() => {
    if (step >= total) { const tm = setTimeout(done, 800); return () => clearTimeout(tm); }
    return undefined;
  }, [step]); // eslint-disable-line
  const pct = Math.min(100, Math.round((step / total) * 100));
  const finished = RUN_STEPS.slice(0, step);

  return (
    <div className="stage stage-run">
      <header className="stage-head center">
        <p className="eyebrow">{t("Step 2 · Draft")}</p>
        <h1 className="display lg">{t("Reading everything,")} <em>{t("so you do not have to.")}</em></h1>
        <p className="lede">{t("Eight specialists work through your material. You can leave this page. I will tell you when it is ready.")}</p>
      </header>

      <div className="run-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${pct}%` }} /></div>

      <div className="run-grid">
        <ol className="run-steps">
          {RUN_STEPS.map((s, i) => {
            const st = i < step ? 'done' : i === step ? 'active' : 'todo';
            return (
              <li key={s.id} className={st}>
                <span className="rs-ico">{st === 'done' ? <Check size={14} strokeWidth={2.6} /> : st === 'active' ? <Loader2 size={14} className="spin" /> : <CircleDashed size={14} />}</span>
                <span className="rs-main"><strong>{t(s.title)}</strong><span className="mono">{t(s.agent)}</span></span>
              </li>
            );
          })}
        </ol>
        <div className="run-feed card pad">
          <h2>{t("Findings so far")}</h2>
          {finished.length === 0 && <p className="muted">{t("Starting…")}</p>}
          <ul>
            {finished.map((s) => (
              <li key={s.id} className={s.warn ? 'warn' : ''}>
                {s.warn ? <AlertTriangle size={16} /> : <Check size={16} />}
                <span>{t(s.finding)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <ActionBar>
        <div className="ab-text"><strong>{t('Analysing {files} and {n} sources', { files: ws.brief.files.length ? t('{n} files', { n: ws.brief.files.length }) : t('your files'), n: Object.values(ws.brief.connectors).filter(Boolean).length })}</strong><span>{t("Your brief stays editable while this runs.")}</span></div>
        <button className={`btn${ws.analysis.notify ? ' on' : ''}`} onClick={() => { setAnalysis((a) => ({ ...a, notify: !a.notify })); toast(ws.analysis.notify ? t('Notification off') : t('I will notify you in Teams when the draft is ready')); }}><Bell size={16} /> {ws.analysis.notify ? t('Notifying you') : t('Notify me when ready')}</button>
        <button className="btn quiet" onClick={done}>{t("Skip ahead (demo)")}</button>
      </ActionBar>
    </div>
  );
}

export default function StageAnalysis(props) {
  return <RunView {...props} />;
}
