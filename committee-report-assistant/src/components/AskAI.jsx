import { Fragment, useEffect, useRef, useState } from 'react';
import { Mic, Send, Sparkles, Undo2 } from 'lucide-react';
import { t, getLang } from '../i18n.js';

// The "Ask AI" card of the draft screen: a small chat, because this is where the final edits are made.
// Shared by the Demo and the Live draft so that both look and behave the same; only what happens on "send" differs.

const SpeechRecognition = typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : undefined;

/** The conversation of one draft session. Entries: { id, text, tag, pending, reply, tone, notes, undo, undone }. */
export function useThread() {
  const [thread, setThread] = useState([]);
  const add = (entry) => {
    const id = Math.random().toString(36).slice(2);
    setThread((l) => [...l, { id, ...entry }]);
    return id;
  };
  const update = (id, patch) => setThread((l) => l.map((x) => (x.id === id ? { ...x, ...patch } : x)));
  return [thread, add, update];
}

// Voice: the browser's own speech input (Web Speech API; Chrome and Edge). Dictation is appended to the text box.
function useDictation(value, setValue, toast) {
  const [on, setOn] = useState(false);
  const [secs, setSecs] = useState(0);
  const rec = useRef(null);
  const want = useRef(false); // Chrome ends a session after silence; keep going while the person wants to dictate
  const base = useRef('');
  const finals = useRef('');
  const current = useRef(value);
  current.current = value;

  const stop = () => { want.current = false; rec.current?.stop(); setOn(false); };
  const start = () => {
    if (!SpeechRecognition) { toast?.(t('Speech input is not supported in this browser. Please use Chrome or Edge.'), 'warn'); return; }
    base.current = current.current ? `${current.current.trim()} ` : '';
    finals.current = '';
    const r = new SpeechRecognition();
    r.lang = getLang() === 'de' ? 'de-DE' : 'en-US';
    r.continuous = true;
    r.interimResults = true;
    r.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i += 1) {
        const x = e.results[i];
        if (x.isFinal) finals.current += `${x[0].transcript.trim()} `; else interim += x[0].transcript;
      }
      setValue((base.current + finals.current + interim).replace(/\s+/g, ' ').replace(/^\s+/, ''));
    };
    r.onerror = (e) => {
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') { want.current = false; toast?.(t('Microphone access was blocked. Allow the microphone in your browser and try again.'), 'warn'); }
      else if (e.error === 'audio-capture') { want.current = false; toast?.(t('No microphone found.'), 'warn'); }
      else if (e.error === 'network') { want.current = false; toast?.(t('The speech service could not be reached. Please check your connection.'), 'warn'); }
    };
    r.onend = () => {
      if (want.current) { base.current += finals.current; finals.current = ''; try { r.start(); return; } catch { /* already running */ } }
      setOn(false);
    };
    rec.current = r; want.current = true;
    try { r.start(); setSecs(0); setOn(true); } catch { want.current = false; }
  };
  useEffect(() => {
    if (!on) return undefined;
    const i = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(i);
  }, [on]);
  useEffect(() => () => { want.current = false; rec.current?.abort?.(); }, []);
  return { on, secs, start, stop };
}

/**
 * scopes: [{ key, label, disabled? }]   target: what the change applies to, in words
 * thread / busy: from useThread and the caller   onSend(text): the caller does the work and updates the thread
 * restore: { label, onUndo } an earlier AI change that can still be undone (kept by the backend)
 */
export default function AskAI({ scopes, scope, onScope, target, thread, busy, disabled, disabledNote, placeholder, onSend, toast, restore }) {
  const [text, setText] = useState('');
  const dict = useDictation(text, setText, toast);
  const box = useRef(null);
  const list = useRef(null);
  const canSend = !disabled && !busy && text.trim().length > 2;
  const lastUndo = [...thread].reverse().find((m) => m.undo)?.id;

  useEffect(() => { const el = list.current; if (el) el.scrollTop = el.scrollHeight; }, [thread]);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  }, [text]);

  const send = () => {
    if (!canSend) return;
    if (dict.on) dict.stop();
    const q = text.trim();
    setText('');
    onSend(q);
  };
  const time = `${String(Math.floor(dict.secs / 60)).padStart(2, '0')}:${String(dict.secs % 60).padStart(2, '0')}`;

  return (
    <section className="card pad ask-card" aria-label={t('Ask AI')}>
      <div className="ask-top">
        <h2><Sparkles size={16} /> {t('Ask AI')}</h2>
        <p>{t('Make your final edits here. Type or speak, as you would tell a colleague.')}</p>
      </div>

      <div className="ask-scope">
        <div className="seg sm" role="radiogroup" aria-label={t('What should AI change?')}>
          {scopes.map((s) => (
            <button key={s.key} type="button" role="radio" aria-checked={scope === s.key} className={scope === s.key ? 'on' : ''} disabled={s.disabled} onClick={() => onScope(s.key)}>{s.label}</button>
          ))}
        </div>
        <p className="ask-target">{t('Applies to')}: <strong>{target}</strong></p>
      </div>

      {thread.length > 0 && (
        <div className="ask-thread" ref={list} role="log" aria-live="polite" aria-label={t('Conversation with Ask AI')}>
          {thread.map((m) => (
            <Fragment key={m.id}>
              <div className="msg user"><span>{m.text}</span>{m.tag && <small>{m.tag}</small>}</div>
              <div className={`msg ai${m.tone === 'warn' ? ' warn' : ''}`}>
                {m.pending ? <span className="typing" aria-label={t('Working…')}><i /><i /><i /></span> : (
                  <>
                    <p>{m.reply}</p>
                    {m.notes?.map((n, i) => <p key={i} className="note">{n}</p>)}
                    {m.undone ? <small className="note">{t('Undone.')}</small> : m.undo && m.id === lastUndo && (
                      <button type="button" className="textlink" disabled={!!busy} onClick={m.undo}><Undo2 size={12} /> {t('Undo')}</button>
                    )}
                  </>
                )}
              </div>
            </Fragment>
          ))}
        </div>
      )}
      {restore && (
        <p className="ask-restore"><Undo2 size={13} /> {t('Undo the last AI change')}: “{restore.label}” <button type="button" className="textlink" disabled={disabled || !!busy} onClick={restore.onUndo}>{t('Undo')}</button></p>
      )}

      <div className={`ask-box${dict.on ? ' rec' : ''}${disabled ? ' off' : ''}`}>
        <textarea
          ref={box} rows={2} value={text} disabled={disabled} placeholder={placeholder} aria-label={t('Ask AI')}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }}
        />
        <div className="ask-bar">
          <button type="button" className={`ask-mic${dict.on ? ' on' : ''}`} disabled={disabled} aria-pressed={dict.on} onClick={dict.on ? dict.stop : dict.start}>
            <Mic size={16} /><span>{dict.on ? t('Listening… {time}', { time }) : t('Speak')}</span>
          </button>
          <span className="grow" />
          {text.trim() && !dict.on && <span className="ask-hint">{t('Enter to send')}</span>}
          <button type="button" className="round solid sm" aria-label={t('Send')} disabled={!canSend} onClick={send}><Send size={15} /></button>
        </div>
      </div>
      {disabledNote && <p className="ask-note">{disabledNote}</p>}
    </section>
  );
}
