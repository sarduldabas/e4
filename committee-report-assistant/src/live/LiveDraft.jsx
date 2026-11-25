// Live stage 2: the draft. Research, analysis and slides come together here: the slides are shown as they will be exported, every text can be edited
// on the slide itself or changed by asking AI (one slide, one section or the whole deck), and everything is saved as you go. There is no approval step:
// the saved draft is the final version, and downloading it is recorded.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowLeft, ArrowRight, Check, ChevronRight, Download, FileText, Globe, GripVertical, Layers, Lock, Plus, Send, Sparkles, Trash2, Undo2, UserRound, X } from 'lucide-react';
import { t } from '../i18n.js';
import { api, saveBlob } from './client.js';
import { errText, Empty, Spin, useAction } from './kit.jsx';
import { ImageLibrary, ResearchPlan, Running, Sources } from './LiveMaterial.jsx';
import SlideCanvas from './SlideCanvas.jsx';

const isSystem = (s) => s.section_key.startsWith('_');

const SUGGEST = {
  slide: ['Make the text shorter', 'Make the title a clear statement', 'Add a speaker note'],
  section: ['Go into more detail on cost', 'Shorter, for senior management', 'Add the risks'],
  deck: ['Shorter overall, for senior management', 'More focus on the decision', 'Remove the appendix details'],
};

