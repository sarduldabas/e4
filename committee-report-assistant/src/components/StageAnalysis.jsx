import { t } from '../i18n.js';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Check, Pencil, RefreshCw, MessageSquare, EyeOff, AlertTriangle, ArrowRight, ArrowLeft, Send, Loader2, Bell,
  ShieldCheck, Undo2, CircleDashed, Plus, Trash2, Eye, ChevronRight,
} from 'lucide-react';
import {
  RUN_STEPS, SOURCES, SRC, COMMITTEE_QA, CHAT_SUGGESTIONS, replyTo, qcText,
} from '../data.js';
import { includedSections, openItems } from '../workspace.js';
import { VISUALS, OptionsTable } from './Charts.jsx';
import { ActionBar, Avatar, RichText, SourceIcon, useInterval } from './ui.jsx';

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
        <p className="eyebrow">{t("Step 2 of 3 · Analysis")}</p>
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
        <button className={`btn${ws.analysis.notify ? ' on' : ''}`} onClick={() => { setAnalysis((a) => ({ ...a, notify: !a.notify })); toast(ws.analysis.notify ? t('Notification off') : t('I will notify you in Teams when the analysis is ready')); }}><Bell size={16} /> {ws.analysis.notify ? t('Notifying you') : t('Notify me when ready')}</button>
        <button className="btn quiet" onClick={done}>{t("Skip ahead (demo)")}</button>
      </ActionBar>
    </div>
  );
}

