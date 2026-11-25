// Live stage 3: the slides. What is on screen is drawn from the same stored slide as the PowerPoint file, so the download is what you see.
// Edit text right on the slide, or write a comment and let the slide editor carry it out (numbers are checked against the evidence).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowLeft, ArrowRight, Download, FileCheck2, GripVertical, Lock, MessageSquare, Plus, Redo2, RefreshCw, Send, Sparkles, Trash2, Undo2, Wand2 } from 'lucide-react';
import { t } from '../i18n.js';
import { api, saveBlob } from './client.js';
import { errText, ProgressBar, Spin, useAction } from './kit.jsx';
import SlideCanvas from './SlideCanvas.jsx';

const GEN_STEPS = [['storyline', 'Plan the storyline'], ['writing slides', 'Write the slides'], ['building file', 'Build the PowerPoint file'], ['done', 'Done']];

function Generating({ c, go, busy }) {
  const j = c.job; const p = j?.progress || {};
  const failed = j?.status === 'failed';
  const idx = Math.max(0, GEN_STEPS.findIndex(([k]) => k === p.step));
  return (
    <div className="lv-stage">
      <div className="stage-head center"><p className="eyebrow">{t('Step 3 · Report')}</p>
        <h1 className="display md">{failed ? t('The slides could not be built') : t('Building your slides…')}</h1>
        <p className="lede">{failed ? j.error : t('Each section is written as slides with figures and charts; every number is checked against the evidence.')}</p></div>
      <div className="card pad lv-run">
        {!failed && <ProgressBar done={p.done || 0} total={p.total || 1} />}
        <ol className="lv-steps">{GEN_STEPS.map(([k, label], i) => <li key={k} className={i < idx ? 'done' : i === idx && !failed ? 'now' : ''}>{i < idx ? '✓' : i === idx && !failed ? <Spin size={14} /> : <i />}{t(label)}</li>)}</ol>
        {(p.log || []).length > 0 && <ul className="lv-log">{p.log.slice(-6).map((l, i) => <li key={i}>{l}</li>)}</ul>}
        {failed && <button className="btn" disabled={!!busy} onClick={() => go('analysis')}>{t('Back to the analysis')}</button>}
      </div>
    </div>
  );
}

function Feedback({ rid, c, reload, selected, toast, go }) {
  const [text, setText] = useState('');
  const [plan, setPlan] = useState(null);
  const [busy, run] = useAction(toast);
  const interpret = () => run('fb', async () => setPlan(await api.feedback(rid, text, selected)));
  const apply = () => run('apply', async () => { await api.applyFeedback(rid, plan.id); setPlan(null); setText(''); await reload(); go('analysis'); });
  return (
    <div className="lv-fb card pad">
      <h3><MessageSquare size={16} /> {t('Committee feedback → next version')}</h3>
      <p className="muted small">{t('Paste what the committee asked for. The agent turns it into changes and tells you how far back each one reaches (new research, new analysis, or only the slide).')}</p>
      <textarea className="lv-in" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder={t('e.g. “Please add a sensitivity analysis on the volume assumption.”')} />
      <button className="btn sm" disabled={!!busy || text.trim().length < 3} onClick={interpret}>{busy === 'fb' ? <Spin /> : <Wand2 size={14} />} {t('Interpret')}</button>
      {plan && (
        <div className="lv-plan">
          {plan.clarification && <p className="lv-note"><Sparkles size={15} /> {plan.clarification}</p>}
          <ul>{plan.changes.map((ch, i) => <li key={i}><span className="pill info">{ch.action.replace('_', ' ')}</span> {ch.instruction} <span className="muted small">→ {ch.rerun_from}</span></li>)}</ul>
          {plan.changes.length > 0 && <button className="btn primary sm" disabled={!!busy} onClick={apply}>{busy === 'apply' ? <Spin /> : <RefreshCw size={14} />} {t('Start the next version')}</button>}
        </div>
      )}
    </div>
  );
}

