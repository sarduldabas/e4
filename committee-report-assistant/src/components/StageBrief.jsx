import { t, getLang } from '../i18n.js';
import { useEffect, useRef, useState } from 'react';
import {
  Mic, Square, Paperclip, Link2, Check, X, ArrowRight, ChevronUp, ChevronDown, Plus, Loader2, Sparkles, UploadCloud,
} from 'lucide-react';
import { SAMPLE_FILE_IDS, SRC, CONNECTORS, BRIEF_QUESTIONS } from '../data.js';
import { detect, briefStrength, fileFromSource } from '../workspace.js';
import { ActionBar, ProgressRing, SourceIcon, useInterval } from './ui.jsx';

const CHIPS = [
  { key: 'topic', label: 'Topic', ph: 'Add topic' },
  { key: 'committee', label: 'Committee', ph: 'Add committee' },
  { key: 'date', label: 'Committee date', ph: 'Add date' },
  { key: 'audience', label: 'Audience', ph: 'Add audience' },
  { key: 'template', label: 'Template', ph: 'Choose template' },
];

export const extKind = (name) => {
  const e = name.split('.').pop().toLowerCase();
  if (['ppt', 'pptx', 'potx'].includes(e)) return 'pptx';
  if (e === 'pdf') return 'pdf';
  if (['xls', 'xlsx', 'csv'].includes(e)) return 'xlsx';
  if (['msg', 'eml'].includes(e)) return 'mail';
  return 'pdf';
};

export function SmartChip({ def, value, onCommit }) {
  const [edit, setEdit] = useState(false);
  const [v, setV] = useState('');
  const ref = useRef(null);
  useEffect(() => { if (edit) ref.current?.focus(); }, [edit]);
  const commit = () => { onCommit(def.key, v.trim()); setEdit(false); };
  if (edit) {
    return (
      <span className="smart-chip editing">
        <span className="sc-label">{t(def.label)}</span>
        <input ref={ref} value={v} onChange={(e) => setV(e.target.value)} onBlur={commit} onKeyDown={(e) => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEdit(false); }} aria-label={t(def.label)} />
      </span>
    );
  }
  return (
    <button type="button" className={`smart-chip ${value ? 'found' : 'missing'}`} onClick={() => { setV(value ? t(value) : ''); setEdit(true); }} title={t("Click to change")}>
      <span className="sc-label">{t(def.label)}</span>
      <span className="sc-value" key={value || 'x'}>{value ? t(value) : t(def.ph)}</span>
      {value ? <Check size={13} strokeWidth={2.4} className="sc-ok" /> : <Plus size={13} />}
    </button>
  );
}

const SpeechRecognition = typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : undefined;

