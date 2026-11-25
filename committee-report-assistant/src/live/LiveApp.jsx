// Live mode: the same product, but every screen works on the real backend (reports, files, agents, deck, audit).
import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, ArrowUp, CalendarDays, Check, History, Lock, Mic, ScrollText, Trash2, AlertTriangle, ServerCrash, Cpu } from 'lucide-react';
import { t } from '../i18n.js';
import { Brand, LangToggle } from '../components/TopBar.jsx';
import ModeToggle from './ModeToggle.jsx';
import { api } from './client.js';
import { errText, Spin, useAction, useCase } from './kit.jsx';
import { fmtDate } from '../data.js';

const daysUntil = (iso) => Math.round((Date.UTC(...iso.split('-').map((x, i) => (i === 1 ? +x - 1 : +x))) - Date.now()) / 864e5);
import LiveBrief from './LiveBrief.jsx';
import LiveDraft from './LiveDraft.jsx';
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

// the same top bar as the demo: brand, the two steps with a caption, language, and the report's version. Only what is real is shown.
const STEPS = [{ id: 'brief', n: 1, label: 'Brief', sub: 'Tell me what you know' }, { id: 'draft', n: 2, label: 'Draft', sub: 'Adjust and download' }];

function caption(n, c) {
  if (n === 1) return c.counts.files ? t('{n} files', { n: c.counts.files }) : t('Not started');
  if (['SETUP', 'OUTLINE_REVIEW'].includes(c.state)) return t('Not started');
  if (c.state !== 'DECK_REVIEW') return t('Analysing…');
  return t('{n} slides', { n: c.counts.slides });
}

function LiveBar({ c, tab, setTab, onHome, lang, setLang, mode, setMode, st }) {
  const reached = c?.stage || 1;
  return (
    <header className="topbar">
      <div className="topbar-in">
        <div className="tb-left"><Brand onClick={onHome} /></div>
        <nav className="stepper" aria-label={t('Progress')}>
          {STEPS.map((s, i) => {
            const state = tab === s.id ? 'current' : s.n < reached && tab !== s.id ? 'done' : s.n <= reached ? 'done' : 'todo';
            return (
              <div key={s.id} className="step-wrap">
                {i > 0 && <span className={`step-line${state !== 'todo' || reached > i ? ' on' : ''}`} />}
                <button className={`step ${state}`} disabled={s.n > reached} onClick={() => setTab(s.id)} aria-current={tab === s.id ? 'step' : undefined}>
                  <span className="step-dot">{state === 'done' ? <Check size={14} strokeWidth={2.4} /> : s.n}</span>
                  <span className="step-text"><span className="step-label">{t(s.label)}</span><span className="step-cap">{tab === s.id && c ? t(s.sub) : c ? caption(s.n, c) : ''}</span></span>
                </button>
              </div>
            );
          })}
        </nav>
        <div className="tb-right">
          <ModeToggle mode={mode} setMode={setMode} />
          <LangToggle lang={lang} setLang={setLang} />
          <span className="secure" title={st?.llm?.configured ? `${st.llm.deployment || ''} · ${st.llm.auth || ''}` : t('Stays in VW environment')}><Lock size={13} /> {t('Stays in VW environment')}</span>
          {c && <span className="ghost-pill static"><History size={15} /> {c.version} <span className="muted">{t('· Draft')}</span></span>}
          <button className={`btn sm${tab === 'audit' ? ' on' : ''}`} onClick={() => setTab('audit')}><ScrollText size={15} /> {t('Agent log')}</button>
        </div>
      </div>
    </header>
  );
}

const STATE_DE = {
  SETUP: 'Brief', OUTLINE_REVIEW: 'Gliederung', COLLECTING: 'Recherche', ANALYSING: 'Analyse', FINDINGS_REVIEW: 'Folien', GENERATING: 'Folien', DECK_REVIEW: 'Entwurf',
};
const STATE_EN = {
  SETUP: 'Brief', OUTLINE_REVIEW: 'Outline', COLLECTING: 'Research', ANALYSING: 'Analysis', FINDINGS_REVIEW: 'Slides', GENERATING: 'Slides', DECK_REVIEW: 'Draft',
};
export const stateLabel = (s) => (t('Language') === 'Sprache' ? STATE_DE : STATE_EN)[s] || s;

