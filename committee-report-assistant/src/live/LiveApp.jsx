// Live mode: the same product, but every screen works on the real backend (reports, files, agents, deck, audit).
import { useCallback, useEffect, useState } from 'react';
import { Check, ChevronLeft, Lock, Plus, Trash2, ScrollText, AlertTriangle, ServerCrash, Cpu } from 'lucide-react';
import { t } from '../i18n.js';
import { Brand, LangToggle } from '../components/TopBar.jsx';
import ModeToggle from './ModeToggle.jsx';
import { api } from './client.js';
import { errText, Spin, useAction, useCase } from './kit.jsx';
import LiveBrief from './LiveBrief.jsx';
import LiveAnalysis from './LiveAnalysis.jsx';
import LiveReport from './LiveReport.jsx';
import LiveAudit from './LiveAudit.jsx';
import './live.css';

const RID_KEY = 'coe4.live.report';
const rememberRid = (rid) => { try { if (rid) sessionStorage.setItem(RID_KEY, rid); else sessionStorage.removeItem(RID_KEY); } catch { /* ignore */ } };
const recallRid = () => { try { return sessionStorage.getItem(RID_KEY); } catch { return null; } };

/** What the page learns from /system/status: is everything up, and do the agents use a language model? */
function useStatus() {
  const [st, setSt] = useState(undefined); // undefined = asking, null = backend unreachable
  const check = useCallback(() => api.status().then(setSt).catch(() => setSt(null)), []);
  useEffect(() => { check(); const id = setInterval(check, 20000); return () => clearInterval(id); }, [check]);
  return [st, check];
}

function StatusBanner({ st, check }) {
  if (st === undefined) return null;
  if (st === null) {
    return (
      <div className="lv-banner crit" role="alert"><ServerCrash size={20} />
        <div><strong>{t('The backend is not reachable')}</strong><span>{t('Start it with “uvicorn app.main:app --port 8001” in the backend folder, then try again.')}</span></div>
        <button className="btn sm" onClick={check}>{t('Try again')}</button></div>
    );
  }
  if (st.agents === 'down') {
    return <div className="lv-banner warn" role="alert"><AlertTriangle size={20} /><div><strong>{t('The agents service is not reachable')}</strong><span>{t('Start it with “uvicorn app.main:app --port 8002” in the agents folder. Until then every step that needs an agent will fail.')}</span></div><button className="btn sm" onClick={check}>{t('Try again')}</button></div>;
  }
  if (!st.llm?.configured) {
    return <div className="lv-banner warn"><Cpu size={20} /><div><strong>{t('Agents run without a language model')}</strong><span>{t('No Foundry deployment is configured (agents/.env), so the agents use their fixed rules: the structure works, the analysis stays shallow. See the README for the settings.')}</span></div></div>;
  }
  return null;
}

