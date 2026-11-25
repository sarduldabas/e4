// Live brief: the same screen as the demo's (composer, understood chips, material, report structure, strength, quick questions),
// but every part is real: the text and fields are saved on the server, files are uploaded and read, the structure comes from the template analyst.
import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, ArrowRight, Check, ChevronDown, ChevronUp, Link2, Loader2, Mic, Paperclip, Plus, Sparkles, Square, UploadCloud, X } from 'lucide-react';
import { t } from '../i18n.js';
import { api } from './client.js';
import { bytes, errText, nf, useAction, useDebouncedEffect } from './kit.jsx';
import { ActionBar, ProgressRing, SourceIcon } from '../components/ui.jsx';
import { extKind, SmartChip } from '../components/StageBrief.jsx';

const ROLE_LABEL = { source: 'Source', template: 'Template', prior_report: 'Previous report' };
const SpeechRecognition = typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : undefined;

function readInfo(info) {
  if (!info) return '';
  const bits = [info.pages ? t('{n} pages/slides/sheets', { n: info.pages }) : null, info.chars ? t('{n} characters of text', { n: nf(info.chars) }) : null,
    info.figures ? t('{n} figures', { n: info.figures }) : null].filter(Boolean);
  return bits.join(' · ');
}

export default function LiveBrief({ rid, c, reload, lang, toast, go, autoVoice }) {
  const open = ['SETUP', 'OUTLINE_REVIEW'].includes(c.state);
  const [busy, run] = useAction(toast);
  const [f, setF] = useState(null);                 // text, overrides, decision, links, web
  const [committees, setCommittees] = useState([]);
  const [files, setFiles] = useState([]);
  const [assess, setAssess] = useState(null);
  const [secs, setSecs] = useState(null);
  const [answers, setAnswers] = useState({});
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkText, setLinkText] = useState('');
  const [drag, setDrag] = useState(false);
  const [uploading, setUploading] = useState(0);
  const [editOutline, setEditOutline] = useState(null);
  const dirty = useRef(false);
  const outlineDirty = useRef(false);
  const tried = useRef(false);
  const taRef = useRef(null);
  const fileRefs = { source: useRef(null), template: useRef(null), prior_report: useRef(null) };

  useEffect(() => {
    setF({ text: c.description || '', topic: c.topic || '', committee: c.committee || '', decision: c.decision_requested || '', links: c.links || [], web: c.use_web !== false });
    api.committees().then(setCommittees).catch(() => {});
    api.files(rid).then(setFiles).catch(() => {});
    api.outline(rid).then((o) => { setSecs(o); tried.current = o.length > 0; }).catch(() => setSecs([]));
  }, [rid]); // eslint-disable-line react-hooks/exhaustive-deps

  // ----- save the brief as it is typed -----
  const com = f && committees.find((x) => x.name === f.committee || x.id === f.committee);
  const u = assess?.understood || {};
  const topic = (f?.topic || u.topic || '').trim();
  const committeeName = f?.committee || u.committee || '';
  const comId = (committees.find((x) => x.name === committeeName || x.id === committeeName) || {}).id;
  const caseBody = () => ({ topic, description: f.text, decision_requested: f.decision, lang, use_web: f.web, links: f.links, ...(comId ? { committee_id: comId } : {}) });
  const save = async () => { await api.putCase(rid, caseBody()); dirty.current = false; await reload(); };
  useDebouncedEffect(() => { save().catch((e) => toast(errText(e), 'warn')); }, [JSON.stringify(f), topic, comId], 900, !!f && dirty.current && open);
  const edit = (patch) => { dirty.current = true; setF((x) => ({ ...x, ...(typeof patch === 'function' ? patch(x) : patch) })); };

  // ----- what the brief agent thinks of it (the same call as in the demo) -----
  useDebouncedEffect(() => {
    const ctrl = new AbortController();
    api.assess({ lang, text: `${f.text}\n${f.decision}`.trim(), overrides: { topic: f.topic || null, committee: f.committee || null }, preset_committee: null,
      files: files.map((x) => ({ name: x.name, kind: extKind(x.name), status: 'ready' })), links: f.links, connectors: { web: f.web }, answers }, ctrl.signal)
      .then(setAssess).catch(() => {});
    return () => ctrl.abort();
  }, [f?.text, f?.decision, f?.topic, f?.committee, JSON.stringify(f?.links), files.length, f?.web, JSON.stringify(answers), lang], 900, !!f);

  // ----- the structure: made once the topic is clear, as the demo shows it from the start -----
  const propose = () => run('prop', async () => { await save(); const r = await api.proposeOutline(rid); setSecs(r.sections); outlineDirty.current = false; await reload(); });
  const ready = topic.length >= 3 && ((f?.text || '').trim().length >= 20 || files.length > 0);
  useDebouncedEffect(() => { tried.current = true; propose(); }, [ready, files.length], 2200, open && ready && secs !== null && secs.length === 0 && !tried.current && !busy);
  useDebouncedEffect(() => run('osave', async () => { await api.putOutline(rid, secs); outlineDirty.current = false; }), [JSON.stringify(secs)], 900, outlineDirty.current && !!secs && open);
  const editSecs = (fn) => { outlineDirty.current = true; setSecs((s) => fn(s.map((x) => ({ ...x })))); };
  const move = (i, d) => editSecs((s) => { const j = i + d; if (j >= 0 && j < s.length) [s[i], s[j]] = [s[j], s[i]]; return s; });

  // ----- files -----
  const upload = async (list, role = 'source') => {
    setUploading((n) => n + 1);
    for (const file of [...list]) {
      try { await api.upload(rid, file, role); } catch (e) { toast(`${file.name}: ${errText(e)}`, 'warn'); }
    }
    setFiles(await api.files(rid)); setUploading((n) => n - 1); reload();
  };
  const removeFile = (fl) => run(fl.id, async () => { await api.deleteFile(rid, fl.id); setFiles(await api.files(rid)); reload(); });
  const addLink = () => { const v = linkText.trim(); if (!v) return; edit((x) => ({ links: [...x.links, v] })); setLinkText(''); setLinkOpen(false); };

  // ----- voice (the browser's own speech input) -----
  const [listening, setListening] = useState(false);
  const rec = useRef(null);
  const want = useRef(false);
  const startVoice = () => {
    if (!SpeechRecognition) { toast(t('Speech input is not supported in this browser. Please use Chrome or Edge.')); return; }
    const r = new SpeechRecognition();
    r.lang = lang === 'de' ? 'de-DE' : 'en-US'; r.continuous = true; r.interimResults = false;
    r.onresult = (e) => { for (let i = e.resultIndex; i < e.results.length; i += 1) if (e.results[i].isFinal) edit((x) => ({ text: `${x.text} ${e.results[i][0].transcript.trim()}`.trim() })); };
    r.onerror = (e) => { if (['not-allowed', 'service-not-allowed'].includes(e.error)) { want.current = false; toast(t('Microphone access was blocked. Allow the microphone in your browser and try again.')); } };
    r.onend = () => { if (want.current) { try { r.start(); return; } catch { /* running */ } } setListening(false); };
    rec.current = r; want.current = true;
    try { r.start(); setListening(true); } catch { want.current = false; }
  };
  const stopVoice = () => { want.current = false; rec.current?.stop(); setListening(false); };
  useEffect(() => () => { want.current = false; rec.current?.abort?.(); }, []);
  useEffect(() => { if (autoVoice && open) { const tm = setTimeout(startVoice, 500); return () => clearTimeout(tm); } return undefined; }, []); // eslint-disable-line

  useEffect(() => { const el = taRef.current; if (el) { el.style.height = 'auto'; el.style.height = `${Math.max(150, el.scrollHeight)}px`; } }, [f?.text]);

  if (!f || secs === null) return <div className="stage"><p className="muted"><Loader2 size={16} className="spin" /> {t('Loading…')}</p></div>;

  const words = f.text.trim().split(/\s+/).filter(Boolean).length;
  const readyFiles = files.length;
  const included = secs.filter((o) => o.included).length;
  const templateFile = files.find((x) => x.role === 'template');
  const templateName = templateFile?.name || com?.template || committees.find((x) => x.name === u.committee)?.template || '';
  const dateText = c.date ? c.date.split('-').reverse().join('.') : (u.date || '');
  const strength = assess ? assess.strength.score : 0;
  const canStart = open && topic.length >= 3 && included > 0;
  const approve = () => run('approve', async () => {
    await save();
    const answered = (assess?.questions || []).filter((q) => answers[q.id]);
    for (const q of answered) { try { await api.turn(rid, `${q.text} ${q.options.find((o) => o.id === answers[q.id])?.label || ''}`.trim(), false); } catch { /* the answer is also part of the brief */ } }
    await api.approveOutline(rid); await reload(); go('draft');
  });
  const questions = assess?.questions || [];
  const chip = (key, label, ph, value, onCommit) => <SmartChip def={{ key, label, ph }} value={value} onCommit={(_, v) => open && onCommit(v)} />;

  return (
    <div className="stage stage-brief">
      <header className="stage-head">
        <p className="eyebrow">{t('Step 1 of 2 · Brief')}</p>
        <h1 className="display lg">{t('Tell me what you are')} <em>{t('presenting.')}</em></h1>
        <p className="lede">{t('Speak or type, the way you would brief a colleague. Drop in whatever you have. I organise it.')}</p>
        <div className="expect">
          <div><span className="expect-k">{t('From you')}</span><span>{t('A few sentences and your material. About two minutes.')}</span></div>
          <div><span className="expect-k">{t('Then')}</span><span>{t('I analyse everything and show you what I found. Nothing is final.')}</span></div>
        </div>
      </header>

      {!open && <div className="banner"><Check size={18} /><div><strong>{t('The draft has been made')}</strong><span>{t('The brief is locked once the draft is made. Change the draft itself with Ask AI or directly on the slides.')}</span></div><button className="btn primary sm" onClick={() => go('draft')}>{t('To the draft')}</button></div>}

      <div className="brief-grid">
        <div className="brief-main">
          <section className="composer card">
            <div className="composer-top">
              <label htmlFor="brief-text" className="sr-only">{t('Your brief')}</label>
              <textarea id="brief-text" ref={taRef} value={f.text} disabled={!open} onChange={(e) => edit({ text: e.target.value })}
                placeholder={t('What is the topic? What should the committee decide? What do you already know?')} />
              {listening && <div className="wave" aria-hidden="true">{Array.from({ length: 18 }).map((_, i) => <i key={i} style={{ animationDelay: `${(i % 6) * 0.11}s` }} />)}</div>}
            </div>
            <div className="composer-bar">
              <button type="button" className={`mic${listening ? ' live' : ''}`} disabled={!open} onClick={listening ? stopVoice : startVoice} aria-pressed={listening}>
                <span className="mic-ico">{listening ? <Square size={16} fill="currentColor" /> : <Mic size={20} />}</span>
                <span>{listening ? t('Listening… {time}', { time: '' }).trim() : t('Speak')}</span>
              </button>
              <button type="button" className="btn quiet sm" disabled={!open} onClick={() => fileRefs.source.current?.click()}><Paperclip size={15} /> {t('Add files')}</button>
              <button type="button" className="btn quiet sm" disabled={!open} onClick={() => setLinkOpen((v) => !v)}><Link2 size={15} /> {t('Add link')}</button>
              <span className="grow" />
              <span className="muted small">{t('{n} words', { n: words })}</span>
            </div>
            <div className="understood">
              <p className="understood-title"><Sparkles size={14} /> {t('What I understood so far')}</p>
              <div className="chips">
                {chip('topic', 'Topic', 'Add topic', topic, (v) => edit({ topic: v }))}
                <span className={`smart-chip ${committeeName ? 'found' : 'missing'}`}>
                  <span className="sc-label">{t('Committee')}</span>
                  <select className="sc-select" value={comId || ''} disabled={!open} aria-label={t('Committee')} onChange={(e) => edit({ committee: committees.find((k) => k.id === e.target.value)?.name || '' })}>
                    <option value="">{t('Add committee')}</option>
                    {committees.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
                  </select>
                  {committeeName ? <Check size={13} strokeWidth={2.4} className="sc-ok" /> : <Plus size={13} />}
                </span>
                {dateText && <span className="smart-chip found static"><span className="sc-label">{t('Committee date')}</span><span className="sc-value">{dateText}</span><Check size={13} strokeWidth={2.4} className="sc-ok" /></span>}
                {chip('decision', 'Decision requested', 'Add decision', f.decision, (v) => edit({ decision: v }))}
                <button type="button" className={`smart-chip ${templateName ? 'found' : 'missing'}`} disabled={!open} onClick={() => fileRefs.template.current?.click()} title={t('Upload template (.pptx)')}>
                  <span className="sc-label">{t('Template')}</span><span className="sc-value">{templateName || t('Choose template')}</span>{templateName ? <Check size={13} strokeWidth={2.4} className="sc-ok" /> : <Plus size={13} />}
                </button>
              </div>
            </div>
          </section>

          <section className="card pad">
            <div className="card-head"><h2>{t('Material')}</h2><span className="muted small">{t('{n} items', { n: readyFiles + f.links.length })}</span></div>
            <div className={`drop${drag ? ' over' : ''}`} onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); if (open) upload(e.dataTransfer.files); }}>
              <UploadCloud size={22} strokeWidth={1.5} />
              <div>
                <strong>{uploading ? t('Uploading and checking…') : t('Drop mails, presentations, PDFs, spreadsheets')}</strong>
                <span>{t('or')} <button type="button" className="textlink" disabled={!open} onClick={() => fileRefs.source.current?.click()}>{t('browse')}</button>
                  {' '}{t('·')} <button type="button" className="textlink" disabled={!open} onClick={() => fileRefs.template.current?.click()}>{t('use your own template')}</button>
                  {' '}{t('·')} <button type="button" className="textlink" disabled={!open} onClick={() => fileRefs.prior_report.current?.click()}>{t('add a previous report')}</button></span>
              </div>
              {Object.entries(fileRefs).map(([role, ref]) => (
                <input key={role} ref={ref} type="file" hidden multiple={role === 'source'} accept={role === 'template' ? '.pptx,.potx' : undefined} onChange={(e) => { upload(e.target.files, role); e.target.value = ''; }} />
              ))}
            </div>
            {linkOpen && (
              <div className="inline-add">
                <input autoFocus value={linkText} onChange={(e) => setLinkText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addLink()} placeholder={t('Paste a Confluence, Jira, SharePoint or web link')} aria-label={t('Link')} />
                <button className="btn sm" onClick={addLink}>{t('Add')}</button>
              </div>
            )}
            {(files.length > 0 || f.links.length > 0 || uploading > 0) && (
              <ul className="files">
                {files.map((fl) => (
                  <li key={fl.id} className="ready">
                    <span className="f-ico"><SourceIcon kind={extKind(fl.name)} /></span>
                    <span className="f-main"><strong>{fl.name}</strong><span className="muted small">{[t(ROLE_LABEL[fl.role] || fl.role), bytes(fl.size), readInfo(fl.info)].filter(Boolean).join(' · ')}</span>
                      {fl.info?.warnings?.length > 0 && <span className="muted small"><AlertTriangle size={12} /> {fl.info.warnings[0]}</span>}</span>
                    {busy === fl.id ? <Loader2 size={16} className="spin" /> : <Check size={16} className="ok" />}
                    <button className="iconbtn sm" disabled={!open} onClick={() => removeFile(fl)} aria-label={t('Remove {name}', { name: fl.name })}><X size={15} /></button>
                  </li>
                ))}
                {uploading > 0 && <li className="reading"><span className="f-ico"><Loader2 size={16} className="spin" /></span><span className="f-main"><strong>{t('Reading…')}</strong></span></li>}
                {f.links.map((l) => (
                  <li key={l}><span className="f-ico"><SourceIcon kind="link" /></span>
                    <span className="f-main"><strong>{l}</strong><span className="muted small">{t('Link · will be read during analysis')}</span></span>
                    <button className="iconbtn sm" disabled={!open} onClick={() => edit((x) => ({ links: x.links.filter((y) => y !== l) }))} aria-label={t('Remove link')}><X size={15} /></button></li>
                ))}
              </ul>
            )}
            <div className="conn">
              <span className="conn-label">{t('Also look in')}</span>
              <div className="chips">
                <button type="button" className={`toggle-chip${f.web && c.web_enabled ? ' on' : ''}`} disabled={!open || !c.web_enabled} onClick={() => edit((x) => ({ web: !x.web }))} aria-pressed={f.web} title={t('Search the public web and read the pages it finds')}>
                  {f.web && c.web_enabled ? <Check size={13} strokeWidth={2.4} /> : <Plus size={13} />} {t('Public web')}
                </button>
              </div>
            </div>
          </section>

          <section className="card pad">
            <div className="card-head"><h2>{t('Report structure')}</h2>
              <span className="muted small">{secs.length ? `${t('{n} sections', { n: included })}` : ''}{open && secs.length > 0 && <> · <button className="textlink" disabled={!!busy} onClick={propose}>{busy === 'prop' ? t('Working…') : t('Propose again')}</button></>}</span></div>
            <p className="muted small tight">{t('Taken from your template. Reorder, rename or leave out sections. The analysis follows this structure.')}</p>
            {secs.length === 0 ? (
              <p className="muted small">{busy === 'prop' ? <><Loader2 size={14} className="spin" /> {t('Working…')}</> : t('The structure appears here as soon as the topic is clear. It comes from your template, or from the topic and the committee.')}</p>
            ) : (
              <ol className="outline">
                {secs.map((o, i) => (
                  <li key={o.key || i} className={o.included ? '' : 'off'}>
                    <span className="o-num">{String(i + 1).padStart(2, '0')}</span>
                    <input type="checkbox" checked={o.included} disabled={!open} onChange={(e) => editSecs((x) => { x[i].included = e.target.checked; return x; })} aria-label={t('Include {title}', { title: o.title })} />
                    {editOutline === i ? (
                      <input className="o-edit" autoFocus value={o.title} onChange={(e) => editSecs((x) => { x[i].title = e.target.value; return x; })} onBlur={() => setEditOutline(null)} onKeyDown={(e) => e.key === 'Enter' && setEditOutline(null)} aria-label={t('Section title')} />
                    ) : (
                      <button type="button" className="o-title" disabled={!open} onClick={() => setEditOutline(i)} title={t('Click to rename')}>{o.title}</button>
                    )}
                    <span className="o-move">
                      <button className="iconbtn sm" disabled={!open || i === 0} onClick={() => move(i, -1)} aria-label={t('Move up')}><ChevronUp size={15} /></button>
                      <button className="iconbtn sm" disabled={!open || i === secs.length - 1} onClick={() => move(i, 1)} aria-label={t('Move down')}><ChevronDown size={15} /></button>
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>

        <aside className="brief-side">
          <section className="card pad strength">
            <div className="strength-top">
              <ProgressRing value={strength} />
              <div>
                <p className="eyebrow tight">{t('Brief strength')}</p>
                <h3>{assess?.strength.label || '…'}</h3>
                <p className="muted small">{assess ? assess.strength.summary : t('You can start at any time. More input makes the analysis sharper.')}</p>
              </div>
            </div>
            {assess?.strength.hints?.length > 0 && (
              <ul className="hints"><li className="hints-title">{t('What would help most')}</li>{assess.strength.hints.slice(0, 3).map((h) => <li key={h}><span className="dot" />{h}</li>)}</ul>
            )}
            {assess && <p className="agent-tag"><Sparkles size={12} /> {t(assess.agent?.mode === 'llm' ? 'Assessed by the brief agent (AI)' : 'Assessed by the brief agent')}</p>}
          </section>

          {questions.length > 0 && (
            <section className="card pad">
              <div className="card-head"><h2>{t('Three quick questions')}</h2><span className="muted small">{t('Optional')}</span></div>
              <ul className="qs">
                {questions.map((q) => {
                  const a = answers[q.id] || null;
                  return (
                    <li key={q.id} className={a ? 'done' : ''}>
                      <p>{a && <Check size={14} className="ok" />} {q.text}</p>
                      <div className="chips">
                        {q.options.map((o) => <button key={o.id} type="button" disabled={!open} className={`opt${a === o.id ? ' on' : ''}`} aria-pressed={a === o.id} onClick={() => setAnswers((x) => ({ ...x, [q.id]: a === o.id ? null : o.id }))}>{o.label}</button>)}
                      </div>
                    </li>
                  );
                })}
              </ul>
              <p className="muted small tight">{t('Skipping is fine. I will make a reasonable assumption and mark it.')}</p>
            </section>
          )}
        </aside>
      </div>

      {open && (
        <ActionBar>
          <div className="ab-text">
            <strong>{t('Next: Analysis')}</strong>
            <span>{!topic ? t('Start with the topic: say what the report is about.') : secs.length === 0 ? (busy === 'prop' ? t('Working on the structure…') : t('I draft the structure as soon as you have said a little more.')) : t('I read {files}, search the web and cross-check every figure.', { files: readyFiles ? t('{n} files', { n: readyFiles }) : t('your text') })}</span>
          </div>
          <button className="btn primary lg" disabled={!canStart || !!busy} onClick={approve}>{busy === 'approve' ? <Loader2 size={16} className="spin" /> : null} {t('Start analysis')} <ArrowRight size={18} /></button>
        </ActionBar>
      )}
    </div>
  );
}