// the same home screen as the demo; the committees and the reports are the real ones from the server
function LiveHome({ onOpen, toast, lang, setLang, mode, setMode, st, check }) {
  const [reports, setReports] = useState(null);
  const [committees, setCommittees] = useState([]);
  const [text, setText] = useState('');
  const [busy, run] = useAction(toast);
  const load = useCallback(() => api.reports().then(setReports).catch((e) => { setReports([]); toast(errText(e), 'warn'); }), [toast]);
  useEffect(() => { load(); api.committees().then(setCommittees).catch(() => {}); }, [load]);
  const create = (opts = {}) => run('create', async () => {
    const txt = (opts.text || '').trim();
    const title = txt ? (txt.length > 64 ? `${txt.slice(0, 61).trim()}…` : txt) : t('New committee report');
    const r = await api.createReport(title, opts.committeeId || null);
    await api.putCase(r.id, { lang, ...(opts.committeeId ? { committee_id: opts.committeeId } : {}), ...(txt ? { description: txt } : {}) });
    onOpen(r.id, { autoVoice: !!opts.autoVoice });
  });
  const hour = new Date().getHours();
  const greeting = hour < 11 ? t('Good morning') : hour < 18 ? t('Good afternoon') : t('Good evening');
  const mine = (c) => (reports || []).find((r) => r.committee === c.name);
  return (
    <>
      <header className="topbar plain"><div className="topbar-in">
        <div className="tb-left"><Brand onClick={() => {}} /></div>
        <div className="tb-right"><ModeToggle mode={mode} setMode={setMode} /><LangToggle lang={lang} setLang={setLang} /><span className="secure"><Lock size={13} /> {t('Stays in VW environment')}</span></div>
      </div></header>
      <StatusBanner st={st} check={check} />
      <main className="home">
        <section className="hero">
          <p className="eyebrow">{greeting}</p>
          <h1 className="display xl">{t('What are you')}<br />{t('presenting')} <em>{t('next?')}</em></h1>
          <p className="lede">{t('Say it the way you would to a colleague. I will collect the material, check the numbers and build the slides. You decide at every step.')}</p>
          <form className="hero-input" onSubmit={(e) => { e.preventDefault(); create({ text }); }}>
            <input id="hero-text" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" disabled={st === null}
              placeholder={t('For example: FAKOM on 3 December, dual sourcing for battery cells')} aria-label={t('Describe your next committee report')} />
            <button type="button" className="round ghost" disabled={!!busy || st === null} onClick={() => create({ autoVoice: true })} aria-label={t('Start by speaking')} title={t('Start by speaking')}><Mic size={20} /></button>
            <button type="submit" className="round solid" disabled={!!busy || st === null} aria-label={t('Start report')}>{busy === 'create' ? <Spin /> : <ArrowUp size={20} />}</button>
          </form>
        </section>

        {committees.length > 0 && (
          <section className="home-section">
            <div className="sec-head"><h2>{t('Upcoming committees')}</h2></div>
            <div className="cmt-grid">
              {committees.map((c) => {
                const d = daysUntil(c.date);
                const r = mine(c);
                return (
                  <article key={c.id} className="cmt-card">
                    <div className="cmt-top">
                      <span className="cmt-date"><CalendarDays size={15} /> {fmtDate(c.date)}</span>
                      {d >= 0 && <span className={`due${d < 14 ? ' soon' : ''}`}>{t('in {d} days', { d })}</span>}
                    </div>
                    <h3>{c.name}</h3>
                    <p className="muted">{c.template}</p>
                    {r ? <button className="link-btn" onClick={() => onOpen(r.id)}>{t('Continue report')} <ArrowRight size={15} /></button>
                      : <button className="link-btn" disabled={!!busy} onClick={() => create({ committeeId: c.id })}>{t('Start report')} <ArrowRight size={15} /></button>}
                  </article>
                );
              })}
            </div>
          </section>
        )}

        <section className="home-section">
          <div className="sec-head"><h2>{t('Your reports')}</h2><span className="muted">{reports ? t('{n} reports', { n: reports.length }) : ''}</span></div>
          {reports === null ? <p className="muted"><Spin /> {t('Loading…')}</p> : reports.length === 0 ? <p className="muted">{t('No report yet. Describe your next one above.')}</p> : (
            <div className="rep-list">
              {reports.map((r) => (
                <div key={r.id} className="rep-row live" role="button" tabIndex={0} onClick={() => onOpen(r.id)} onKeyDown={(e) => e.key === 'Enter' && onOpen(r.id)}>
                  <span className="rep-main"><strong>{r.title}</strong><span className="muted">{[r.committee, r.date && fmtDate(r.date)].filter(Boolean).join(' · ')}</span></span>
                  <span className="ver">{r.version}</span>
                  <span className={`status ${r.stage >= 2 ? 'presented' : 'draft'}`}>{r.stage >= 2 ? t('Draft') : t('Brief')}</span>
                  <span className="muted rep-edit">{r.edited}</span>
                  <button className="iconbtn" title={t('Delete')} onClick={(e) => { e.stopPropagation(); window.confirm(t('Delete this report with all its files and results?')) && run('del', async () => { await api.deleteReport(r.id); load(); }); }}><Trash2 size={16} /></button>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </>
  );
}

export default function LiveApp({ lang, setLang, mode, setMode, toast }) {
  const [st, checkStatus] = useStatus();
  const [rid, setRid] = useState(recallRid);
  const [tab, setTab] = useState('brief');
  const [opts, setOpts] = useState({});
  const [layouts, setLayouts] = useState(null);
  const open = (id, o = {}) => { rememberRid(id); setOpts(o); setRid(id); setTab('brief'); window.scrollTo({ top: 0 }); };
  const home = () => { rememberRid(null); setRid(null); };
  useEffect(() => { api.layouts().then(setLayouts).catch(() => {}); }, [st === null]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!rid) return <LiveHome onOpen={open} toast={toast} lang={lang} setLang={setLang} mode={mode} setMode={setMode} st={st} check={checkStatus} />;
  return <Workspace rid={rid} tab={tab} setTab={setTab} home={home} layouts={layouts} lang={lang} setLang={setLang} mode={mode} setMode={setMode} toast={toast} st={st} checkStatus={checkStatus} opts={opts} />;
}

function Workspace({ rid, tab, setTab, home, layouts, lang, setLang, mode, setMode, toast, st, checkStatus, opts }) {
  const { c, err, reload } = useCase(rid);
  const go = useCallback((id) => { setTab(id); window.scrollTo({ top: 0 }); }, [setTab]);
  // a report that is further along opens on its current step
  const [placed, setPlaced] = useState(false);
  useEffect(() => { if (c && !placed) { setPlaced(true); setTab(['brief', 'brief', 'draft'][c.stage] || 'brief'); } }, [c, placed, setTab]);
  if (err?.status === 404) { home(); return null; }
  return (
    <>
      <LiveBar c={c} tab={tab} setTab={setTab} onHome={home} lang={lang} setLang={setLang} mode={mode} setMode={setMode} st={st} />
      <StatusBanner st={st} check={checkStatus} />
      {!c ? <div className="stage"><p className="muted"><Spin /> {err ? errText(err) : t('Loading…')}</p></div> : (
        <div className="stage-anim" key={tab}>
          {tab === 'brief' && <LiveBrief rid={rid} c={c} reload={reload} lang={lang} st={st} toast={toast} go={go} autoVoice={!!opts.autoVoice} />}
          {tab === 'draft' && <LiveDraft rid={rid} c={c} reload={reload} layouts={layouts} lang={lang} toast={toast} go={go} />}
          {tab === 'audit' && <LiveAudit rid={rid} c={c} toast={toast} />}
        </div>
      )}
    </>
  );
}
