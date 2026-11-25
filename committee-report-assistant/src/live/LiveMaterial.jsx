// What the draft is made from: the progress screen while the research runs, and the material behind the slides (sources, pictures and charts, research plan).
import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, BarChart3, Check, CircleDashed, ExternalLink, FileText, Globe, ImageIcon, Loader2, RefreshCw, Search, UserRound } from 'lucide-react';
import { t } from '../i18n.js';
import { api } from './client.js';
import { Empty, nf, Spin, useAction } from './kit.jsx';
import { ActionBar } from '../components/ui.jsx';

// one list for the whole run: research, analysis and the first draft of the slides (same screen as the demo's, with the real progress)
const STEPS = [['reading', 'Reading your material', 'Reader'], ['planning', 'Planning the research', 'Research planner'], ['searching', 'Searching the web and sources', 'Web researcher'],
  ['gaps', 'Closing the gaps', 'Research planner'], ['assets', 'Looking at pictures and charts', 'Asset analyst'], ['analysing', 'Analysing the sections', 'Analyst'],
  ['red-team', 'Cross-checking the whole draft', 'Cross-checker'], ['storyline', 'Planning the storyline', 'Storyline architect'], ['writing slides', 'Writing the slides', 'Slide writer'],
  ['building file', 'Building the PowerPoint file', 'Builder']];
const ALIAS = { extracting: 'reading', screening: 'searching', collected: 'assets', analysed: 'red-team', done: 'building file' };

export function Running({ rid, c, onRetry, busy, onBack }) {
  const j = c.job; const p = j?.progress || {};
  const idx = Math.max(0, STEPS.findIndex(([k]) => k === (ALIAS[p.step] || p.step)));
  const failed = j?.status === 'failed';
  const pct = p.total ? Math.min(100, Math.round((p.done / p.total) * 100)) : Math.round((idx / STEPS.length) * 100);
  const log = (p.log || []).slice(-8);
  return (
    <div className="stage stage-run">
      <header className="stage-head center">
        <p className="eyebrow">{t('Step 2 · Draft')}</p>
        <h1 className="display lg">{failed ? t('The draft could not be finished') : <>{t('Reading everything,')} <em>{t('so you do not have to.')}</em></>}</h1>
        <p className="lede">{failed ? j.error : t('The agents work through your material. You can leave this page: the work continues on the server and the draft opens here when it is ready.')}</p>
      </header>

      <div className="run-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${failed ? pct : pct}%` }} /></div>

      <div className="run-grid">
        <ol className="run-steps">
          {STEPS.map(([k, title, agent], i) => {
            const st = failed && i === idx ? 'todo' : i < idx ? 'done' : i === idx ? 'active' : 'todo';
            return (
              <li key={k} className={st}>
                <span className="rs-ico">{st === 'done' ? <Check size={14} strokeWidth={2.6} /> : st === 'active' ? <Loader2 size={14} className="spin" /> : failed && i === idx ? <AlertTriangle size={14} /> : <CircleDashed size={14} />}</span>
                <span className="rs-main"><strong>{t(title)}</strong><span className="mono">{t(agent)}</span></span>
              </li>
            );
          })}
        </ol>
        <div className="run-feed card pad">
          <h2>{t('Findings so far')}</h2>
          <p className="muted small">{t('{a} files · {b} sources read · {c} findings', { a: c.counts.files, b: c.counts.sources, c: c.counts.claims })}</p>
          {log.length === 0 && <p className="muted">{t('Starting…')}</p>}
          <ul>{log.map((l, i) => <li key={i}><Check size={16} /><span>{l}</span></li>)}</ul>
        </div>
      </div>

      <ActionBar>
        <div className="ab-text"><strong>{failed ? t('The analysis stopped') : t('Analysing {n} files and the web', { n: c.counts.files })}</strong>
          <span>{failed ? t('Nothing was lost. You can try again.') : t('This usually takes a few minutes.')}</span></div>
        {failed && <button className="btn primary" disabled={!!busy} onClick={onRetry}>{busy ? <Spin /> : <RefreshCw size={15} />} {t('Try again')}</button>}
      </ActionBar>
    </div>
  );
}