function LiveBar({ c, tab, setTab, onHome, lang, setLang, mode, setMode, st }) {
  const reached = c?.stage || 1;
  const steps = [
    { id: 'brief', n: 1, label: 'Brief' }, { id: 'analysis', n: 2, label: 'Analysis' }, { id: 'report', n: 3, label: 'Report' },
  ];
  return (
    <header className="topbar">
      <div className="topbar-in">
        <div className="tb-left"><Brand onClick={onHome} /><button className="btn quiet sm" onClick={onHome}><ChevronLeft size={15} /> {t('All reports')}</button></div>
        <nav className="stepper" aria-label={t('Progress')}>
          {steps.map((s, i) => {
            const ok = s.n <= reached;
            const state = tab === s.id ? 'current' : ok && s.n < reached ? 'done' : 'todo';
            return (
              <div key={s.id} className="step-wrap">
                {i > 0 && <span className={`step-line${state !== 'todo' || tab === 'audit' || reached > i ? ' on' : ''}`} />}
                <button className={`step ${state}`} disabled={!ok} onClick={() => setTab(s.id)} aria-current={tab === s.id ? 'step' : undefined}>
                  <span className="step-dot">{state === 'done' ? <Check size={14} strokeWidth={2.4} /> : s.n}</span>
                  <span className="step-text"><span className="step-label">{t(s.label)}</span></span>
                </button>
              </div>
            );
          })}
          <div className="step-wrap">
            <span className="step-line on" />
            <button className={`step audit ${tab === 'audit' ? 'current' : 'done'}`} onClick={() => setTab('audit')} aria-current={tab === 'audit' ? 'step' : undefined}>
              <span className="step-dot"><ScrollText size={14} /></span>
              <span className="step-text"><span className="step-label">{t('Agent log')}</span></span>
            </button>
          </div>
        </nav>
        <div className="tb-right">
          <ModeToggle mode={mode} setMode={setMode} />
          <LangToggle lang={lang} setLang={setLang} />
          {c && <span className="pill info" title={t('Version and step of this report')}>{c.version} · {stateLabel(c.state)}</span>}
          <span className="lv-lock" title={st?.llm?.configured ? `${st.llm.deployment || ''} · ${st.llm.auth || ''}` : t('Stays in VW environment')}><Lock size={14} /></span>
        </div>
      </div>
    </header>
  );
}

const STATE_DE = {
  SETUP: 'Brief', OUTLINE_REVIEW: 'Gliederung', COLLECTING: 'Recherche', ANALYSING: 'Analyse', FINDINGS_REVIEW: 'Prüfung', GENERATING: 'Folien', DECK_REVIEW: 'Folienprüfung', FINAL: 'Final', FEEDBACK: 'Rückmeldung',
};
const STATE_EN = {
  SETUP: 'Brief', OUTLINE_REVIEW: 'Outline', COLLECTING: 'Research', ANALYSING: 'Analysis', FINDINGS_REVIEW: 'Review', GENERATING: 'Slides', DECK_REVIEW: 'Slide review', FINAL: 'Final', FEEDBACK: 'Feedback',
};
export const stateLabel = (s) => (t('Language') === 'Sprache' ? STATE_DE : STATE_EN)[s] || s;

