// Live stage 2: watch the research, then check what was found (claims, evidence, flags) and what was read (sources and their quality).
import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertOctagon, AlertTriangle, BadgeCheck, Calculator, Check, ChevronRight, ExternalLink, FileText, Globe, Pencil, RefreshCw, ShieldCheck, Sparkles, UserRound, X } from 'lucide-react';
import { t } from '../i18n.js';
import { api } from './client.js';
import { errText, Empty, nf, ProgressBar, Spin, useAction } from './kit.jsx';

const STEPS = [['planning', 'Plan sources'], ['searching', 'Search the web'], ['screening', 'Screen candidates'], ['reading', 'Read documents'], ['extracting', 'Extract evidence'],
  ['assets', 'Pick figures and tables'], ['collected', 'Evidence complete'], ['analysing', 'Analyse sections'], ['red-team', 'Cross-check the whole draft'], ['analysed', 'Done']];

function Running({ c, onRetry, busy }) {
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
        </div>
      </div>
      {blockers > 0 && <div className="lv-banner warn"><AlertOctagon size={20} /><div><strong>{t('{n} blockers are open', { n: blockers })}</strong><span>{t('A blocker is a problem the checker found that would make a statement wrong or unsupported. Resolve each one, with a reason if you accept it.')}</span></div></div>}
      {view === 'sources' ? <div className="card pad"><Sources rid={rid} /></div> : (
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
      <div className="lv-actionbar">
        <span className="muted small">{t('{a} of {b} claims approved', { a: c.counts.approved_claims, b: c.counts.claims })}</span>
        <span className="grow" />
        {editable && <button className="btn" disabled={!!busy} onClick={() => rerun(null)}><RefreshCw size={15} /> {t('Research everything again')}</button>}
        {editable ? <button className="btn primary lg" disabled={!!busy || blockers > 0} onClick={approve} title={blockers ? t('Resolve the open blockers first') : ''}>{busy === 'approve' ? <Spin /> : <BadgeCheck size={17} />} {t('Approve findings and build slides')}</button>
          : <button className="btn lg" onClick={() => go('report')}>{t('To the report')}</button>}
      </div>
    </div>
  );
}

export default function LiveAnalysis({ rid, c, reload, toast, go }) {
  const [busy, run] = useAction(toast);
  const working = ['COLLECTING', 'ANALYSING'].includes(c.state) || (c.job?.kind === 'research' && c.job.status === 'failed' && ['COLLECTING', 'ANALYSING', 'OUTLINE_REVIEW'].includes(c.state));
  if (working) return <Running c={c} busy={busy} onRetry={() => run('retry', async () => { await api.rerun(rid, null); await reload(); })} />;
  if (['SETUP', 'OUTLINE_REVIEW'].includes(c.state)) return <div className="lv-stage"><Empty icon={<Sparkles size={24} />} title={t('Nothing to check yet')}>{t('Approve the outline in the brief step to start the analysis.')}</Empty></div>;
  return <Findings rid={rid} c={c} reload={reload} toast={toast} go={go} />;
}