// ------------------------------------------------------------------------------------------ sources
export function Sources({ rid }) {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.sources(rid).then(setRows).catch(() => setRows([])); }, [rid]);
  if (!rows) return <p className="muted"><Spin /></p>;
  if (!rows.length) return <Empty icon={<FileText size={22} />} title={t('No sources yet')} />;
  const by = { parsed: [], other: [] }; rows.forEach((r) => by[r.status === 'parsed' ? 'parsed' : 'other'].push(r));
  const Row = ({ s }) => (
    <li className={s.status}>
      {s.kind === 'web' ? <Globe size={16} /> : s.kind === 'user' ? <UserRound size={16} /> : <FileText size={16} />}
      <div className="grow">
        <strong>{s.title || '—'}</strong>{s.ref && <a className="lv-ext" href={s.ref} target="_blank" rel="noreferrer noopener" title={s.ref}><ExternalLink size={12} /></a>}
        <div className="muted small">{[s.kind, s.chunks ? t('{n} passages', { n: s.chunks }) : null, s.relevance != null ? t('relevance {p} %', { p: Math.round(s.relevance * 100) }) : null].filter(Boolean).join(' · ')}</div>
        {s.reason && <div className="muted small">{s.reason}</div>}
        {s.error && <div className="lv-err small">{s.error}</div>}
        {s.info?.warnings?.length > 0 && <ul className="lv-warn">{s.info.warnings.slice(0, 4).map((w, i) => <li key={i}>{w}</li>)}</ul>}
      </div>
      <span className={`pill ${s.status === 'parsed' ? (s.info?.status === 'partial' || s.info?.status === 'poor' ? 'warn' : 'good') : s.duplicate_of ? '' : 'warn'}`}>
        {s.status === 'parsed' ? (s.info?.status === 'partial' ? t('read in part') : s.info?.status === 'poor' ? t('hardly readable') : t('read')) : s.duplicate_of ? t('duplicate') : s.status}</span>
    </li>
  );
  return (
    <div className="lv-sources">
      <ul className="lv-slist">{by.parsed.map((s) => <Row key={s.id} s={s} />)}</ul>
      {by.other.length > 0 && <><h3>{t('Not used')}</h3><ul className="lv-slist dim">{by.other.map((s) => <Row key={s.id} s={s} />)}</ul></>}
    </div>
  );
}

// ------------------------------------------------------------------------------------------ research plan
const KIND_LABEL = { web: 'Web', files: 'Files', sharepoint: 'SharePoint', mail: 'Mail', teams: 'Teams', sap: 'SAP', jira: 'Jira', confluence: 'Confluence' };

