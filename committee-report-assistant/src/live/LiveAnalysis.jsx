// Live stage 2: watch the research, then check what was found (claims, evidence, flags) and what was read (sources and their quality).
import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertOctagon, AlertTriangle, BadgeCheck, BarChart3, Calculator, Check, ChevronRight, ExternalLink, FileText, Globe, ImageIcon, Pencil, RefreshCw, Search, ShieldCheck, Sparkles, UserRound, X } from 'lucide-react';
import { t } from '../i18n.js';
import { api } from './client.js';
import { errText, Empty, nf, NextBar, ProgressBar, Spin, useAction } from './kit.jsx';

const STEPS = [['reading', 'Read your material'], ['extracting', 'Extract evidence'], ['planning', 'Plan the research'], ['searching', 'Search the web and sources'], ['screening', 'Screen new sources'],
  ['gaps', 'Close the gaps'], ['assets', 'Look at pictures and charts'], ['collected', 'Evidence complete'], ['analysing', 'Analyse sections'], ['red-team', 'Cross-check the whole draft'], ['analysed', 'Done']];

function Running({ rid, c, onRetry, busy }) {
  const j = c.job; const p = j?.progress || {};
  const idx = Math.max(0, STEPS.findIndex(([k]) => k === p.step));
  const failed = j?.status === 'failed';
  return (
    <div className="lv-stage">
      <div className="stage-head center"><p className="eyebrow">{t('Step 2 · Analysis')}</p>
        <h1 className="display md">{failed ? t('The analysis stopped') : t('Reading, researching, checking…')}</h1>
        <p className="lede">{failed ? j.error : t('You can leave this page open or come back later: the work continues on the server.')}</p></div>
      <div className="card pad lv-run">
        {!failed && <ProgressBar done={p.done || 0} total={p.total || 1} />}
        <ol className="lv-steps">
          {STEPS.map(([k, label], i) => <li key={k} className={failed && i === idx ? 'bad' : i < idx ? 'done' : i === idx ? 'now' : ''}>{i < idx ? <Check size={14} /> : i === idx && !failed ? <Spin size={14} /> : <i />}{t(label)}</li>)}
        </ol>
        <div className="lv-facts"><span><b>{c.counts.files}</b> {t('files')}</span><span><b>{c.counts.sources}</b> {t('sources read')}</span><span><b>{nf(c.counts.evidence)}</b> {t('evidence items')}</span><span><b>{c.counts.claims}</b> {t('claims')}</span></div>
        {(p.log || []).length > 0 && <ul className="lv-log">{p.log.slice(-8).map((l, i) => <li key={i}>{l}</li>)}</ul>}
        {failed && <button className="btn primary" disabled={!!busy} onClick={onRetry}>{busy ? <Spin /> : <RefreshCw size={15} />} {t('Run again')}</button>}
      </div>
      {!failed && <div className="card pad lv-run"><h2>{t('The research plan')}</h2><ResearchPlan rid={rid} live /></div>}
    </div>
  );
}

// ------------------------------------------------------------------------------------------ one claim
const KIND = { fact: 'Fact', number: 'Number', risk: 'Risk', decision: 'Decision', recommendation: 'Recommendation', calculation: 'Calculation', assumption: 'Assumption' };
const STATUS = { verified: ['good', 'Verified'], approved: ['good', 'Approved'], flagged: ['warn', 'Flagged'], draft: ['', 'Draft'], rejected: ['', 'Rejected'] };