// ------------------------------------------------------------------------------------------ what needs a look
function Attention({ items, deck, rid, toast, reload, load, onJump }) {
  const [busy, run] = useAction(toast);
  if (!items.length) return <Empty icon={<Check size={22} />} title={t('Nothing needs your attention')}>{t('Every statement on the slides is backed by a source. You can download the draft any time.')}</Empty>;
  const done = (fn) => async () => { await fn(); await Promise.all([load(true), reload()]); };
  const include = (it) => run(it.id, done(async () => {
    const r = await api.includeClaim(rid, it.id);
    if (r.mode === 'slide') toast(r.changed ? t('Taken in: the slide was updated.') : (r.needs?.[0] || t('The finding is approved, but the slide could not be changed without a language model.')), r.changed ? undefined : 'warn');
    else toast(t('Writing the section again…'));
  }));
  const leave = (it) => run(it.id, done(() => api.patchClaim(rid, it.id, { status: 'rejected' })));
  const dismiss = (it) => run(it.id, done(() => api.resolveFlag(rid, it.id, 'dismissed', null)));
  return (
    <ul className="lv-attn">
      {items.map((it) => (
        <li key={`${it.kind}-${it.id}`} className={it.severity}>
          <div className="lv-attn-h">{it.severity === 'blocker' ? <AlertTriangle size={15} /> : <Sparkles size={15} />}
            <strong>{it.kind === 'claim' ? t('Left out: not backed by the sources') : it.severity === 'blocker' ? t('Please check') : t('Note')}</strong>
            {it.section && <span className="muted small">{it.section}</span>}</div>
          <p>{it.text}</p>
          {it.issues?.length > 0 && <ul className="lv-issues">{it.issues.map((x, i) => <li key={i}>{x}</li>)}</ul>}
          <div className="lv-row">
            {it.slide_id && <button className="btn quiet sm" onClick={() => onJump(it.slide_id)}>{t('Show slide')}</button>}
            {it.kind === 'claim' ? (
              <>
                <button className="btn sm" disabled={!!busy} onClick={() => include(it)}>{busy === it.id ? <Spin size={13} /> : <Plus size={13} />} {t('Take into the slides')}</button>
                <button className="btn quiet sm" disabled={!!busy} onClick={() => leave(it)}><X size={13} /> {t('Leave out')}</button>
              </>
            ) : <button className="btn sm" disabled={!!busy} onClick={() => dismiss(it)}>{busy === it.id ? <Spin size={13} /> : <Check size={13} />} {t('Got it')}</button>}
          </div>
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------------------------------ why a slide says what it says
function Why({ slide }) {
  const [open, setOpen] = useState(null);
  if (!slide.claims.length) return <p className="muted small">{slide.locked ? t('This slide is generated from the others.') : t('No source is linked to this slide.')}</p>;
  return (
    <ul className="lv-why">
      {slide.claims.map((cl) => (
        <li key={cl.id}>
          <button className="lv-why-h" onClick={() => setOpen(open === cl.id ? null : cl.id)}><ChevronRight size={13} className={open === cl.id ? 'rot' : ''} /><span>{cl.text}</span></button>
          {open === cl.id && (
            <ul className="lv-why-ev">
              {cl.evidence.map((e) => (
                <li key={e.id}><span className="lv-ev-src">{e.origin === 'user' ? <UserRound size={12} /> : e.origin === 'web' ? <Globe size={12} /> : <FileText size={12} />} {e.source || '—'}{e.locator ? ` · ${e.locator}` : ''}</span>
                  <blockquote>{e.quote || e.statement}</blockquote></li>
              ))}
              {cl.calculations.map((k) => <li key={k.id}><span className="lv-ev-src">{k.label}</span><code>{k.formula} = {k.value}{k.unit ? ` ${k.unit}` : ''}</code></li>)}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------------------------------ the material behind the draft
function Material({ rid, sections, toast, onClose, onApply }) {
  const [tab, setTab] = useState('sources');
  return (
    <div className="lv-drawer" role="dialog" aria-label={t('Material')}>
      <div className="lv-drawer-in">
        <header><h2>{t('The material behind the slides')}</h2><button className="iconbtn" onClick={onClose} aria-label={t('Close')}><X size={18} /></button></header>
        <div className="lv-seg" role="tablist">
          {[['sources', 'Sources'], ['images', 'Pictures and charts'], ['plan', 'Research plan']].map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{t(l)}</button>)}
        </div>
        <div className="lv-drawer-body">
          {tab === 'sources' ? <Sources rid={rid} /> : tab === 'images' ? <ImageLibrary rid={rid} sections={sections} toast={toast} onApply={onApply} /> : <ResearchPlan rid={rid} />}
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------ the draft itself
function Editor({ rid, c, reload, layouts, lang, toast }) {
  const [deck, setDeck] = useState(null);
  const [sel, setSel] = useState(null);
  const [panel, setPanel] = useState('slide');
  const [drawer, setDrawer] = useState(false);
  const [scope, setScope] = useState('slide');
  const [text, setText] = useState('');
  const [result, setResult] = useState({});
  const [dismissed, setDismissed] = useState(null);
  const [busy, run] = useAction(toast);
  const drag = useRef(null);
  const job = c.job;
  const working = !!job && ['queued', 'running'].includes(job.status);
  const editable = c.state === 'DECK_REVIEW' && !working;

  const load = useCallback(async (keep) => {
    try { const d = await api.deck(rid); setDeck(d); setSel((s) => (keep && d.slides.some((x) => x.id === s) ? s : d.slides[0]?.id || null)); return d; } catch (e) { toast(errText(e), 'warn'); return null; }
  }, [rid, toast]);
  useEffect(() => { if (c.state === 'DECK_REVIEW') load(true); }, [c.state, job?.id, job?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const theme = useMemo(() => ({ ...layouts?.theme, ...(deck?.theme || {}), colors: { ...layouts?.theme?.colors, ...(deck?.theme?.colors || {}) }, fonts: { ...layouts?.theme?.fonts, ...(deck?.theme?.fonts || {}) }, palette: deck?.theme?.palette || layouts?.theme?.palette }), [layouts, deck]);
  const idx = deck ? deck.slides.findIndex((s) => s.id === sel) : -1;
  const slide = idx >= 0 ? deck.slides[idx] : null;
  const sections = useMemo(() => (deck ? [...new Map(deck.slides.filter((s) => !isSystem(s)).map((s) => [s.section_key, { key: s.section_key, title: s.section }])).values()] : []), [deck]);
  const patchLocal = (id, fn) => setDeck((d) => ({ ...d, slides: d.slides.map((s) => (s.id === id ? fn(s) : s)) }));
  useEffect(() => { if (scope === 'section' && slide && isSystem(slide)) setScope('slide'); }, [scope, slide]);

  if (!deck || !layouts) return <div className="lv-stage"><p className="muted"><Spin /> {t('Loading…')}</p></div>;

  const edit = (spec) => {
    patchLocal(slide.id, (s) => ({ ...s, spec, title: spec.title }));
    run('edit', async () => {
      const r = await api.patchSlide(rid, slide.id, spec);
      patchLocal(slide.id, (s) => ({ ...s, spec: r.spec, title: r.spec.title, can_undo: true, user_edited: true }));
      setResult((x) => ({ ...x, [slide.id]: { ...(x[slide.id] || {}), warnings: r.warnings } }));
    }).then(() => load(true));
  };
  const ask = (override) => run('ask', async () => {
    const q = (override ?? text).trim();
    const r = await api.ask(rid, { text: q, scope, slide_id: slide?.id || null, section_key: slide && !isSystem(slide) ? slide.section_key : null });
    if (r.mode === 'slide') {
      patchLocal(slide.id, (s) => ({ ...s, spec: r.spec, title: r.spec.title, can_undo: r.changed || s.can_undo }));
      setResult((x) => ({ ...x, [slide.id]: { summary: r.summary, needs: r.needs, warnings: r.warnings, changed: r.changed } }));
      if (r.changed) setText('');
      await load(true);
    } else if (r.mode === 'job') {
      setText(''); setResult((x) => ({ ...x, [slide?.id]: { summary: t('Working on: {s}', { s: r.sections.join(', ') }), changed: true, needs: r.manual?.length ? [t('Reordering: drag the slides in the list on the left.')] : [] } }));
      await reload();
    } else {
      setResult((x) => ({ ...x, [slide?.id]: { summary: r.clarification || t('Nothing was changed. Say which slide or section you mean.'), changed: false, needs: (r.manual || []).length ? [t('Reordering: drag the slides in the list on the left.')] : [] } }));
    }
  });
  const undoSlide = () => run('undo', async () => { const r = await api.undoSlide(rid, slide.id); patchLocal(slide.id, (s) => ({ ...s, spec: r.spec, title: r.spec.title })); setResult((x) => ({ ...x, [slide.id]: undefined })); await load(true); });
  const undoAi = () => run('undoai', async () => { await api.undoAsk(rid); await Promise.all([load(true), reload()]); toast(t('Undone.')); });
  const add = (layout = 'bullets') => run('add', async () => { const r = await api.addSlide(rid, slide?.id || null, layout); await load(); setSel(r.id); });
  const del = () => window.confirm(t('Delete this slide?')) && run('del', async () => { await api.deleteSlide(rid, slide.id); await load(); });
  const drop = (to) => { const id = drag.current; drag.current = null; if (id && id !== deck.slides[to]?.id) run('mv', async () => { await api.moveSlide(rid, id, to); await load(true); }); };
  const download = () => run('dl', async () => { const { name, blob } = await api.downloadDeck(rid); saveBlob(blob, name); toast(t('PowerPoint file saved: {n} slides.', { n: deck.export.slides })); });
  const applyPictures = (key) => api.ask(rid, { text: lang === 'de' ? 'Setze die gewählten Bilder und Diagramme dieses Abschnitts neu ein.' : 'Place the chosen pictures and charts of this section again.', scope: 'section', section_key: key }).then(() => reload());
  const jump = (id) => { setSel(id); setPanel('slide'); };

  const res = slide ? result[slide.id] : null;
  const attn = deck.attention || [];
  const saving = busy === 'edit';
  const scopeLabel = { slide: t('This slide'), section: t('This section'), deck: t('Whole deck') };
  const failed = job?.status === 'failed' && dismissed !== job.id ? job : null;

  return (
    <div className="lv-report">
      <div className="lv-rbar">
        <div><h1 className="lv-rtitle">{c.title}</h1>
          <p className="muted small lv-saved">{saving ? <><Spin size={12} /> {t('Saving…')}</> : <><Check size={13} /> {t('Saved automatically')}</>}{deck.template ? ` · ${deck.template}` : ''}</p></div>
        <div className="lv-rtools">
          <button className="btn" onClick={() => setDrawer(true)}><Layers size={16} /> {t('Material')}</button>
          <button className={`btn${attn.length ? ' attn' : ''}`} onClick={() => setPanel(panel === 'attention' ? 'slide' : 'attention')}>{attn.length ? <AlertTriangle size={16} /> : <Check size={16} />} {attn.length ? t('{n} to look at', { n: attn.length }) : t('All clear')}</button>
          <button className="btn primary" disabled={!!busy || working} onClick={download}>{busy === 'dl' ? <Spin /> : <Download size={16} />} {t('Download PowerPoint')}</button>
        </div>
      </div>
      {deck.export.shared > 0 && <p className="muted small lv-exportnote">{t('The file has {n} slides: short sections that follow each other share a page. You can adjust that in PowerPoint.', { n: deck.export.slides })}</p>}
      {working && <div className="lv-jobbar" role="status"><Spin size={15} /> <span>{job.progress?.log?.slice(-1)[0] || t('Working…')}</span><span className="muted small">{t('The slides can be edited again when this is done.')}</span></div>}
      {failed && <div className="lv-banner warn"><AlertTriangle size={20} /><div><strong>{t('The last change could not be made')}</strong><span>{failed.error} {t('Your draft is as it was.')}</span></div><button className="btn sm" onClick={() => setDismissed(failed.id)}>{t('OK')}</button></div>}

      <div className="lv-work">
        <div className="lv-film" aria-label={t('Slides')}>
          {deck.slides.map((s, i) => (
            <div key={s.id} className="lv-film-item">
              {(i === 0 || deck.slides[i - 1].section_key !== s.section_key) && <p className="lv-film-sec">{s.section}</p>}
              <button className={`lv-thumb${s.id === sel ? ' on' : ''}`} draggable={editable && !isSystem(s)}
                onDragStart={() => { drag.current = s.id; }} onDragOver={(e) => e.preventDefault()} onDrop={() => drop(i)} onClick={() => setSel(s.id)}>
                <span className="lv-thumb-n">{s.locked || isSystem(s) ? <Lock size={10} /> : <GripVertical size={11} />}{i + 1}</span>
                {s.attention > 0 && <i className="lv-dot warn lv-thumb-dot" title={t('open flags')} />}
                <SlideCanvas spec={s.spec} layouts={layouts} theme={theme} page={i + 1} lang={lang} rid={rid} />
              </button>
              {s.shares_with_next && <p className="lv-film-share" title={t('In the file these two share one page')}>↧ {t('shares a page with the next')}</p>}
            </div>
          ))}
          {editable && <button className="lv-thumb add" onClick={() => add()} disabled={!!busy}><Plus size={18} /> {t('Add slide')}</button>}
        </div>

        <div className="lv-canvas">
          {slide && (
            <>
              <div className="lv-sbar">
                <span className="muted small">{t('Slide {n} of {total}', { n: idx + 1, total: deck.slides.length })} · {slide.section}</span>
                <span className="grow" />
                <button className="btn quiet sm" disabled={!editable || !slide.can_undo || !!busy} onClick={undoSlide}><Undo2 size={14} /> {t('Undo')}</button>
                <button className="iconbtn" disabled={idx <= 0} onClick={() => setSel(deck.slides[idx - 1].id)} title={t('Previous')}><ArrowLeft size={16} /></button>
                <button className="iconbtn" disabled={idx >= deck.slides.length - 1} onClick={() => setSel(deck.slides[idx + 1].id)} title={t('Next')}><ArrowRight size={16} /></button>
              </div>
              <div className={`lv-slide${editable && !slide.locked ? ' editable' : ''}`}>
                <SlideCanvas key={slide.id} spec={slide.spec} layouts={layouts} theme={theme} page={idx + 1} lang={lang} rid={rid} onChange={editable && !slide.locked ? edit : undefined} />
              </div>
              <p className="muted small lv-hint">{slide.locked ? <><Lock size={12} /> {t('This slide is generated from the others and cannot be edited.')}</> : editable ? t('Click any text on the slide to edit it, or ask AI below. Everything is saved as you go.') : t('The draft is being updated; editing is back in a moment.')}</p>

              <section className="card pad lv-ask">
                <div className="lv-ask-top">
                  <h3><Sparkles size={15} /> {t('Ask AI')}</h3>
                  <div className="lv-seg sm" role="radiogroup" aria-label={t('What should AI change?')}>
                    {['slide', 'section', 'deck'].map((k) => <button key={k} role="radio" aria-checked={scope === k} className={scope === k ? 'on' : ''} disabled={k === 'section' && isSystem(slide)} onClick={() => setScope(k)}>{scopeLabel[k]}</button>)}
                  </div>
                </div>
                <form className="lv-ask-row" onSubmit={(e) => { e.preventDefault(); if (text.trim().length > 2) ask(); }}>
                  <input className="lv-in" value={text} disabled={!editable || (scope === 'slide' && slide.locked)} onChange={(e) => setText(e.target.value)}
                    placeholder={scope === 'slide' ? t('What should change on this slide?') : scope === 'section' ? t('What should change in “{s}”?', { s: slide.section }) : t('What should change in the whole deck?')} />
                  <button className="btn primary" disabled={!editable || !!busy || text.trim().length < 3 || (scope === 'slide' && slide.locked)}>{busy === 'ask' ? <Spin /> : <Send size={15} />} {t('Send')}</button>
                </form>
                <div className="chips lv-chips">{SUGGEST[scope].map((s) => <button key={s} type="button" className="opt" disabled={!editable} onClick={() => setText(t(s))}>{t(s)}</button>)}</div>
                {scope !== 'slide' && <p className="muted small">{t('A section or the whole deck is written again from the findings; changes you made by hand in it are replaced. You can undo the last such change.')}</p>}
                {res?.summary && <p className={`lv-res${res.changed ? '' : ' none'}`}>{res.changed ? <Check size={13} /> : <AlertTriangle size={13} />} {res.summary}</p>}
                {res?.needs?.length > 0 && <ul className="lv-needs">{res.needs.map((n, i) => <li key={i}>{n}</li>)}</ul>}
                {res?.warnings?.length > 0 && <ul className="lv-needs warn">{res.warnings.map((n, i) => <li key={i}><AlertTriangle size={12} /> {n}</li>)}</ul>}
                {deck.ai_undo && <button className="btn quiet sm" disabled={!editable || !!busy} onClick={undoAi}><Undo2 size={14} /> {t('Undo the last AI change')}: “{deck.ai_undo.label}”</button>}
              </section>
            </>
          )}
        </div>

        <aside className="lv-insp">
          {panel === 'attention' ? (
            <section className="card pad"><h3><AlertTriangle size={15} /> {t('Needs your attention')}</h3>
              <p className="muted small">{t('Nothing here stops you from downloading the draft.')}</p>
              <Attention items={attn} deck={deck} rid={rid} toast={toast} reload={reload} load={load} onJump={jump} /></section>
          ) : slide && (
            <>
              <section className="card pad"><h3>{t('Why does this slide say that?')}</h3><Why key={slide.id} slide={slide} />
                {slide.spec.source_line && <p className="muted small">{slide.spec.source_line}</p>}</section>
              <section className="card pad">
                <h3>{t('Speaker notes')}</h3>
                <textarea key={slide.id + (slide.spec.notes || '').length} className="lv-in" rows={4} defaultValue={slide.spec.notes || ''} disabled={!editable || slide.locked}
                  onBlur={(e) => { if (e.target.value !== (slide.spec.notes || '')) edit({ ...slide.spec, notes: e.target.value }); }} />
              </section>
              {editable && (
                <div className="lv-row">
                  <select className="lv-in" value="" onChange={(e) => e.target.value && add(e.target.value)} aria-label={t('Add slide')}>
                    <option value="">{t('Add slide with layout…')}</option>
                    {Object.entries(layouts.layouts).filter(([k]) => k !== 'decision').map(([k, v]) => <option key={k} value={k}>{v.label[lang] || v.label.en}</option>)}
                  </select>
                  <button className="btn quiet sm" disabled={!!busy || slide.locked || ['_title', '_summary', '_decision'].includes(slide.section_key)} onClick={del}><Trash2 size={14} /> {t('Delete')}</button>
                </div>
              )}
            </>
          )}
        </aside>
      </div>
      {drawer && <Material rid={rid} sections={sections} toast={toast} onClose={() => setDrawer(false)} onApply={applyPictures} />}
    </div>
  );
}

// ------------------------------------------------------------------------------------------ the screen
export default function LiveDraft({ rid, c, reload, layouts, lang, toast, go }) {
  const [busy, run] = useAction(toast);
  const working = ['COLLECTING', 'ANALYSING', 'FINDINGS_REVIEW', 'GENERATING'].includes(c.state) || (c.job?.status === 'failed' && ['research', 'generate'].includes(c.job.kind) && !c.deck);
  if (['SETUP', 'OUTLINE_REVIEW'].includes(c.state) && !(c.job?.status === 'failed' && c.job.kind === 'research')) {
    return <div className="lv-stage"><Empty icon={<Sparkles size={24} />} title={t('The draft is made after the brief')}>{t('Approve the outline in the brief to start. Research, analysis and the slides then run in one go.')}
      <button className="btn primary" onClick={() => go('brief')}>{t('To the brief')}</button></Empty></div>;
  }
  if (!c.deck && working) {
    const retry = () => run('retry', async () => { await (c.state === 'FINDINGS_REVIEW' ? api.buildDeck(rid) : api.rerun(rid, null)); await reload(); });
    return <Running rid={rid} c={c} busy={busy} onRetry={retry} />;
  }
  if (!c.deck && c.state !== 'DECK_REVIEW') return <div className="lv-stage"><p className="muted"><Spin /> {t('Loading…')}</p></div>;
  return <Editor rid={rid} c={c} reload={reload} layouts={layouts} lang={lang} toast={toast} />;
}