/** What the research planner decided for this topic, round by round, and what each round found. */
export function ResearchPlan({ rid, live }) {
  const [plan, setPlan] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = () => api.researchPlan(rid).then((p) => alive && setPlan(p)).catch(() => {});
    load();
    if (!live) return () => { alive = false; };
    const id = setInterval(load, 3000);
    return () => { alive = false; clearInterval(id); };
  }, [rid, live]);
  if (!plan) return <p className="muted"><Spin /></p>;
  if (!plan.rounds.length) return live ? <p className="muted small"><Spin size={13} /> {t('The research planner is looking at your material…')}</p> : <Empty icon={<Search size={22} />} title={t('No research plan yet')} />;
  return (
    <div className="lv-plan-view">
      {plan.web_notes.length > 0 && <div className="lv-banner warn"><AlertTriangle size={20} /><div><strong>{t('The web search did not deliver')}</strong><span>{/language model/i.test(plan.web_notes[plan.web_notes.length - 1] || '') ? t('Web research needs the language model. Configure the Foundry deployment in agents/.env and start the agents again.') : plan.web_notes[plan.web_notes.length - 1]}</span></div></div>}
      {plan.rounds.map((r, i) => (
        <section key={i} className="lv-round">
          <h3>{r.mode === 'initial' ? t('Round {n}: plan for this topic', { n: r.round }) : t('Round {n}: close the gaps', { n: r.round })}</h3>
          {r.strategy && <p className="lv-strategy">{r.strategy}</p>}
          {r.needs?.length > 0 && (
            <ul className="lv-needs-list">{r.needs.slice(0, 10).map((n, j) => (
              <li key={j} className={n.covered ? 'covered' : ''}>{n.covered ? <Check size={13} /> : <Search size={13} />}<span>{n.question}</span>{n.where?.length > 0 && <span className="muted small">{n.where.map((w) => t(KIND_LABEL[w] || w)).join(', ')}</span>}</li>
            ))}</ul>
          )}
          {r.queries?.length > 0 && (
            <div className="lv-queries">{r.queries.map((q) => <span key={q.id} className="lv-q" data-kind={q.kind} title={q.why}>{q.kind === 'web' ? <Globe size={11} /> : <FileText size={11} />}<b>{t(KIND_LABEL[q.kind] || q.kind)}</b> {q.query}</span>)}</div>
          )}
          {r.result && (
            <p className="muted small">{[r.result.evidence_own != null ? t('{n} findings from your material', { n: r.result.evidence_own }) : null, r.result.web_briefings ? t('{n} web briefings', { n: r.result.web_briefings }) : null,
              r.result.web_pages ? t('{n} pages read in full', { n: r.result.web_pages }) : null, r.result.connector_hits ? t('{n} documents from connected systems', { n: r.result.connector_hits }) : null,
              r.result.evidence_new != null ? t('{n} new findings', { n: r.result.evidence_new }) : null, r.result.enough ? t('Nothing more to search for.') : null].filter(Boolean).join(' · ')}</p>
          )}
        </section>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------------------------------ image library
const ROLE_LABEL = { chart: 'Chart', diagram: 'Diagram', photo: 'Photo', screenshot: 'Screenshot', table_image: 'Table', scan: 'Scan', logo: 'Logo', decorative: 'Decoration', other: 'Picture' };

function AssetCard({ a, rid, sections, reload, toast, onTouch }) {
  const [busy, run] = useAction(toast);
  const set = (body) => run('p', async () => { await api.patchAsset(rid, a.id, body); onTouch?.(body.section_key || a.section_key); await reload(); });
  const on = a.chosen;
  const treatment = a.treatment === 'redraw' && a.has_data ? t('redrawn as native chart') : a.treatment === 'discard' ? t('not usable') : '';
  return (
    <li className={`lv-asset${on ? ' on' : ''}${a.user_choice === 'skip' ? ' skip' : ''}`}>
      <div className="lv-asset-pic">
        {a.has_image ? <img src={api.assetUrl(rid, a.id)} alt={a.caption || ''} loading="lazy" />
          : a.chart ? <div className="lv-asset-chart"><BarChart3 size={22} /><table><tbody>{a.chart.labels.slice(0, 5).map((l, i) => <tr key={i}><td>{l}</td><td>{a.chart.series.map((s) => s.values[i]).filter((v) => v != null).map((v) => nf(v)).join(' / ')}</td></tr>)}</tbody></table></div>
            : a.table ? <div className="lv-asset-chart"><table><tbody>{a.table.slice(0, 4).map((r, i) => <tr key={i}>{r.slice(0, 3).map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody></table></div> : <ImageIcon size={24} />}
      </div>
      <div className="lv-asset-body">
        <div className="lv-asset-top"><span className="pill">{t(ROLE_LABEL[a.role] || (a.kind === 'table' ? 'Table' : 'Picture'))}</span>
          {a.origin === 'crop' && <span className="pill info">{t('cut out')}</span>}
          {a.origin === 'web' && <span className="pill warn" title={a.rights || ''}>{t('web · check rights')}</span>}
          {treatment && <span className="pill info">{treatment}</span>}
          {a.used_on?.length > 0 && <span className="pill good">{t('on slide {n}', { n: a.used_on.join(', ') })}</span>}</div>
        <strong className="lv-asset-cap">{a.caption || a.description || '—'}</strong>
        {a.description && a.description !== a.caption && <p className="muted small">{a.description}</p>}
        <div className="muted small">{[a.source, a.locator].filter(Boolean).join(' · ')}</div>
        <div className="lv-asset-act">
          <select className="lv-in" value={a.section_key || ''} onChange={(e) => set({ section_key: e.target.value, user_choice: 'use' })} aria-label={t('Section')}>
            <option value="">{t('No section')}</option>{sections.map((s) => <option key={s.key} value={s.key}>{s.title}</option>)}</select>
          {a.user_choice === 'skip' ? <button className="btn sm" disabled={!!busy} onClick={() => set({ user_choice: null })}>{t('Undo')}</button>
            : <><button className={`btn sm${a.user_choice === 'use' ? ' primary' : ''}`} disabled={!!busy} onClick={() => set({ user_choice: a.user_choice === 'use' ? null : 'use' })}>{a.user_choice === 'use' ? <Check size={13} /> : null} {t('Use')}</button>
              <button className="btn quiet sm" disabled={!!busy} onClick={() => set({ user_choice: 'skip' })}>{t('Skip')}</button></>}
        </div>
      </div>
    </li>
  );
}

export function ImageLibrary({ rid, sections, toast, onApply }) {
  const [rows, setRows] = useState(null);
  const [all, setAll] = useState(false);
  const [touched, setTouched] = useState([]);
  const [busy, run] = useAction(toast);
  const load = useCallback(() => api.assets(rid).then(setRows).catch(() => setRows([])), [rid]);
  useEffect(() => { load(); }, [load]);
  if (!rows) return <p className="muted"><Spin /></p>;
  const shown = rows.filter((a) => all || a.treatment !== 'discard' || a.user_choice === 'use');
  if (!rows.length) return <Empty icon={<ImageIcon size={22} />} title={t('No pictures, charts or tables found')}>{t('Pictures are cut out of PDFs, Word and PowerPoint files, e-mails and web pages; charts are read and redrawn.')}</Empty>;
  const chosen = rows.filter((a) => a.chosen).length;
  const touch = (key) => key && setTouched((x) => (x.includes(key) ? x : [...x, key]));
  const title = (k) => sections.find((s) => s.key === k)?.title || k;
  return (
    <div className="lv-library">
      <div className="lv-lib-head"><p className="muted">{t('{a} of {b} are proposed for slides. Charts with readable numbers are redrawn as editable charts; pictures are placed as they are. You decide: “Use” always shows it, “Skip” never.', { a: chosen, b: rows.filter((x) => x.treatment !== 'discard').length })}</p>
        <label className="lv-check"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> {t('Show rejected too')}</label></div>
      {touched.length > 0 && onApply && (
        <div className="lv-apply"><span>{t('Your choices apply to the slides when a section is written again:')}</span>
          {touched.map((k) => <button key={k} className="btn primary sm" disabled={!!busy} onClick={() => run('apply', async () => { await onApply(k); setTouched((x) => x.filter((y) => y !== k)); })}>{busy === 'apply' ? <Spin size={13} /> : <RefreshCw size={13} />} {title(k)}</button>)}</div>
      )}
      <ul className="lv-assets">{shown.map((a) => <AssetCard key={a.id} a={a} rid={rid} sections={sections} reload={load} toast={toast} onTouch={touch} />)}</ul>
    </div>
  );
}