function Claim({ cl, flags, rid, reload, toast, editable }) {
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState(null);
  const [busy, run] = useAction(toast);
  const [st, label] = STATUS[cl.status] || ['', cl.status];
  const act = (status) => run(status, async () => { await api.patchClaim(rid, cl.id, { status }); await reload(); });
  const save = () => run('save', async () => { const r = await api.patchClaim(rid, cl.id, { text: edit }); setEdit(null); await reload(); if (r.verdict && r.verdict !== 'supported') toast(t('The edited claim is not fully supported by the evidence: {v}', { v: (r.issues || []).join('; ') || r.verdict }), 'warn'); });
  return (
    <li className={`lv-claim ${cl.status}`}>
      <div className="lv-claim-top">
        <span className={`pill ${st}`}>{t(label)}</span>
        <span className="pill">{t(KIND[cl.kind] || cl.kind)}</span>
        {cl.user_edited && <span className="pill info"><Pencil size={11} /> {t('edited')}</span>}
        {cl.evidence.some((e) => e.origin === 'user') && <span className="pill info"><UserRound size={11} /> {t('your input')}</span>}
        {cl.confidence != null && <span className="muted small lv-conf" title={t('Confidence')}>{Math.round(cl.confidence * 100)} %</span>}
      </div>
      {edit == null ? <p className="lv-claim-text">{cl.text}</p> : (
        <div><textarea className="lv-in" rows={3} value={edit} onChange={(e) => setEdit(e.target.value)} autoFocus />
          <div className="lv-row"><button className="btn primary sm" disabled={!!busy} onClick={save}>{busy === 'save' ? <Spin /> : <Check size={14} />} {t('Save and verify again')}</button><button className="btn quiet sm" onClick={() => setEdit(null)}>{t('Cancel')}</button></div></div>
      )}
      {(cl.issues || []).length > 0 && <ul className="lv-issues">{cl.issues.map((x, i) => <li key={i}><AlertTriangle size={13} /> {x}</li>)}</ul>}
      {flags.map((fl) => <Flag key={fl.id} fl={fl} rid={rid} reload={reload} toast={toast} editable={editable} />)}
      <div className="lv-claim-actions">
        <button className="link-btn small" onClick={() => setOpen(!open)}><ChevronRight size={13} className={open ? 'rot' : ''} /> {t('{n} evidence', { n: cl.evidence.length + cl.calculations.length })}</button>
        {editable && cl.status !== 'rejected' && edit == null && (
          <span className="lv-acts">
            <button className="btn quiet sm" onClick={() => setEdit(cl.text)}><Pencil size={13} /> {t('Edit')}</button>
            <button className="btn quiet sm" disabled={!!busy} onClick={() => act('rejected')}><X size={13} /> {t('Reject')}</button>
            {cl.status !== 'approved' && <button className="btn good sm" disabled={!!busy || cl.status === 'flagged'} title={cl.status === 'flagged' ? t('Resolve the flag first') : ''} onClick={() => act('approved')}><Check size={13} /> {t('Approve')}</button>}
          </span>
        )}
        {cl.status === 'rejected' && editable && <button className="btn quiet sm" onClick={() => act('verified')}>{t('Restore')}</button>}
      </div>
      {open && (
        <ul className="lv-evs">
          {cl.evidence.map((e) => (
            <li key={e.id}>
              <span className="lv-ev-src">{e.origin === 'user' ? <UserRound size={13} /> : e.origin === 'web' ? <Globe size={13} /> : <FileText size={13} />} {e.source || '—'}{e.locator ? ` · ${e.locator}` : ''}</span>
              <blockquote>{e.quote || e.statement}</blockquote>
              {e.value != null && <span className="pill">{e.value}{e.unit ? ` ${e.unit}` : ''}</span>}
            </li>
          ))}
          {cl.calculations.map((k) => <li key={k.id} className="calc"><span className="lv-ev-src"><Calculator size={13} /> {k.label}</span><code>{k.formula} = {k.value}{k.unit ? ` ${k.unit}` : ''}</code></li>)}
        </ul>
      )}
    </li>
  );
}