/* ============================== Section card ================================ */
function SectionCard({ s, idx, a, qc, active, onCite, activeCite, actions }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(null);
  const [redo, setRedo] = useState(false);
  const [instr, setInstr] = useState('');
  const [reply, setReply] = useState('');
  const reviewed = !!a.reviewed[s.id];
  const busy = !!a.revising[s.id];
  const comments = a.comments[s.id] || [];
  const stale = a.stale.includes(s.id);

  const startEdit = () => { setDraft({ headline: t(s.headline).replace(/%QC%/g, qc), bullets: s.bullets.map((b) => toEditable(b, qc)) }); setEditing(true); };
  const save = () => {
    const bullets = draft.bullets.map((d, i) => {
      const orig = s.bullets[i];
      return orig !== undefined && toEditable(orig, qc) === d ? orig : fromEditable(d);
    }).filter((b) => b.trim());
    const headline = t(s.headline).replace(/%QC%/g, qc) === draft.headline ? s.headline : draft.headline;
    actions.edit(s.id, { headline, bullets });
    setEditing(false);
  };
  const runRedo = (text) => { if (!text.trim()) return; actions.redo(s.id, text.trim()); setRedo(false); setInstr(''); };

  return (
    <article id={`sec-${s.id}`} data-sec={s.id} className={`sec card${active ? ' active' : ''}${reviewed ? ' reviewed' : ''}${busy ? ' busy' : ''}`}>
      <header className="sec-head">
        <span className="sec-num">{String(idx + 1).padStart(2, '0')}</span>
        <span className="sec-title">{t(s.title)}</span>
        <span className={`conf ${s.confidence}`}><ShieldCheck size={13} /> {t(CONF[s.confidence])} · {t('{n} sources', { n: s.sources.length })}</span>
        {reviewed && <span className="pill good"><Check size={12} strokeWidth={2.6} /> {t("Reviewed")}</span>}
        {stale && <span className="pill warn">{t("Needs update")}</span>}
      </header>

      {busy && <div className="sec-busy"><Loader2 size={16} className="spin" /> {t("Updating this section…")}</div>}

      {editing ? (
        <div className="edit">
          <label className="sr-only" htmlFor={`h-${s.id}`}>{t("Headline")}</label>
          <textarea id={`h-${s.id}`} className="edit-h" value={draft.headline} onChange={(e) => setDraft({ ...draft, headline: e.target.value })} rows={2} />
          {draft.bullets.map((b, i) => (
            <div key={i} className="edit-row">
              <textarea aria-label={t('Point {n}', { n: i + 1 })} value={b} rows={2} onChange={(e) => setDraft({ ...draft, bullets: draft.bullets.map((x, k) => (k === i ? e.target.value : x)) })} />
              <button className="iconbtn sm" onClick={() => setDraft({ ...draft, bullets: draft.bullets.filter((_, k) => k !== i) })} aria-label={t("Remove point")}><Trash2 size={15} /></button>
            </div>
          ))}
          <p className="muted small">{t("Numbers in brackets are source references. Keep them to keep the evidence link.")}</p>
          <div className="row gap">
            <button className="btn sm" onClick={() => setDraft({ ...draft, bullets: [...draft.bullets, ''] })}><Plus size={14} /> {t("Add point")}</button>
            <span className="grow" />
            <button className="btn quiet sm" onClick={() => setEditing(false)}>{t("Cancel")}</button>
            <button className="btn primary sm" onClick={save}>{t("Save changes")}</button>
          </div>
        </div>
      ) : (
        <>
          <h2 className="headline"><RichText text={s.headline} qc={qc} /></h2>
          <ul className="points">
            {s.bullets.map((b, i) => <li key={i}><RichText text={b} qc={qc} onCite={onCite} active={activeCite} /></li>)}
          </ul>
          {s.decision && <div className="decision"><strong>{t("Decision requested")}</strong><span>{t(s.decision).replace(/^[^:]+:\s*/, '').replace(/%QC%/g, qc)}</span></div>}
          {a.revisions[s.id] && <p className="revnote"><RefreshCw size={13} /> {t('Revised: “{text}”', { text: a.revisions[s.id] })} <button className="textlink" onClick={() => actions.undoRedo(s.id)}><Undo2 size={12} /> {t("Undo")}</button></p>}
        </>
      )}

      {s.id === 's3' && (
        a.gap === null ? (
          <div className="flag warn">
            <AlertTriangle size={18} />
            <div>
              <strong>{t("Gap: capacity beyond 2029 is not stated in any source")}</strong>
              <p>{t("A 40% share needs 12.8 GWh. Without a commitment, risk R3 stays open.")}</p>
              <div className="row gap wrap">
                <button className="btn sm" onClick={() => actions.setGap('requested')}>{t("Ask Procurement")}</button>
                <button className="btn sm" onClick={() => actions.setGap('assumption')}>{t("Treat as assumption")}</button>
                <button className="btn quiet sm" onClick={() => actions.setGap('open')}>{t("Leave open")}</button>
              </div>
            </div>
          </div>
        ) : (
          <div className="flag ok"><Check size={16} /> {t(a.gap === 'requested' ? 'Request to Procurement prepared. Shown as an open item for the committee.' : a.gap === 'assumption' ? 'Marked as assumption: capacity stays at 18 GWh after 2029.' : 'Left open and listed in the committee questions.')} <button className="textlink" onClick={() => actions.setGap(null)}>{t("Change")}</button></div>
        )
      )}

      {(s.visuals || []).map((v) => {
        if (v === 'table') return <div key={v} className="viz"><span className="viz-tag">{t("Generated")}</span><OptionsTable qc={qc} /></div>;
        const C = VISUALS[v];
        return (
          <div key={v} className="viz">
            <span className={`viz-tag${v === 'capacity' ? ' ext' : ''}`}>{v === 'capacity' ? t('Extracted from Supplier_B_Proposal.pdf, p. 12') : t('Generated')}</span>
            <C assumed={a.gap === 'assumption'} />
          </div>
        );
      })}

      {s.id === 's4' && (
        a.qualCost === null ? (
          <div className="flag warn">
            <AlertTriangle size={18} />
            <div>
              <strong>{t("Conflict: one-time qualification cost")}</strong>
              <p>{t("Two sources give different figures. Choose which one the report uses.")}</p>
              <div className="choices">
                <button className="choice" onClick={() => actions.setQc('14.2')}><b>{qcText('14.2')}</b><span>{t("Email, J. Meier, 14.10.2026")} <button type="button" className="cite" onClick={(e) => { e.stopPropagation(); onCite(4); }}>{t("4")}</button></span></button>
                <button className="choice" onClick={() => actions.setQc('15.1')}><b>{qcText('15.1')}</b><span>{t("Cost_model_Q3.xlsx, sheet Options")} <button type="button" className="cite" onClick={(e) => { e.stopPropagation(); onCite(3); }}>{t("3")}</button></span></button>
                <button className="choice ghost" onClick={() => actions.setQc('range')}><b>{t("Show range")}</b><span>{t("Report both and name the sources")}</span></button>
              </div>
            </div>
          </div>
        ) : (
          <div className="flag ok"><Check size={16} /> {t('Qualification cost: {qc} {note}.', { qc: qcText(a.qualCost), note: t(a.qualCost === 'range' ? '(range shown)' : 'used in the report') })} <button className="textlink" onClick={() => actions.setQc(null)}>{t("Change")}</button></div>
        )
      )}

      {comments.length > 0 && (
        <div className="thread">
          {comments.map((c, i) => (
            <div key={i} className={`cmt${c.resolved ? ' resolved' : ''}`}>
              <Avatar id={c.who} size={26} ring={false} />
              <div>
                <p><strong>{c.who === 'jm' ? 'Jonas Meier' : 'Katrin Weber'}</strong> <span className="muted small">{t(c.when)}</span></p>
                <p>{t(c.text)}</p>
              </div>
            </div>
          ))}
          {!comments.every((c) => c.resolved) && (
            <div className="row gap reply">
              <input value={reply} onChange={(e) => setReply(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && reply.trim()) { actions.comment(s.id, reply.trim()); setReply(''); } }} placeholder={t("Reply…")} aria-label={t("Reply to comment")} />
              <button className="btn sm" onClick={() => actions.resolve(s.id)}><Check size={14} /> {t("Resolve")}</button>
            </div>
          )}
        </div>
      )}

      {redo && (
        <div className="redo">
          <label htmlFor={`r-${s.id}`}>{t("What should change in this section?")}</label>
          <div className="row gap">
            <input id={`r-${s.id}`} autoFocus value={instr} onChange={(e) => setInstr(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && runRedo(instr)} placeholder={t("For example: shorter, more detail on cost, add a counter-argument")} />
            <button className="btn primary sm" onClick={() => runRedo(instr)}>{t("Redo")}</button>
          </div>
          <div className="chips">{['Make it shorter', 'More detail on cost', 'Add a counter-argument'].map((c) => <button key={c} className="opt" onClick={() => runRedo(t(c))}>{t(c)}</button>)}</div>
        </div>
      )}

      <footer className="sec-actions">
        <button className={`btn sm${reviewed ? ' good' : ''}`} onClick={() => actions.approve(s.id)}><Check size={15} /> {reviewed ? t('Reviewed') : t('Mark as reviewed')}</button>
        <button className="btn quiet sm" onClick={startEdit} disabled={editing}><Pencil size={14} /> {t("Edit")}</button>
        <button className="btn quiet sm" onClick={() => setRedo((v) => !v)}><RefreshCw size={14} /> {t("Redo with instruction")}</button>
        <button className="btn quiet sm" onClick={() => actions.focusAsk(t(s.title))}><MessageSquare size={14} /> {t("Ask about this")}</button>
        <span className="grow" />
        <button className="btn quiet sm" onClick={() => actions.exclude(s.id)}><EyeOff size={14} /> {t("Leave out")}</button>
      </footer>
    </article>
  );
}