export default function StageBrief({ ws, assessment, setBrief, briefChanged, onStart, autoVoice, toast }) {
  const b = ws.brief;
  const d = detect(b);
  const ag = assessment; // answer of the Brief agent (via backend); null = offline, use the local logic below
  const strength = ag ? ag.strength.score : briefStrength(b);
  const taRef = useRef(null);
  const fileRef = useRef(null);
  const [drag, setDrag] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkText, setLinkText] = useState('');
  const [connecting, setConnecting] = useState({});
  const [editOutline, setEditOutline] = useState(null);

  // ----- voice: the browser's own speech input (Web Speech API; Chrome and Edge) -----
  // Note: Chrome sends the audio to Google's speech service. For production replace this with Azure Speech
  // inside the Volkswagen environment (see README, section Speech).
  const [listening, setListening] = useState(false);
  const [secs, setSecs] = useState(0);
  const recRef = useRef(null);
  const wantRef = useRef(false); // true while the user wants to keep dictating (Chrome ends sessions after silence)
  const base = useRef('');
  const finals = useRef('');
  const startVoice = () => {
    if (!SpeechRecognition) { toast(t('Speech input is not supported in this browser. Please use Chrome or Edge.')); return; }
    base.current = b.text ? `${b.text.trim()} ` : '';
    finals.current = '';
    const rec = new SpeechRecognition();
    rec.lang = getLang() === 'de' ? 'de-DE' : 'en-US';
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i += 1) {
        const r = e.results[i];
        if (r.isFinal) finals.current += `${r[0].transcript.trim()} `; else interim += r[0].transcript;
      }
      setBrief({ text: (base.current + finals.current + interim).replace(/\s+/g, ' ').replace(/^\s+/, '') });
    };
    rec.onerror = (e) => {
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') { wantRef.current = false; toast(t('Microphone access was blocked. Allow the microphone in your browser and try again.')); }
      else if (e.error === 'audio-capture') { wantRef.current = false; toast(t('No microphone found.')); }
      else if (e.error === 'network') { wantRef.current = false; toast(t('The speech service could not be reached. Please check your connection.')); }
      // 'no-speech' and 'aborted' are normal: onend decides whether to continue
    };
    rec.onend = () => {
      if (wantRef.current) {
        base.current += finals.current; finals.current = '';
        try { rec.start(); return; } catch (err) { /* already running */ }
      }
      setListening(false); briefChanged('text');
    };
    recRef.current = rec; wantRef.current = true;
    try { rec.start(); setSecs(0); setListening(true); } catch (err) { wantRef.current = false; }
  };
  const stopVoice = () => { wantRef.current = false; recRef.current?.stop(); setListening(false); briefChanged('text'); };
  useInterval(() => setSecs((s) => s + 1), 1000, listening);
  useEffect(() => () => { wantRef.current = false; recRef.current?.abort?.(); }, []);
  useEffect(() => { if (autoVoice) { const tm = setTimeout(startVoice, 500); return () => clearTimeout(tm); } return undefined; }, []); // eslint-disable-line

  useEffect(() => {
    const el = taRef.current;
    if (el) { el.style.height = 'auto'; el.style.height = `${Math.max(150, el.scrollHeight)}px`; }
  }, [b.text]);

  // ----- files -----
  const addReal = (list) => {
    [...list].forEach((f, i) => {
      const id = `u${Date.now()}${i}`;
      const kind = extKind(f.name);
      setBrief((x) => ({ ...x, files: [...x.files, { id, name: f.name, kind, detail: '', status: 'reading' }] }));
      setTimeout(() => {
        const n = 2 + (f.size % 7);
        setBrief((x) => ({ ...x, files: x.files.map((y) => (y.id === id ? { ...y, status: 'ready', kb: Math.round(f.size / 1024), n } : y)) }));
        briefChanged('files');
      }, 900 + i * 300);
    });
  };
  const addSample = () => {
    SAMPLE_FILE_IDS.filter((id) => !b.files.some((f) => f.srcId === id)).forEach((id, i) => {
      setTimeout(() => setBrief((x) => ({ ...x, files: [...x.files, { ...fileFromSource(id), status: 'reading' }] })), i * 380);
      setTimeout(() => { setBrief((x) => ({ ...x, files: x.files.map((y) => (y.srcId === id ? { ...y, status: 'ready' } : y)) })); briefChanged('files'); }, i * 380 + 1000);
    });
  };
  const removeFile = (id) => { setBrief((x) => ({ ...x, files: x.files.filter((f) => f.id !== id) })); briefChanged('files'); };
  const addLink = () => {
    if (!linkText.trim()) return;
    setBrief((x) => ({ ...x, links: [...x.links, { id: `l${Date.now()}`, url: linkText.trim() }] }));
    setLinkText(''); setLinkOpen(false); briefChanged('files');
  };
  const toggleConn = (id) => {
    if (b.connectors[id]) { setBrief((x) => ({ ...x, connectors: { ...x.connectors, [id]: false } })); briefChanged('connectors'); return; }
    setConnecting((c) => ({ ...c, [id]: true }));
    setTimeout(() => {
      setConnecting((c) => ({ ...c, [id]: false }));
      setBrief((x) => ({ ...x, connectors: { ...x.connectors, [id]: true } }));
      briefChanged('connectors');
    }, 700);
  };

  // ----- outline -----
  const move = (i, dir) => setBrief((x) => {
    const o = [...x.outline]; const j = i + dir;
    if (j < 0 || j >= o.length) return x;
    [o[i], o[j]] = [o[j], o[i]]; return { ...x, outline: o };
  });
  const patchOutline = (id, patch) => setBrief((x) => ({ ...x, outline: x.outline.map((o) => (o.id === id ? { ...o, ...patch } : o)) }));

  const readyFiles = b.files.filter((f) => f.status === 'ready').length;
  const words = (b.text || '').trim().split(/\s+/).filter(Boolean).length;
  const hasPrecedent = b.files.some((f) => /fakom_report/i.test(f.name));
  const unanswered = BRIEF_QUESTIONS.filter((q) => !b.answers[q.id]);

  const localHints = [];
  if (words < 40) localHints.push(t('Say a few sentences about what you know and what you expect'));
  if (readyFiles + b.links.length < 3) localHints.push(t('Add the key documents, mails and previous reports'));
  if (!b.connectors.outlook) localHints.push(t('Let me look in Outlook for related mails'));
  if (unanswered.length) localHints.push(unanswered.length > 1 ? t('Answer {n} quick questions on the right', { n: unanswered.length }) : t('Answer 1 quick question on the right'));
  const hints = ag ? ag.strength.hints : localHints;
  const label = ag ? ag.strength.label : t(strength < 40 ? 'Getting started' : strength < 70 ? 'Good basis' : strength < 90 ? 'Strong brief' : 'Excellent brief');
  const canStart = ag ? ag.can_start : !!d.topic || b.files.length > 0;
  const questions = ag
    ? ag.questions
    : BRIEF_QUESTIONS.map((q) => ({ id: q.id, text: t(q.id === 'q3' && hasPrecedent ? q.textWithPrecedent : q.text), answer: b.answers[q.id] || null, options: q.options.map((o) => ({ id: o.id, label: t(o.label) })) }));
  const included = b.outline.filter((o) => o.included).length;

  return (
    <div className="stage stage-brief">
      <header className="stage-head">
        <p className="eyebrow">{t("Step 1 of 2 · Brief")}</p>
        <h1 className="display lg">{t("Tell me what you are")} <em>{t("presenting.")}</em></h1>
        <p className="lede">{t("Speak or type, the way you would brief a colleague. Drop in whatever you have. I organise it.")}</p>
        <div className="expect">
          <div><span className="expect-k">{t("From you")}</span><span>{t("A few sentences and your material. About two minutes.")}</span></div>
          <div><span className="expect-k">{t("Then")}</span><span>{t("I analyse everything and show you what I found. Nothing is final.")}</span></div>
        </div>
      </header>

      <div className="brief-grid">
        <div className="brief-main">
          {/* Composer */}
          <section className="composer card">
            <div className="composer-top">
              <label htmlFor="brief-text" className="sr-only">{t("Your brief")}</label>
              <textarea
                id="brief-text" ref={taRef} value={b.text}
                onChange={(e) => { setBrief({ text: e.target.value }); briefChanged('text'); }}
                placeholder={t("What is the topic? What should the committee decide? What do you already know?")}
              />
              {listening && (
                <div className="wave" aria-hidden="true">{Array.from({ length: 18 }).map((_, i) => <i key={i} style={{ animationDelay: `${(i % 6) * 0.11}s` }} />)}</div>
              )}
            </div>
            <div className="composer-bar">
              <button type="button" className={`mic${listening ? ' live' : ''}`} onClick={listening ? stopVoice : startVoice} aria-pressed={listening}>
                <span className="mic-ico">{listening ? <Square size={16} fill="currentColor" /> : <Mic size={20} />}</span>
                <span>{listening ? t('Listening… {time}', { time: `${String(Math.floor(secs / 60)).padStart(2, '0')}:${String(secs % 60).padStart(2, '0')}` }) : t('Speak')}</span>
              </button>
              <button type="button" className="btn quiet sm" onClick={() => fileRef.current?.click()}><Paperclip size={15} /> {t("Add files")}</button>
              <button type="button" className="btn quiet sm" onClick={() => setLinkOpen((v) => !v)}><Link2 size={15} /> {t("Add link")}</button>
              <span className="grow" />
              <span className="muted small">{t('{n} words', { n: words })}</span>
            </div>
            <div className="understood">
              <p className="understood-title"><Sparkles size={14} /> {t("What I understood so far")}</p>
              <div className="chips">
                {CHIPS.map((c) => (
                  <SmartChip key={c.key} def={c} value={d[c.key]} onCommit={(k, v) => { setBrief((x) => ({ ...x, overrides: { ...x.overrides, [k]: v || undefined } })); }} />
                ))}
              </div>
            </div>
          </section>

          {/* Material */}
          <section className="card pad">
            <div className="card-head">
              <h2>{t("Material")}</h2>
              <span className="muted small">{t('{n} items', { n: readyFiles + b.links.length })}{readyFiles ? ` · ${t('charts and tables are extracted for reuse')}` : ''}</span>
            </div>
            <div
              className={`drop${drag ? ' over' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); addReal(e.dataTransfer.files); }}
            >
              <UploadCloud size={22} strokeWidth={1.5} />
              <div>
                <strong>{t("Drop mails, presentations, PDFs, spreadsheets")}</strong>
                <span>{t("or")} <button type="button" className="textlink" onClick={() => fileRef.current?.click()}>{t("browse")}</button>{b.files.length === 0 && <> {t("·")} <button type="button" className="textlink" onClick={addSample}>{t("use sample material")}</button></>}</span>
              </div>
              <input ref={fileRef} type="file" multiple hidden onChange={(e) => { addReal(e.target.files); e.target.value = ''; }} />
            </div>

            {linkOpen && (
              <div className="inline-add">
                <input autoFocus value={linkText} onChange={(e) => setLinkText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addLink()} placeholder={t("Paste a Confluence, Jira, SharePoint or web link")} aria-label={t("Link")} />
                <button className="btn sm" onClick={addLink}>{t("Add")}</button>
              </div>
            )}

            {(b.files.length > 0 || b.links.length > 0) && (
              <ul className="files">
                {b.files.map((f) => (
                  <li key={f.id} className={f.status}>
                    <span className="f-ico"><SourceIcon kind={f.kind} /></span>
                    <span className="f-main"><strong>{t(f.name)}</strong><span className="muted small">{f.status === 'reading' ? t('Reading…') : f.srcId ? t(SRC[f.srcId].detail) : t('{kb} KB · {n} items found', { kb: f.kb, n: f.n })}</span></span>
                    {f.status === 'reading' ? <Loader2 size={16} className="spin" /> : <Check size={16} className="ok" />}
                    <button className="iconbtn sm" onClick={() => removeFile(f.id)} aria-label={t('Remove {name}', { name: f.name })}><X size={15} /></button>
                  </li>
                ))}
                {b.links.map((l) => (
                  <li key={l.id}>
                    <span className="f-ico"><SourceIcon kind="link" /></span>
                    <span className="f-main"><strong>{l.url}</strong><span className="muted small">{t("Link · will be read during analysis")}</span></span>
                    <button className="iconbtn sm" onClick={() => setBrief((x) => ({ ...x, links: x.links.filter((y) => y.id !== l.id) }))} aria-label={t("Remove link")}><X size={15} /></button>
                  </li>
                ))}
              </ul>
            )}

            <div className="conn">
              <span className="conn-label">{t("Also look in")}</span>
              <div className="chips">
                {CONNECTORS.map((c) => {
                  const on = b.connectors[c.id];
                  return (
                    <button key={c.id} type="button" className={`toggle-chip${on ? ' on' : ''}`} onClick={() => toggleConn(c.id)} aria-pressed={on} title={t(c.hint)}>
                      {connecting[c.id] ? <Loader2 size={13} className="spin" /> : on ? <Check size={13} strokeWidth={2.4} /> : <Plus size={13} />}
                      {t(c.label)}
                    </button>
                  );
                })}
              </div>
            </div>
          </section>

          {/* Structure */}
          <section className="card pad">
            <div className="card-head">
              <h2>{t("Report structure")}</h2>
              <span className="muted small">{t(d.template || 'Standard template')} · {t('{n} sections', { n: included })}</span>
            </div>
            <p className="muted small tight">{t("Taken from your template. Reorder, rename or leave out sections. The analysis follows this structure.")}</p>
            <ol className="outline">
              {b.outline.map((o, i) => (
                <li key={o.id} className={o.included ? '' : 'off'}>
                  <span className="o-num">{String(i + 1).padStart(2, '0')}</span>
                  <input type="checkbox" checked={o.included} onChange={(e) => patchOutline(o.id, { included: e.target.checked })} aria-label={t('Include {title}', { title: t(o.title) })} />
                  {editOutline === o.id ? (
                    <input className="o-edit" autoFocus value={t(o.title)} onChange={(e) => patchOutline(o.id, { title: e.target.value })} onBlur={() => setEditOutline(null)} onKeyDown={(e) => e.key === 'Enter' && setEditOutline(null)} aria-label={t("Section title")} />
                  ) : (
                    <button type="button" className="o-title" onClick={() => setEditOutline(o.id)} title={t("Click to rename")}>{t(o.title)}</button>
                  )}
                  <span className="o-move">
                    <button className="iconbtn sm" disabled={i === 0} onClick={() => move(i, -1)} aria-label={t("Move up")}><ChevronUp size={15} /></button>
                    <button className="iconbtn sm" disabled={i === b.outline.length - 1} onClick={() => move(i, 1)} aria-label={t("Move down")}><ChevronDown size={15} /></button>
                  </span>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <aside className="brief-side">
          <section className="card pad strength">
            <div className="strength-top">
              <ProgressRing value={strength} />
              <div>
                <p className="eyebrow tight">{t("Brief strength")}</p>
                <h3>{label}</h3>
                <p className="muted small">{ag ? ag.strength.summary : t("You can start at any time. More input makes the analysis sharper.")}</p>
              </div>
            </div>
            {hints.length > 0 && (
              <ul className="hints">
                <li className="hints-title">{t("What would help most")}</li>
                {hints.slice(0, 3).map((h) => <li key={h}><span className="dot" />{h}</li>)}
              </ul>
            )}
            {ag && <p className="agent-tag"><Sparkles size={12} /> {t(ag.agent?.mode === 'llm' ? 'Assessed by the brief agent (AI)' : 'Assessed by the brief agent')}</p>}
          </section>

          <section className="card pad">
            <div className="card-head"><h2>{t("Three quick questions")}</h2><span className="muted small">{t("Optional")}</span></div>
            <ul className="qs">
              {questions.map((q) => {
                const a = b.answers[q.id] || null;
                const text = q.text;
                return (
                  <li key={q.id} className={a ? 'done' : ''}>
                    <p>{a && <Check size={14} className="ok" />} {text}</p>
                    <div className="chips">
                      {q.options.map((o) => (
                        <button key={o.id} type="button" className={`opt${a === o.id ? ' on' : ''}`} aria-pressed={a === o.id}
                          onClick={() => { setBrief((x) => ({ ...x, answers: { ...x.answers, [q.id]: a === o.id ? null : o.id } })); briefChanged('answers'); }}>
                          {o.label}
                        </button>
                      ))}
                    </div>
                  </li>
                );
              })}
            </ul>
            <p className="muted small tight">{t("Skipping is fine. I will make a reasonable assumption and mark it.")}</p>
          </section>
        </aside>
      </div>

      <ActionBar>
        <div className="ab-text">
          <strong>{t("Next: Analysis")}</strong>
          <span>{t('I read {files}, search {n} sources and cross-check every figure. About 3 minutes.', { files: readyFiles ? t('{n} files', { n: readyFiles }) : t('your files'), n: Object.values(b.connectors).filter(Boolean).length })}</span>
        </div>
        <button className="btn primary lg" disabled={!canStart} onClick={onStart}>{t("Start analysis")} <ArrowRight size={18} /></button>
      </ActionBar>
    </div>
  );
}