function Flag({ fl, rid, reload, toast, editable }) {
  const [note, setNote] = useState('');
  const [busy, run] = useAction(toast);
  const blocker = fl.severity === 'blocker';
  const done = fl.status === 'resolved';
  const resolve = (resolution) => run(resolution, async () => { await api.resolveFlag(rid, fl.id, resolution, note.trim() || null); await reload(); });
  return (
    <div className={`lv-flag ${blocker ? 'blocker' : ''} ${done ? 'done' : ''}`}>
      <div className="lv-flag-h">{blocker ? <AlertOctagon size={16} /> : <AlertTriangle size={16} />}<strong>{blocker ? t('Blocker') : t('Note')}</strong><span className="muted small">{fl.origin} · {fl.kind}</span>
        {done && <span className="pill good"><Check size={11} /> {fl.resolution}</span>}</div>
      <p>{fl.text}</p>
      {done && fl.note && <p className="muted small">{t('Reason')}: {fl.note}</p>}
      {!done && editable && (
        <div className="lv-flag-act">
          <input className="lv-in" value={note} placeholder={blocker ? t('Short reason (required for a blocker)') : t('Optional note')} onChange={(e) => setNote(e.target.value)} />
          <button className="btn sm" disabled={!!busy || (blocker && !note.trim())} onClick={() => resolve('accepted')}>{t('Accept')}</button>
          <button className="btn quiet sm" disabled={!!busy || (blocker && !note.trim())} onClick={() => resolve('dismissed')}>{t('Dismiss')}</button>
          {fl.claim_id && <button className="btn quiet sm" disabled={!!busy} onClick={() => resolve('rejected')}>{t('Reject the claim')}</button>}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------ sources
function Sources({ rid }) {
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

function AssetCard({ a, rid, sections, reload, toast }) {
  const [busy, run] = useAction(toast);
  const set = (body) => run('p', async () => { await api.patchAsset(rid, a.id, body); await reload(); });
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

function ImageLibrary({ rid, sections, toast }) {
  const [rows, setRows] = useState(null);
  const [all, setAll] = useState(false);
  const load = useCallback(() => api.assets(rid).then(setRows).catch(() => setRows([])), [rid]);
  useEffect(() => { load(); }, [load]);
  if (!rows) return <p className="muted"><Spin /></p>;
  const shown = rows.filter((a) => all || a.treatment !== 'discard' || a.user_choice === 'use');
  if (!rows.length) return <Empty icon={<ImageIcon size={22} />} title={t('No pictures, charts or tables found')}>{t('Pictures are cut out of PDFs, Word and PowerPoint files, e-mails and web pages; charts are read and redrawn.')}</Empty>;
  const chosen = rows.filter((a) => a.chosen).length;
  return (
    <div className="lv-library">
      <div className="lv-lib-head"><p className="muted">{t('{a} of {b} are proposed for slides. Charts with readable numbers are redrawn as editable charts; pictures are placed as they are. You decide: “Use” always shows it, “Skip” never.', { a: chosen, b: rows.filter((x) => x.treatment !== 'discard').length })}</p>
        <label className="lv-check"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> {t('Show rejected too')}</label></div>
      <ul className="lv-assets">{shown.map((a) => <AssetCard key={a.id} a={a} rid={rid} sections={sections} reload={load} toast={toast} />)}</ul>
    </div>
  );
}

// ------------------------------------------------------------------------------------------ the review
function Findings({ rid, c, reload, toast, go }) {
  const [data, setData] = useState(null);
  const [sel, setSel] = useState(null);
  const [view, setView] = useState('findings');
  const [busy, run] = useAction(toast);
  const load = useCallback(async () => { try { setData(await api.findings(rid)); } catch (e) { toast(errText(e), 'warn'); } }, [rid, toast]);
  useEffect(() => { load(); }, [load]);
  const refresh = useCallback(async () => { await Promise.all([load(), reload()]); }, [load, reload]);
  const editable = c.state === 'FINDINGS_REVIEW';
  const secs = data?.sections || [];
  const cur = secs.find((s) => s.key === sel) || secs[0];
  const counts = useMemo(() => Object.fromEntries(secs.map((s) => [s.key, { n: s.claims.filter((x) => x.status !== 'rejected').length, open: s.flags.filter((f) => f.status === 'open').length }])), [secs]);
  if (!data) return <div className="lv-stage"><p className="muted"><Spin /> {t('Loading…')}</p></div>;
  const blockers = data.open_blockers;
  const rerun = (keys) => run('rerun', async () => { await api.rerun(rid, keys); await reload(); });
  const approve = () => run('approve', async () => { await api.approveFindings(rid); await reload(); go('report'); });
  const flagsOf = (cid) => (cur?.flags || []).filter((f) => f.claim_id === cid);
  return (
    <div className="lv-stage wide">
      <div className="stage-head compact">
        <div><p className="eyebrow">{t('Step 2 · Analysis')}</p><h1 className="display md">{t('Check what I found')}</h1></div>
        <div className="lv-seg" role="tablist">
          <button role="tab" aria-selected={view === 'findings'} className={view === 'findings' ? 'on' : ''} onClick={() => setView('findings')}>{t('Findings')}</button>
          <button role="tab" aria-selected={view === 'sources'} className={view === 'sources' ? 'on' : ''} onClick={() => setView('sources')}>{t('Sources')} <b>{c.counts.sources}</b></button>
          <button role="tab" aria-selected={view === 'images'} className={view === 'images' ? 'on' : ''} onClick={() => setView('images')}>{t('Pictures and charts')}</button>
          <button role="tab" aria-selected={view === 'plan'} className={view === 'plan' ? 'on' : ''} onClick={() => setView('plan')}>{t('Research plan')}</button>
        </div>
      </div>
      {blockers > 0 && <div className="lv-banner warn"><AlertOctagon size={20} /><div><strong>{t('{n} blockers are open', { n: blockers })}</strong><span>{t('A blocker is a problem the checker found that would make a statement wrong or unsupported. Resolve each one, with a reason if you accept it.')}</span></div></div>}
      {view === 'sources' ? <div className="card pad"><Sources rid={rid} /></div> : view === 'images' ? <div className="card pad"><ImageLibrary rid={rid} sections={secs} toast={toast} /></div> : view === 'plan' ? <div className="card pad"><ResearchPlan rid={rid} /></div> : (
        <div className="lv-review">
          <nav className="lv-secnav card" aria-label={t('Sections')}>
            {(data.general_flags || []).length > 0 && <button className={sel === '_general' ? 'on' : ''} onClick={() => setSel('_general')}><AlertTriangle size={15} /> {t('General notes')} <b>{data.general_flags.filter((f) => f.status === 'open').length}</b></button>}
            {secs.map((s) => (
              <button key={s.key} className={(cur && sel !== '_general' && cur.key === s.key) ? 'on' : ''} onClick={() => setSel(s.key)}>
                <span className="grow">{s.title}</span><span className="muted small">{counts[s.key].n}</span>{counts[s.key].open > 0 && <i className="lv-dot warn" title={t('open flags')} />}
              </button>
            ))}
          </nav>
          <div className="lv-secbody">
            {sel === '_general' ? (
              <div className="card pad"><h2>{t('General notes')}</h2>{data.general_flags.map((fl) => <Flag key={fl.id} fl={fl} rid={rid} reload={refresh} toast={toast} editable={editable} />)}</div>
            ) : cur ? (
              <div className="card pad">
                <div className="sec-head"><h2>{cur.title}</h2>
                  {cur.verified === true && <span className="pill good"><ShieldCheck size={12} /> {t('checked')}</span>}
                  {editable && <button className="btn quiet sm" disabled={!!busy} onClick={() => rerun([cur.key])}>{busy === 'rerun' ? <Spin /> : <RefreshCw size={14} />} {t('Research again')}</button>}</div>
                {cur.headline && <p className="lv-headline">{cur.headline}</p>}
                {cur.claims.length === 0 ? <Empty icon={<Sparkles size={22} />} title={t('No claim in this section')}>{t('There was not enough evidence. Add files or tell the interviewer what you know, then research again.')}</Empty> : (
                  <ul className="lv-claims">{cur.claims.map((cl) => <Claim key={cl.id} cl={cl} flags={flagsOf(cl.id)} rid={rid} reload={refresh} toast={toast} editable={editable} />)}</ul>
                )}
                {cur.flags.filter((f) => !f.claim_id).map((fl) => <Flag key={fl.id} fl={fl} rid={rid} reload={refresh} toast={toast} editable={editable} />)}
                {(cur.open_points || []).length > 0 && <div className="lv-open"><h3>{t('Still open in this section')}</h3><ul>{cur.open_points.map((p, i) => <li key={i}>{p}</li>)}</ul></div>}
              </div>
            ) : null}
          </div>
        </div>
      )}
      <NextBar status={blockers > 0 ? t('{n} blockers are open', { n: blockers }) : t('{a} of {b} claims approved', { a: c.counts.approved_claims, b: c.counts.claims })}>
        {editable && <button className="btn quiet" disabled={!!busy} onClick={() => rerun(null)}><RefreshCw size={15} /> {t('Research everything again')}</button>}
        {editable ? <button className="btn primary lg" disabled={!!busy || blockers > 0} onClick={approve} title={blockers ? t('Resolve the open blockers first') : ''}>{busy === 'approve' ? <Spin /> : <BadgeCheck size={17} />} {t('Approve findings and build slides')}</button>
          : <button className="btn lg" onClick={() => go('report')}>{t('To the report')}</button>}
      </NextBar>
    </div>
  );
}

export default function LiveAnalysis({ rid, c, reload, toast, go }) {
  const [busy, run] = useAction(toast);
  const working = ['COLLECTING', 'ANALYSING'].includes(c.state) || (c.job?.kind === 'research' && c.job.status === 'failed' && ['COLLECTING', 'ANALYSING', 'OUTLINE_REVIEW'].includes(c.state));
  if (working) return <Running rid={rid} c={c} busy={busy} onRetry={() => run('retry', async () => { await api.rerun(rid, null); await reload(); })} />;
  if (['SETUP', 'OUTLINE_REVIEW'].includes(c.state)) return <div className="lv-stage"><Empty icon={<Sparkles size={24} />} title={t('Nothing to check yet')}>{t('Approve the outline in the brief step to start the analysis.')}</Empty></div>;
  return <Findings rid={rid} c={c} reload={reload} toast={toast} go={go} />;
}
