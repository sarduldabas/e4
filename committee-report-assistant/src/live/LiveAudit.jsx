// The agent log (live mode only): which agent did what, on which model, how many tokens, how long, and what the decisions were.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, Bot, ChevronRight, Clock, Cpu, RefreshCw, ScrollText, Zap } from 'lucide-react';
import { t } from '../i18n.js';
import { api } from './client.js';
import { errText, nf, Spin } from './kit.jsx';

const AGENT_DE = {
  'brief': 'Briefing', 'template-analyst': 'Vorlagen-Analyst', 'interviewer': 'Interviewer', 'document-reader': 'Dokument-Leser', 'source-planner': 'Quellenplaner', 'source-screener': 'Quellenprüfer',
  'evidence-extractor': 'Belegsammler', 'asset-curator': 'Bild- und Tabellenauswahl', 'web-search': 'Websuche', 'section-analyst': 'Abschnittsanalyst', 'verifier': 'Prüfer', 'red-team': 'Gegenprüfer', 'storyline-architect': 'Storyline',
  'slide-writer': 'Folienautor', 'slide-editor': 'Folieneditor', 'feedback-interpreter': 'Rückmeldungs-Interpret', 'web-researcher': 'Web-Recherche',
};
const name = (id) => (t('Language') === 'Sprache' ? AGENT_DE[id] || id : id);
const ms = (v) => (v >= 60000 ? `${Math.floor(v / 60000)} min ${Math.round((v % 60000) / 1000)} s` : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`);
const time = (iso) => new Date(iso).toLocaleTimeString(t('Language') === 'Sprache' ? 'de-DE' : 'en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

function Tile({ icon, label, value, sub }) {
  return <div className="lv-tile">{icon}<b>{value}</b><span>{label}</span>{sub && <small>{sub}</small>}</div>;
}

export default function LiveAudit({ rid, c, toast }) {
  const [sum, setSum] = useState(null);
  const [runs, setRuns] = useState(null);
  const [events, setEvents] = useState([]);
  const [filter, setFilter] = useState('');
  const [openRun, setOpenRun] = useState(null);
  const [io, setIo] = useState({});
  const load = useCallback(async () => {
    try { const [s, r, e] = await Promise.all([api.runSummary(rid), api.runs(rid), api.events(rid)]); setSum(s); setRuns(r); setEvents(e); } catch (er) { toast(errText(er), 'warn'); }
  }, [rid, toast]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (!['COLLECTING', 'ANALYSING', 'GENERATING'].includes(c.state)) return undefined; const id = setInterval(load, 4000); return () => clearInterval(id); }, [c.state, load]);
  const showIo = async (id) => {
    setOpenRun(openRun === id ? null : id);
    if (!io[id] && openRun !== id) { try { const all = await api.runs(rid, true); setIo(Object.fromEntries(all.map((r) => [r.id, { input: r.input, output: r.output }]))); } catch (e) { toast(errText(e), 'warn'); } }
  };
  const shown = useMemo(() => (runs || []).filter((r) => !filter || r.agent === filter), [runs, filter]);
  if (!sum || !runs) return <div className="lv-stage"><p className="muted"><Spin /> {t('Loading…')}</p></div>;
  const tot = sum.total; const tokens = tot.prompt_tokens + tot.completion_tokens;
  const maxMs = Math.max(1, ...sum.agents.map((a) => a.duration_ms));
  return (
    <div className="lv-stage wide">
      <div className="stage-head compact">
        <div><p className="eyebrow">{t('Agent log')}</p><h1 className="display md">{t('Who did what')}</h1></div>
        <button className="btn sm" onClick={load}><RefreshCw size={14} /> {t('Refresh')}</button>
      </div>
      <div className="lv-tiles">
        <Tile icon={<Bot size={18} />} label={t('agent calls')} value={nf(tot.calls)} sub={t('{a} on the model · {b} on rules', { a: tot.llm, b: tot.rules })} />
        <Tile icon={<Zap size={18} />} label={t('tokens')} value={nf(tokens)} sub={t('{a} in · {b} out', { a: nf(tot.prompt_tokens), b: nf(tot.completion_tokens) })} />
        <Tile icon={<Clock size={18} />} label={t('agent time')} value={ms(tot.duration_ms)} sub={t('parallel calls overlap')} />
        <Tile icon={<Activity size={18} />} label={t('errors')} value={nf(tot.errors)} sub={tot.errors ? t('see the table') : t('none')} />
      </div>
      {tot.rules > 0 && tot.llm === 0 && <div className="lv-banner warn"><Cpu size={20} /><div><strong>{t('No call used a language model')}</strong><span>{t('All agents ran on their fixed rules. Configure the Foundry deployment in agents/.env to get the real analysis.')}</span></div></div>}
      <div className="card pad">
        <div className="card-head"><h2>{t('By agent')}</h2></div>
        {sum.agents.length === 0 ? <p className="muted">{t('No agent has run yet.')}</p> : (
          <table className="lv-table">
            <thead><tr><th>{t('Agent')}</th><th className="r">{t('Calls')}</th><th className="r">{t('Model')}</th><th className="r">{t('Rules')}</th><th className="r">{t('Errors')}</th><th className="r">{t('Tokens in')}</th><th className="r">{t('Tokens out')}</th><th>{t('Time')}</th></tr></thead>
            <tbody>{sum.agents.map((a) => (
              <tr key={a.agent} className={filter === a.agent ? 'on' : ''} onClick={() => setFilter(filter === a.agent ? '' : a.agent)}>
                <td><strong>{name(a.agent)}</strong><div className="muted small">{a.models.join(', ')}</div></td>
                <td className="r">{a.calls}</td><td className="r">{a.llm}</td><td className="r">{a.rules}</td><td className={`r${a.errors ? ' bad' : ''}`}>{a.errors}</td>
                <td className="r">{nf(a.prompt_tokens)}</td><td className="r">{nf(a.completion_tokens)}</td>
                <td><div className="lv-meter"><i style={{ width: `${(a.duration_ms / maxMs) * 100}%` }} /></div><span className="muted small">{ms(a.duration_ms)}</span></td>
              </tr>))}</tbody>
          </table>
        )}
      </div>
      <div className="card pad">
        <div className="card-head"><h2>{t('Every call')} {filter && <button className="pill info" onClick={() => setFilter('')}>{name(filter)} ×</button>}</h2><span className="muted small">{t('{n} calls', { n: shown.length })}</span></div>
        <ul className="lv-runs">
          {shown.map((r) => (
            <li key={r.id} className={r.status !== 'ok' ? 'bad' : ''}>
              <button onClick={() => showIo(r.id)} aria-expanded={openRun === r.id}>
                <ChevronRight size={14} className={openRun === r.id ? 'rot' : ''} />
                <span className="mono small">{time(r.at)}</span><strong>{name(r.agent)}</strong>
                <span className={`pill ${r.mode === 'llm' ? 'info' : ''}`}>{r.mode === 'llm' ? (r.model || t('model')) : t('rules')}</span>
                {r.status !== 'ok' && <span className="pill warn">{r.status}</span>}
                <span className="grow" />
                <span className="muted small">{r.usage?.prompt_tokens != null ? `${nf(r.usage.prompt_tokens)} → ${nf(r.usage.completion_tokens)} ${t('tokens')}` : ''}</span>
                <span className="muted small lv-w">{ms(r.duration_ms || 0)}</span>
              </button>
              {(r.note || r.error) && <p className="muted small lv-rnote">{r.error || r.note}</p>}
              {openRun === r.id && <div className="lv-io">{io[r.id] ? <><h4>{t('Input')}</h4><pre>{JSON.stringify(io[r.id].input, null, 1)}</pre><h4>{t('Output')}</h4><pre>{JSON.stringify(io[r.id].output, null, 1)}</pre></> : <Spin />}</div>}
            </li>
          ))}
        </ul>
      </div>
      <div className="card pad">
        <div className="card-head"><h2><ScrollText size={17} /> {t('Decisions and state changes')}</h2></div>
        <ul className="lv-events">{events.slice(-60).reverse().map((e, i) => <li key={i}><span className="mono small">{time(e.at)}</span><strong>{e.kind.replace(/_/g, ' ')}</strong><span className="muted small">{Object.entries(e.payload || {}).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ')}</span></li>)}</ul>
      </div>
    </div>
  );
}