function LiveHome({ onOpen, toast, lang, setLang, mode, setMode, st, check }) {
  const [reports, setReports] = useState(null);
  const [committees, setCommittees] = useState([]);
  const [title, setTitle] = useState('');
  const [committee, setCommittee] = useState('');
  const [busy, run] = useAction(toast);
  const load = useCallback(() => api.reports().then(setReports).catch((e) => { setReports([]); toast(errText(e), 'warn'); }), [toast]);
  useEffect(() => { load(); api.committees().then(setCommittees).catch(() => {}); }, [load]);
  const create = () => run('create', async () => {
    const r = await api.createReport(title.trim() || t('New committee report'), committee || null);
    if (committee) await api.putCase(r.id, { committee_id: committee, lang });
    else await api.putCase(r.id, { lang });
    onOpen(r.id);
  });
  return (
    <>
      <header className="topbar plain"><div className="topbar-in">
        <div className="tb-left"><Brand onClick={() => {}} /></div>
        <div className="tb-right"><ModeToggle mode={mode} setMode={setMode} /><LangToggle lang={lang} setLang={setLang} /><span className="secure"><Lock size={13} /> {t('Stays in VW environment')}</span></div>
      </div></header>
      <StatusBanner st={st} check={check} />
      <div className="lv-home">
        <p className="eyebrow">{t('Live')}</p>
        <h1 className="display lg">{t('Your committee reports,')} <em>{t('analysed for real.')}</em></h1>
        <p className="lede">{t('Live mode reads your files, researches the web, checks every claim against its source and builds the slides on the server. Nothing here is sample data.')}</p>
        <div className="card pad lv-new">
          <h2>{t('New report')}</h2>
          <div className="lv-row">
            <input className="lv-in grow" value={title} placeholder={t('Title, e.g. “Supplier decision battery housings”')} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && create()} />
            <select className="lv-in" value={committee} onChange={(e) => setCommittee(e.target.value)} aria-label={t('Committee')}>
              <option value="">{t('Committee (optional)')}</option>
              {committees.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <button className="btn primary" disabled={!!busy || st === null} onClick={create}>{busy === 'create' ? <Spin /> : <Plus size={16} />} {t('Create')}</button>
          </div>
        </div>
        <div className="home-section">
          <div className="sec-head"><h2>{t('Reports on this server')}</h2></div>
          {reports === null ? <p className="muted"><Spin /> {t('Loading…')}</p> : reports.length === 0 ? <p className="muted">{t('No report yet. Create the first one above.')}</p> : (
            <div className="rep-list">
              {reports.map((r) => (
                <div key={r.id} className="lv-rep">
                  <button className="lv-rep-main" onClick={() => onOpen(r.id)}>
                    <strong>{r.title}</strong><span className="muted small">{[r.committee, r.date, r.version].filter(Boolean).join(' · ')}</span>
                  </button>
                  <span className="pill info">{t('Step {n}', { n: r.stage })}</span>
                  <button className="iconbtn" title={t('Delete')} onClick={() => window.confirm(t('Delete this report with all its files and results?')) && run('del', async () => { await api.deleteReport(r.id); load(); })}><Trash2 size={16} /></button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export default function LiveApp({ lang, setLang, mode, setMode, toast }) {
  const [st, checkStatus] = useStatus();
  const [rid, setRid] = useState(recallRid);
  const [tab, setTab] = useState('brief');
  const [layouts, setLayouts] = useState(null);
  const open = (id) => { rememberRid(id); setRid(id); setTab('brief'); window.scrollTo({ top: 0 }); };
  const home = () => { rememberRid(null); setRid(null); };
  useEffect(() => { api.layouts().then(setLayouts).catch(() => {}); }, [st === null]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!rid) return <LiveHome onOpen={open} toast={toast} lang={lang} setLang={setLang} mode={mode} setMode={setMode} st={st} check={checkStatus} />;
  return <Workspace rid={rid} tab={tab} setTab={setTab} home={home} layouts={layouts} lang={lang} setLang={setLang} mode={mode} setMode={setMode} toast={toast} st={st} checkStatus={checkStatus} />;
}

function Workspace({ rid, tab, setTab, home, layouts, lang, setLang, mode, setMode, toast, st, checkStatus }) {
  const { c, err, reload } = useCase(rid);
  const go = useCallback((id) => { setTab(id); window.scrollTo({ top: 0 }); }, [setTab]);
  // a report that is further along opens on its current step
  const [placed, setPlaced] = useState(false);
  useEffect(() => { if (c && !placed) { setPlaced(true); setTab(['brief', 'brief', 'analysis', 'report'][c.stage] || 'brief'); } }, [c, placed, setTab]);
  if (err?.status === 404) { home(); return null; }
  return (
    <>
      <LiveBar c={c} tab={tab} setTab={setTab} onHome={home} lang={lang} setLang={setLang} mode={mode} setMode={setMode} st={st} />
      <StatusBanner st={st} check={checkStatus} />
      {!c ? <div className="lv-stage"><p className="muted"><Spin /> {err ? errText(err) : t('Loading…')}</p></div> : (
        <div className="stage-anim" key={tab}>
          {tab === 'brief' && <LiveBrief rid={rid} c={c} reload={reload} lang={lang} st={st} toast={toast} go={go} />}
          {tab === 'analysis' && <LiveAnalysis rid={rid} c={c} reload={reload} toast={toast} go={go} />}
          {tab === 'report' && <LiveReport rid={rid} c={c} reload={reload} layouts={layouts} lang={lang} toast={toast} go={go} />}
          {tab === 'audit' && <LiveAudit rid={rid} c={c} toast={toast} />}
        </div>
      )}
    </>
  );
}
