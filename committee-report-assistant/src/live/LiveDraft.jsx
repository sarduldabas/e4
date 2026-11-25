// Live stage 2: the draft. Research, analysis and slides come together here: the slides are shown as they will be exported, every text can be edited
// on the slide itself or changed by asking AI (one slide, one section or the whole deck), and everything is saved as you go. There is no approval step:
// the saved draft is the final version, and downloading it is recorded.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowLeft, Check, ChevronLeft, ChevronRight, Download, FileText, Globe, Info, Layers, Loader2, Play, Plus, Send, Sparkles, Trash2, Undo2, UserRound, X } from 'lucide-react';
import { t } from '../i18n.js';
import { api, saveBlob } from './client.js';
import { Empty, errText, Spin, useAction } from './kit.jsx';
import { ActionBar, SourceIcon } from '../components/ui.jsx';
import AskAI, { useThread } from '../components/AskAI.jsx';
import { ImageLibrary, ResearchPlan, Running, Sources } from './LiveMaterial.jsx';
import SlideCanvas from './SlideCanvas.jsx';

const isSystem = (s) => s.section_key.startsWith('_');

// ------------------------------------------------------------------------------------------ what needs a look (the demo's "checks" card)
function Checks({ items, rid, toast, reload, load, onJump }) {
  const [busy, run] = useAction(toast);
  const done = (fn) => async () => { await fn(); await Promise.all([load(true), reload()]); };
  const include = (it) => run(it.id, done(async () => {
    const r = await api.includeClaim(rid, it.id);
    if (r.mode === 'slide') toast(r.changed ? t('Taken in: the slide was updated.') : (r.needs?.[0] || t('The finding is approved, but the slide could not be changed without a language model.')), r.changed ? undefined : 'warn');
    else toast(t('Writing the section again…'));
  }));
  const leave = (it) => run(it.id, done(() => api.patchClaim(rid, it.id, { status: 'rejected' })));
  const dismiss = (it) => run(it.id, done(() => api.resolveFlag(rid, it.id, 'dismissed', null)));
  return (
    <ul className="checks">
      {items.length === 0 && <li className="ok"><Check size={15} /><span>{t('Every statement on the slides is backed by a source.')}</span></li>}
      {items.map((it) => (
        <li key={`${it.kind}-${it.id}`} className="warn">
          <AlertTriangle size={15} />
          <span>
            {it.kind === 'claim' ? <>{t('Left out, not backed by the sources')}: {it.text}{it.issues?.length > 0 && ` (${it.issues.join('; ')})`}</> : <>{it.section ? `${it.section}: ` : ''}{it.text}</>}
            {' '}{it.slide_id && <button className="textlink" onClick={() => onJump(it.slide_id)}>{t('Show slide')}</button>}
            {it.kind === 'claim' ? (
              <> <button className="textlink" disabled={!!busy} onClick={() => include(it)}>{busy === it.id ? t('Working…') : t('Take into the slides')}</button> <button className="textlink" disabled={!!busy} onClick={() => leave(it)}>{t('Leave out')}</button></>
            ) : <> <button className="textlink" disabled={!!busy} onClick={() => dismiss(it)}>{t('Got it')}</button></>}
          </span>
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
  const [drawer, setDrawer] = useState(false);
  const [scope, setScope] = useState('slide');
  const [result, setResult] = useState({});
  const [dismissed, setDismissed] = useState(null);
  const [why, setWhy] = useState(false);
  const [present, setPresent] = useState(false);
  const [busy, run] = useAction(toast);
  const [thread, addMsg, updateMsg] = useThread();
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
  const manualNote = (r) => ((r.manual || []).length ? [t('Reordering: drag the slides in the list on the left.')] : []);
  const undoSlideFor = (slideId, msgId) => () => run('undo', async () => {
    const r = await api.undoSlide(rid, slideId);
    patchLocal(slideId, (s) => ({ ...s, spec: r.spec, title: r.spec.title }));
    updateMsg(msgId, { undo: null, undone: true });
    await load(true);
  });
  const ask = (q) => {
    const sl = slide;
    const id = addMsg({ text: q, tag: scopeLabel[scope], pending: true });
    return run('ask', async () => {
      try {
        const r = await api.ask(rid, { text: q, scope, slide_id: sl?.id || null, section_key: sl && !isSystem(sl) ? sl.section_key : null });
        if (r.mode === 'slide') {
          patchLocal(sl.id, (x) => ({ ...x, spec: r.spec, title: r.spec.title, can_undo: r.changed || x.can_undo }));
          const reply = r.summary || (r.changed ? t('Done.') : (r.needs || [])[0] || t('Nothing was changed.'));
          updateMsg(id, { pending: false, tone: r.changed ? 'ok' : 'warn', reply, notes: [...(r.needs || []), ...(r.warnings || [])].filter((n) => n !== reply), undo: r.changed ? undoSlideFor(sl.id, id) : null });
          await load(true);
        } else if (r.mode === 'job') {
          updateMsg(id, { pending: false, reply: t('Working on: {s}', { s: r.sections.join(', ') }), notes: manualNote(r) });
          await reload();
        } else {
          updateMsg(id, { pending: false, tone: 'warn', reply: r.clarification || t('Nothing was changed. Say which slide or section you mean.'), notes: manualNote(r) });
        }
      } catch (e) {
        updateMsg(id, { pending: false, tone: 'warn', reply: errText(e) });
      }
    });
  };
  const undoAi = () => run('undoai', async () => { await api.undoAsk(rid); await Promise.all([load(true), reload()]); toast(t('Undone.')); });
  const add = (layout = 'bullets') => run('add', async () => { const r = await api.addSlide(rid, slide?.id || null, layout); await load(); setSel(r.id); });
  const del = () => window.confirm(t('Delete this slide?')) && run('del', async () => { await api.deleteSlide(rid, slide.id); await load(); });
  const drop = (to) => { const id = drag.current; drag.current = null; if (id && id !== deck.slides[to]?.id) run('mv', async () => { await api.moveSlide(rid, id, to); await load(true); }); };
  const download = () => run('dl', async () => { const { name, blob } = await api.downloadDeck(rid); saveBlob(blob, name); toast(t('PowerPoint file saved: {n} slides.', { n: deck.export.slides })); });
  const applyPictures = (key) => api.ask(rid, { text: lang === 'de' ? 'Setze die gewählten Bilder und Diagramme dieses Abschnitts neu ein.' : 'Place the chosen pictures and charts of this section again.', scope: 'section', section_key: key }).then(() => reload());
  const jump = (id) => setSel(id);

  const res = slide ? result[slide.id] : null;
  const attn = deck.attention || [];
  const saving = busy === 'edit';
  const scopeLabel = { slide: t('This slide'), section: t('This section'), deck: t('Whole deck') };
  const failed = job?.status === 'failed' && dismissed !== job.id ? job : null;
  const sources = slide ? [...new Map(slide.claims.flatMap((cl) => cl.evidence).filter((e) => e.source).map((e) => [e.source, e])).values()] : [];
  const kindOf = (e) => (e.origin === 'web' ? 'web' : /\.pptx?\b/i.test(e.source) ? 'pptx' : /\.xlsx?\b/i.test(e.source) ? 'xlsx' : 'pdf');

  return (
    <div className="stage stage-report">
      <header className="stage-head compact">
        <div>
          <p className="eyebrow">{t('Step 2 · Draft')}</p>
          <h1 className="display md">{t('Your draft is ready.')} <em>{t('Adjust it, then download.')}</em></h1>
        </div>
        <span className="muted small">{saving ? <><Spin size={12} /> {t('Saving…')}</> : <><Check size={13} /> {t('Saved automatically')}</>}</span>
      </header>

      {working && <div className="banner" role="status"><Loader2 size={18} className="spin" /><div><strong>{job.progress?.log?.slice(-1)[0] || t('Working…')}</strong><span>{t('The slides can be edited again when this is done.')}</span></div></div>}
      {failed && <div className="banner"><AlertTriangle size={18} /><div><strong>{t('The last change could not be made')}</strong><span>{failed.error} {t('Your draft is as it was.')}</span></div><button className="btn sm" onClick={() => setDismissed(failed.id)}>{t('OK')}</button></div>}

      <div className="rep-grid">
        <aside className="rail" aria-label={t('Slides')}>
          {deck.slides.map((s, i) => (
            <button key={s.id} className={`thumb${i === idx ? ' on' : ''}`} draggable={editable && !isSystem(s)} onDragStart={() => { drag.current = s.id; }} onDragOver={(e) => e.preventDefault()} onDrop={() => drop(i)}
              onClick={() => setSel(s.id)} aria-label={t('Slide {n}', { n: i + 1 })} title={s.shares_with_next ? t('In the file these two share one page') : undefined}>
              <span className="t-n">{i + 1}</span>
              <span className="t-frame"><SlideCanvas spec={s.spec} layouts={layouts} theme={theme} page={i + 1} lang={lang} rid={rid} /></span>
              {s.attention > 0 && <span className="t-stale" title={t('open flags')} />}
            </button>
          ))}
          {editable && <button className="thumb add" onClick={() => add()} disabled={!!busy} aria-label={t('Add slide')}><span className="t-frame add-frame"><Plus size={18} /> {t('Add slide')}</span></button>}
        </aside>

        <main className="canvas-col">
          <div className="canvas-bar">
            <span className="tpl"><FileText size={14} /> {deck.template || t('Committee template')}</span>
            <button className="btn quiet sm" onClick={() => setDrawer(true)}><Layers size={14} /> {t('Material')}</button>
            <span className="grow" />
            <button className="iconbtn" disabled={idx <= 0} onClick={() => setSel(deck.slides[idx - 1].id)} aria-label={t('Previous slide')}><ChevronLeft size={18} /></button>
            <span className="small muted">{t('Slide {n} of {total}', { n: idx + 1, total: deck.slides.length })}</span>
            <button className="iconbtn" disabled={idx >= deck.slides.length - 1} onClick={() => setSel(deck.slides[idx + 1].id)} aria-label={t('Next slide')}><ChevronRight size={18} /></button>
          </div>
          <div className="canvas">
            <div className={`lv-slide${editable && !slide.locked ? ' editable' : ''}`}>
              <SlideCanvas key={slide.id} spec={slide.spec} layouts={layouts} theme={theme} page={idx + 1} lang={lang} rid={rid} onChange={editable && !slide.locked ? edit : undefined} />
            </div>
          </div>
          <p className="canvas-hint"><Info size={13} /> {slide.locked ? t('This slide is generated from the others and cannot be edited.') : editable ? t('Click any text on the slide to edit it.') : t('The draft is being updated; editing is back in a moment.')}</p>
          {res?.warnings?.map((n, i) => <p key={i} className="canvas-hint"><AlertTriangle size={13} /> {n}</p>)}
          {sources.length > 0 && (
            <div className="slide-src">
              <span className="muted small">{t('Sources on this slide')}</span>
              {sources.map((e) => <span key={e.source} className="src-pill" title={e.quote || e.statement}><SourceIcon kind={kindOf(e)} size={13} /> {e.source}</span>)}
              <button className="textlink small" onClick={() => setWhy(!why)}>{why ? t('Hide evidence') : t('Show evidence')}</button>
            </div>
          )}
          {why && <section className="card pad"><h2>{t('Why does this slide say that?')}</h2><Why key={slide.id} slide={slide} /></section>}
        </main>

        <aside className="panel">
          <AskAI
            scopes={['slide', 'section', 'deck'].map((k) => ({ key: k, label: scopeLabel[k], disabled: k === 'section' && isSystem(slide) }))}
            scope={scope} onScope={setScope}
            target={scope === 'slide' ? t('Slide {n}', { n: idx + 1 }) : scope === 'section' ? t('Section “{s}”', { s: slide.section }) : t('All {n} slides', { n: deck.slides.length })}
            thread={thread} busy={busy === 'ask'} toast={toast} onSend={ask}
            disabled={!editable || (scope === 'slide' && slide.locked)}
            disabledNote={!editable ? t('The draft is being updated; Ask AI is back in a moment.') : scope === 'slide' && slide.locked ? t('This slide is generated from the others; ask on the section or the whole deck instead.') : null}
            restore={deck.ai_undo ? { label: deck.ai_undo.label, onUndo: undoAi } : null}
            placeholder={scope === 'slide' ? t('e.g. “Make the three figures easier to compare and cut the second bullet”') : scope === 'section' ? t('e.g. “Go into more detail on the risks and name the cost per option”') : t('e.g. “Shorter overall, for senior management, with more focus on the decision”')}
          />

          <section className="card pad">
            <div className="card-head"><h2>{t('Checks')}</h2><span className={`pill ${attn.length ? 'warn' : 'good'}`}>{attn.length ? t('{n} to look at', { n: attn.length }) : t('All clear')}</span></div>
            <Checks items={attn} rid={rid} toast={toast} reload={reload} load={load} onJump={jump} />
          </section>

          <section className="card pad">
            <h2>{t('Speaker notes')} <span className="muted small">· {t('slide {n}', { n: idx + 1 })}</span></h2>
            <textarea key={slide.id + (slide.spec.notes || '').length} className="notes" rows={4} defaultValue={slide.spec.notes || ''} disabled={!editable || slide.locked}
              placeholder={t('What you want to say on this slide')} aria-label={t('Speaker notes')}
              onBlur={(e) => { if (e.target.value !== (slide.spec.notes || '')) edit({ ...slide.spec, notes: e.target.value }); }} />
            {editable && !slide.locked && !['_title', '_summary', '_decision'].includes(slide.section_key) && <button className="btn quiet sm" disabled={!!busy} onClick={del}><Trash2 size={14} /> {t('Delete slide')}</button>}
          </section>
        </aside>
      </div>

      <ActionBar>
        <div className="ab-text">
          <strong>{attn.length ? t(attn.length > 1 ? '{n} points need attention' : '{n} point needs attention', { n: attn.length }) : t('Ready to download')}</strong>
          <span>{deck.export.shared > 0 ? t('The file has {n} slides: short sections that follow each other share a page. You can adjust that in PowerPoint.', { n: deck.export.slides }) : t('Nothing here stops you from downloading the draft.')}</span>
        </div>
        <button className="btn quiet" onClick={() => go('brief')}><ArrowLeft size={16} /> {t('Brief')}</button>
        <button className="btn" onClick={() => setPresent(true)}><Play size={15} /> {t('Present')}</button>
        <button className="btn primary lg" disabled={!!busy || working} onClick={download}>{busy === 'dl' ? <Spin /> : <Download size={17} />} {t('Download PowerPoint')}</button>
      </ActionBar>

      {present && <Present deck={deck} layouts={layouts} theme={theme} lang={lang} rid={rid} start={Math.max(0, idx)} onClose={() => setPresent(false)} />}
      {drawer && <Material rid={rid} sections={sections} toast={toast} onClose={() => setDrawer(false)} onApply={applyPictures} />}
    </div>
  );
}

function Present({ deck, layouts, theme, lang, rid, start, onClose }) {
  const [i, setI] = useState(start);
  const n = deck.slides.length;
  useEffect(() => {
    const k = (e) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowRight' || e.key === ' ') setI((x) => Math.min(n - 1, x + 1));
      if (e.key === 'ArrowLeft') setI((x) => Math.max(0, x - 1));
    };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [n, onClose]);
  return (
    <div className="present" onClick={() => setI((x) => Math.min(n - 1, x + 1))}>
      <button className="iconbtn light" onClick={(e) => { e.stopPropagation(); onClose(); }} aria-label={t('Exit presentation')}><X size={20} /></button>
      <div className="present-slide"><SlideCanvas spec={deck.slides[i].spec} layouts={layouts} theme={theme} page={i + 1} lang={lang} rid={rid} /></div>
      <p className="present-hint">{i + 1} / {n} · {t('Arrow keys to move · Esc to close')}</p>
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