/* ================================== Dock ==================================== */
function Dock({ tab, setTab, evidence, setEvidence, a, setAnalysis, askRef, qc }) {
  const [msg, setMsg] = useState('');
  const [thinking, setThinking] = useState(false);
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'nearest' }); }, [a.chat.length, thinking]);

  const send = (text) => {
    const q = (text ?? msg).trim();
    if (!q) return;
    setMsg(''); setThinking(true);
    setAnalysis((x) => ({ ...x, chat: [...x.chat, { role: 'user', text: q }] }));
    setTimeout(() => {
      const r = replyTo(q);
      setAnalysis((x) => ({ ...x, chat: [...x.chat, { role: 'ai', ...r }] }));
      setThinking(false);
    }, 900);
  };
  const src = evidence ? SRC[evidence] : null;
  const usedIn = src ? a.sections.filter((s) => s.sources.includes(src.id)).map((s) => s.id) : [];

  return (
    <aside className="dock card">
      <div className="tabs" role="tablist">
        {[['ask', 'Ask'], ['evidence', 'Evidence'], ['qa', 'Committee Q&A']].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{t(l)}</button>
        ))}
      </div>

      {tab === 'ask' && (
        <div className="dock-body chat">
          <div className="msgs">
            {a.chat.length === 0 && (
              <div className="empty">
                <p>{t('Ask anything about this analysis. Answers come from your {n} sources and show where they are from.', { n: SOURCES.length })}</p>
                <div className="chips col">{CHAT_SUGGESTIONS.map((s) => <button key={s} className="opt" onClick={() => send(t(s))}>{t(s)}</button>)}</div>
              </div>
            )}
            {a.chat.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <p>{m.role === 'ai' ? t(m.text) : m.text}</p>
                {m.cites?.length > 0 && <p className="cites">{m.cites.map((n) => <button key={n} className="cite" onClick={() => { setEvidence(n); setTab('evidence'); }}>{n}</button>)}</p>}
              </div>
            ))}
            {thinking && <div className="msg ai"><p className="typing"><i /><i /><i /></p></div>}
            <div ref={endRef} />
          </div>
          <form className="chat-in" onSubmit={(e) => { e.preventDefault(); send(); }}>
            <input ref={askRef} value={msg} onChange={(e) => setMsg(e.target.value)} placeholder={t("Ask or tell me what to change")} aria-label={t("Ask about the analysis")} />
            <button className="round solid sm" aria-label={t("Send")}><Send size={15} /></button>
          </form>
        </div>
      )}

      {tab === 'evidence' && (
        <div className="dock-body">
          {src ? (
            <div className="ev">
              <button className="textlink" onClick={() => setEvidence(null)}><ArrowLeft size={13} /> {t("All sources")}</button>
              <div className="ev-head"><span className="f-ico"><SourceIcon kind={src.kind} /></span><div><strong>{t(src.name)}</strong><span className="muted small">{t(src.origin)} · {t(src.loc)}</span></div></div>
              <blockquote>{t(src.excerpt)}</blockquote>
              <p className="muted small">{t('Used in:')} {usedIn.map((id) => a.sections.find((s) => s.id === id)).map((s, i) => <span key={s.id}>{i ? ', ' : ''}{t('section {n}', { n: s.id.replace('s', '') })}</span>)}</p>
              <button className="btn sm" disabled>{t("Open original")}</button>
            </div>
          ) : (
            <ul className="src-list">
              {SOURCES.map((s) => (
                <li key={s.id}><button onClick={() => setEvidence(s.id)}>
                  <span className="f-ico"><SourceIcon kind={s.kind} /></span>
                  <span className="f-main"><strong>{t(s.name)}</strong><span className="muted small">{t(s.origin)} · {t(s.detail)}</span></span>
                  <span className="cite static">{s.id}</span>
                </button></li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === 'qa' && (
        <div className="dock-body">
          <p className="muted small tight">{t("What the committee is likely to ask, with a draft answer from your sources.")}</p>
          <ul className="qa">
            {COMMITTEE_QA.map((x) => (
              <li key={x.q}>
                <strong>{t(x.q)}</strong>
                <p>{t(x.a).replace(/%QC%/g, qc)}</p>
                <p className="cites">{x.cites.map((n) => <button key={n} className="cite" onClick={() => { setEvidence(n); setTab('evidence'); }}>{n}</button>)}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}

/* ================================ Results =================================== */
function Results({ ws, setAnalysis, setIncluded, markDeckStale, onBack, onNext, toast, focus }) {
  const a = ws.analysis;
  const qc = qcText(a.qualCost);
  const secs = includedSections(ws);
  const left = ws.brief.outline.filter((o) => !o.included);
  const [tab, setTab] = useState('ask');
  const [evidence, setEvidence] = useState(null);
  const [activeSec, setActiveSec] = useState(secs[0]?.id);
  const askRef = useRef(null);
  const reviewed = secs.filter((s) => a.reviewed[s.id]).length;
  const items = openItems(a);

  useEffect(() => {
    if (focus) setTimeout(() => document.getElementById(`sec-${focus}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120);
  }, []); // eslint-disable-line

  useEffect(() => {
    const els = [...document.querySelectorAll('[data-sec]')];
    const io = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && setActiveSec(e.target.dataset.sec)), { rootMargin: '-25% 0px -65% 0px' });
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, [secs.length]);

  const revise = (id, text, markStale = true) => {
    setAnalysis((x) => ({ ...x, revising: { ...x.revising, [id]: true } }));
    setTimeout(() => {
      setAnalysis((x) => {
        const r = { ...x.revising }; delete r[id];
        return { ...x, revising: r, revisions: text ? { ...x.revisions, [id]: text } : x.revisions, stale: x.stale.filter((y) => y !== id) };
      });
      if (markStale) markDeckStale([id]);
    }, 1500);
  };

  const actions = {
    approve: (id) => setAnalysis((x) => ({ ...x, reviewed: { ...x.reviewed, [id]: !x.reviewed[id] } })),
    edit: (id, patch) => { setAnalysis((x) => ({ ...x, sections: x.sections.map((s) => (s.id === id ? { ...s, ...patch } : s)), edited: { ...x.edited, [id]: true } })); markDeckStale([id]); toast(t('Changes saved. Slides can be updated.')); },
    redo: (id, text) => revise(id, text),
    undoRedo: (id) => setAnalysis((x) => { const r = { ...x.revisions }; delete r[id]; return { ...x, revisions: r }; }),
    exclude: (id) => { setIncluded(id, false); toast(t('Section left out of the report. Restore it from the list on the left.')); },
    setQc: (v) => { setAnalysis((x) => ({ ...x, qualCost: v })); markDeckStale(['s1', 's4', 's7']); if (v) toast(v === 'range' ? t('Both figures will be shown') : t('Using {qc} everywhere, including summary and recommendation', { qc: qcText(v) })); },
    setGap: (v) => { setAnalysis((x) => ({ ...x, gap: v })); markDeckStale(['s3']); },
    comment: (id, text) => setAnalysis((x) => ({ ...x, comments: { ...x.comments, [id]: [...(x.comments[id] || []), { who: 'kw', text, when: 'Just now', resolved: false }] } })),
    resolve: (id) => { setAnalysis((x) => ({ ...x, comments: { ...x.comments, [id]: (x.comments[id] || []).map((c) => ({ ...c, resolved: true })) } })); toast(t('Comment resolved')); },
    focusAsk: (title) => { setTab('ask'); setTimeout(() => { askRef.current?.focus(); }, 50); toast(t('Ask about “{title}” in the panel on the right', { title })); },
  };
  const onCite = (n) => { setEvidence(n); setTab('evidence'); };
  const updateStale = () => {
    const ids = [...a.stale];
    ids.forEach((id) => revise(id, null, true));
    toast(t(ids.length > 1 ? 'Updating {n} sections' : 'Updating {n} section', { n: ids.length }));
  };
  const statusOf = (s) => (a.reviewed[s.id] ? 'done' : (s.id === 's4' && a.qualCost === null) || (s.id === 's3' && a.gap === null) ? 'flag' : a.stale.includes(s.id) ? 'stale' : 'todo');

  return (
    <div className="stage stage-analysis">
      <header className="stage-head">
        <p className="eyebrow">{t("Step 2 of 3 · Analysis")}</p>
        <h1 className="display lg">{t("Here is what I found.")} <em>{t("You decide what stays.")}</em></h1>
        <div className="expect">
          <div><span className="expect-k">{t("From you")}</span><span>{items.length === 1 ? t('Skim each section, resolve the 1 flagged item, change what you disagree with.') : items.length ? t('Skim each section, resolve the {n} flagged items, change what you disagree with.', { n: items.length }) : t('Skim each section, resolve the open flagged items, change what you disagree with.')}</span></div>
          <div><span className="expect-k">{t("Then")}</span><span>{t("I turn it into slides in your template. You can come back here at any time.")}</span></div>
        </div>
      </header>

      <div className="work-strip">
        <div><b>{SOURCES.length}</b><span>{t("sources read")}</span></div>
        <div><b>{t("8")}</b><span>{t("specialists")}</span></div>
        <div><b>{t("5")}</b><span>{t("charts built")}</span></div>
        <div><b>{t("24")}</b><span>{t("figures cross-checked")}</span></div>
        <div className={items.length ? 'warn' : ''}><b>{items.length}</b><span>{t(items.length === 1 ? 'open item' : 'open items')}</span></div>
      </div>

      {a.stale.length > 0 && (
        <div className="banner">
          <RefreshCw size={18} />
          <div><strong>{t("Your brief changed after this analysis was made")}</strong><span>{t(a.stale.length > 1 ? '{n} sections may be affected: {list}. Everything else stays as it is.' : '{n} section may be affected: {list}. Everything else stays as it is.', { n: a.stale.length, list: a.stale.map((id) => secs.find((s) => s.id === id)?.title).filter(Boolean).map((x) => t(x)).join(', ') })}</span></div>
          <button className="btn primary sm" onClick={updateStale}>{t(a.stale.length > 1 ? 'Update {n} sections' : 'Update {n} section', { n: a.stale.length })}</button>
          <button className="btn quiet sm" onClick={() => setAnalysis({ stale: [] })}>{t("Keep as is")}</button>
        </div>
      )}

      <div className="an-grid">
        <nav className="an-nav" aria-label={t("Sections")}>
          <p className="eyebrow tight">{t("Sections")}</p>
          <ol>
            {secs.map((s, i) => {
              const st = statusOf(s);
              return (
                <li key={s.id}>
                  <button className={`${activeSec === s.id ? 'on' : ''} ${st}`} onClick={() => document.getElementById(`sec-${s.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
                    <span className="nav-ico">{st === 'done' ? <Check size={12} strokeWidth={3} /> : st === 'flag' ? <AlertTriangle size={12} /> : st === 'stale' ? <RefreshCw size={11} /> : String(i + 1)}</span>
                    <span>{t(s.title)}</span>
                  </button>
                </li>
              );
            })}
          </ol>
          {left.length > 0 && (
            <>
              <p className="eyebrow tight mt">{t("Left out")}</p>
              <ul className="leftout">{left.map((o) => <li key={o.id}><span>{t(o.title)}</span><button className="textlink" onClick={() => setIncluded(o.id, true)}><Eye size={12} /> {t("Restore")}</button></li>)}</ul>
            </>
          )}
          {items.length > 0 && (
            <div className="open-items">
              <p className="eyebrow tight">{t("Open items")}</p>
              {items.map((it) => <button key={it.id} onClick={() => document.getElementById(`sec-${it.section}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}><AlertTriangle size={13} /> {t(it.label)} <ChevronRight size={13} /></button>)}
            </div>
          )}
        </nav>

        <main className="an-doc">
          {secs.map((s, i) => (
            <SectionCard key={s.id} s={s} idx={i} a={a} qc={qc} active={activeSec === s.id} onCite={onCite} activeCite={evidence} actions={actions} />
          ))}
        </main>

        <Dock tab={tab} setTab={setTab} evidence={evidence} setEvidence={setEvidence} a={a} setAnalysis={setAnalysis} askRef={askRef} qc={qc} />
      </div>

      <ActionBar>
        <div className="ab-text">
          <strong>{t('{a} of {b} sections reviewed', { a: reviewed, b: secs.length })}{items.length ? ` · ${t('{n} open', { n: items.length })}` : ''}</strong>
          <span>{t("You can continue now. Open items stay flagged in the report checks.")}</span>
        </div>
        <button className="btn quiet" onClick={onBack}><ArrowLeft size={16} /> {t("Brief")}</button>
        <button className="btn primary lg" onClick={onNext}>{t("Create report")} <ArrowRight size={18} /></button>
      </ActionBar>
    </div>
  );
}

export default function StageAnalysis(props) {
  return props.ws.analysis.status === 'running' ? <RunView {...props} /> : <Results {...props} />;
}