export default function LiveReport({ rid, c, reload, layouts, lang, toast, go }) {
  const [deck, setDeck] = useState(null);
  const [sel, setSel] = useState(null);
  const [comment, setComment] = useState('');
  const [result, setResult] = useState({}); // per slide: last revise summary / needs / warnings
  const [busy, run] = useAction(toast);
  const drag = useRef(null);
  const editable = c.state === 'DECK_REVIEW';

  const load = useCallback(async (keep) => {
    try { const d = await api.deck(rid); setDeck(d); setSel((s) => (keep && d.slides.some((x) => x.id === s) ? s : d.slides[0]?.id || null)); return d; } catch (e) { toast(errText(e), 'warn'); return null; }
  }, [rid, toast]);
  useEffect(() => { if (['DECK_REVIEW', 'FINAL', 'FEEDBACK'].includes(c.state)) load(true); }, [c.state, c.version_no]); // eslint-disable-line react-hooks/exhaustive-deps

  const theme = useMemo(() => ({ ...layouts?.theme, ...(deck?.theme || {}), colors: { ...layouts?.theme?.colors, ...(deck?.theme?.colors || {}) }, fonts: { ...layouts?.theme?.fonts, ...(deck?.theme?.fonts || {}) }, palette: deck?.theme?.palette || layouts?.theme?.palette }), [layouts, deck]);
  const idx = deck ? deck.slides.findIndex((s) => s.id === sel) : -1;
  const slide = idx >= 0 ? deck.slides[idx] : null;
  const patchLocal = (id, fn) => setDeck((d) => ({ ...d, slides: d.slides.map((s) => (s.id === id ? fn(s) : s)) }));

  if (['GENERATING'].includes(c.state) || (c.job?.kind === 'generate' && c.job.status === 'failed' && !deck)) return <Generating c={c} go={go} busy={busy} />;
  if (!['DECK_REVIEW', 'FINAL', 'FEEDBACK'].includes(c.state)) return <div className="lv-stage"><p className="muted">{t('The slides are built after you approve the findings.')}</p></div>;
  if (!deck || !layouts) return <div className="lv-stage"><p className="muted"><Spin /> {t('Loading…')}</p></div>;

  const edit = (spec) => {
    patchLocal(slide.id, (s) => ({ ...s, spec, title: spec.title }));
    run('edit', async () => {
      const r = await api.patchSlide(rid, slide.id, spec);
      patchLocal(slide.id, (s) => ({ ...s, spec: r.spec, title: r.spec.title, can_undo: true, user_edited: true }));
      setResult((x) => ({ ...x, [slide.id]: { ...(x[slide.id] || {}), warnings: r.warnings } }));
    }).then(() => load(true));
  };
  const revise = () => run('rev', async () => {
    const r = await api.reviseSlide(rid, slide.id, comment.trim());
    patchLocal(slide.id, (s) => ({ ...s, spec: r.spec, title: r.spec.title, can_undo: r.changed || s.can_undo }));
    setResult((x) => ({ ...x, [slide.id]: { summary: r.summary, needs: r.needs, warnings: r.warnings, changed: r.changed, mode: r.mode } }));
    if (r.changed) setComment('');
    await load(true);
  });
  const undo = () => run('undo', async () => { const r = await api.undoSlide(rid, slide.id); patchLocal(slide.id, (s) => ({ ...s, spec: r.spec, title: r.spec.title })); setResult((x) => ({ ...x, [slide.id]: undefined })); await load(true); });
  const add = (layout = 'bullets') => run('add', async () => { const r = await api.addSlide(rid, slide?.id || null, layout); await load(); setSel(r.id); });
  const del = () => window.confirm(t('Delete this slide?')) && run('del', async () => { await api.deleteSlide(rid, slide.id); await load(); });
  const drop = (to) => { const id = drag.current; drag.current = null; if (id && id !== deck.slides[to]?.id) run('mv', async () => { await api.moveSlide(rid, id, to); await load(true); }); };
  const download = () => run('dl', async () => { const { name, blob } = await api.downloadDeck(rid); saveBlob(blob, name); });
  const finalize = () => run('fin', async () => { await api.finalize(rid); await reload(); });
  const res = slide ? result[slide.id] : null;
  const unsaved = busy === 'edit';

  return (
    <div className="lv-report">
      <div className="lv-rbar">
        <div><p className="eyebrow">{t('Step 3 · Report')}</p><h1 className="lv-rtitle">{c.title} <span className="muted">· {deck.version}</span></h1></div>
        <div className="lv-rtools">
          {deck.template && <span className="pill" title={t('The slides use the colours and fonts of this template')}>{deck.template}</span>}
          <span className="muted small">{unsaved ? <><Spin size={13} /> {t('Saving…')}</> : t('{n} slides', { n: deck.slides.length })}</span>
          <button className="btn" disabled={!!busy} onClick={download}>{busy === 'dl' ? <Spin /> : <Download size={16} />} {t('Download PowerPoint')}</button>
          {c.state === 'DECK_REVIEW' && <button className="btn primary" disabled={!!busy} onClick={finalize}><FileCheck2 size={16} /> {t('Mark as final')}</button>}
          {c.state === 'FINAL' && <span className="pill good"><Lock size={12} /> {t('Final')}</span>}
        </div>
      </div>
      {deck.changes?.length > 0 && <div className="lv-note"><Sparkles size={15} /> <span><strong>{t('Changes since the last version')}:</strong> {deck.changes.map((x) => (typeof x === 'string' ? x : x.text || JSON.stringify(x))).slice(0, 4).join(' · ')}</span></div>}
      <div className="lv-work">
        <div className="lv-film" aria-label={t('Slides')}>
          {deck.slides.map((s, i) => (
            <button key={s.id} className={`lv-thumb${s.id === sel ? ' on' : ''}`} draggable={editable && !s.section_key.startsWith('_')}
              onDragStart={() => { drag.current = s.id; }} onDragOver={(e) => e.preventDefault()} onDrop={() => drop(i)} onClick={() => setSel(s.id)}>
              <span className="lv-thumb-n">{s.locked || s.section_key.startsWith('_') ? <Lock size={10} /> : <GripVertical size={11} />}{i + 1}</span>
              <SlideCanvas spec={s.spec} layouts={layouts} theme={theme} page={i + 1} lang={lang} rid={rid} />
            </button>
          ))}
          {editable && <button className="lv-thumb add" onClick={() => add()} disabled={!!busy}><Plus size={18} /> {t('Add slide')}</button>}
        </div>
        <div className="lv-canvas">
          {slide && (
            <>
              <div className="lv-sbar">
                <span className="muted small">{t('Slide {n} of {total}', { n: idx + 1, total: deck.slides.length })} · {slide.section}</span>
                <span className="grow" />
                <button className="iconbtn" disabled={idx <= 0} onClick={() => setSel(deck.slides[idx - 1].id)} title={t('Previous')}><ArrowLeft size={16} /></button>
                <button className="iconbtn" disabled={idx >= deck.slides.length - 1} onClick={() => setSel(deck.slides[idx + 1].id)} title={t('Next')}><ArrowRight size={16} /></button>
              </div>
              <div className={`lv-slide${editable && !slide.locked ? ' editable' : ''}`}>
                <SlideCanvas key={slide.id} spec={slide.spec} layouts={layouts} theme={theme} page={idx + 1} lang={lang} rid={rid} onChange={editable && !slide.locked ? edit : undefined} />
              </div>
              <p className="muted small lv-hint">{slide.locked ? <><Lock size={12} /> {t('This slide is generated from the others and cannot be edited.')}</> : editable ? t('Click any text on the slide to edit it. Changes are saved and appear in the PowerPoint file exactly like this.') : t('The report is final or being revised: slides are read-only.')}</p>
            </>
          )}
        </div>
        <aside className="lv-insp">
          {slide && (
            <>
              <section className="card pad">
                <h3><Sparkles size={15} /> {t('Ask the slide editor')}</h3>
                <textarea className="lv-in" rows={3} value={comment} disabled={!editable || slide.locked} onChange={(e) => setComment(e.target.value)}
                  placeholder={t('e.g. “Make the chart a bar chart and shorten the bullets.”')} onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && comment.trim().length > 2) revise(); }} />
                <div className="lv-row"><button className="btn primary sm" disabled={!editable || slide.locked || !!busy || comment.trim().length < 3} onClick={revise}>{busy === 'rev' ? <Spin /> : <Send size={14} />} {t('Apply comment')}</button>
                  <button className="btn quiet sm" disabled={!editable || !slide.can_undo || !!busy} onClick={undo}><Undo2 size={14} /> {t('Undo')}</button></div>
                {res?.summary && <p className={`lv-res${res.changed ? '' : ' none'}`}>{res.changed ? <Redo2 size={13} /> : <AlertTriangle size={13} />} {res.summary}</p>}
                {res?.needs?.length > 0 && <ul className="lv-needs">{res.needs.map((n, i) => <li key={i}>{n}</li>)}</ul>}
                {res?.warnings?.length > 0 && <ul className="lv-needs warn">{res.warnings.map((n, i) => <li key={i}><AlertTriangle size={12} /> {n}</li>)}</ul>}
              </section>
              <section className="card pad">
                <h3>{t('Speaker notes')}</h3>
                <textarea key={slide.id + (slide.spec.notes || '').length} className="lv-in" rows={4} defaultValue={slide.spec.notes || ''} disabled={!editable || slide.locked}
                  onBlur={(e) => { if (e.target.value !== (slide.spec.notes || '')) edit({ ...slide.spec, notes: e.target.value }); }} />
              </section>
              {(slide.claims.length > 0 || (slide.spec.evidence || []).length > 0) && (
                <section className="card pad"><h3>{t('Evidence behind this slide')}</h3>
                  <ul className="lv-evlist">{slide.claims.map((cl) => <li key={cl.id}>{cl.text}</li>)}</ul>
                  {slide.spec.source_line && <p className="muted small">{slide.spec.source_line}</p>}</section>
              )}
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
          {['DECK_REVIEW', 'FINAL'].includes(c.state) && <Feedback rid={rid} c={c} reload={reload} selected={sel} toast={toast} go={go} />}
        </aside>
      </div>
    </div>
  );
}
