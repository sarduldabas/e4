import { t } from '../i18n.js';
import { useState } from 'react';
import { ArrowUp, Mic, CalendarDays, ArrowRight } from 'lucide-react';
import { COMMITTEES, REPORTS, daysUntil, fmtDate, USER } from '../data.js';
import { Avatars } from './ui.jsx';

const STATUS_CLASS = { Draft: 'draft', Presented: 'presented', Decided: 'decided' };

export default function Home({ onNew, onOpen, draft, onResume }) {
  const [text, setText] = useState('');
  const submit = (e) => { e?.preventDefault(); onNew({ text: text.trim() }); };

  return (
    <main className="home">
      <section className="hero">
        <p className="eyebrow">{t('Good evening, {name}', { name: USER.first })}</p>
        <h1 className="display xl">
          {t("What are you")}<br />{t("presenting")} <em>{t("next?")}</em>
        </h1>
        <p className="lede">{t("Say it the way you would to a colleague. I will collect the material, check the numbers and build the slides. You decide at every step.")}</p>

        <form className="hero-input" onSubmit={submit}>
          <input
            id="hero-text" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off"
            placeholder={t("For example: FAKOM on 3 December, dual sourcing for battery cells")}
            aria-label={t("Describe your next committee report")}
          />
          <button type="button" className="round ghost" onClick={() => onNew({ text: '', autoVoice: true })} aria-label={t("Start by speaking")} title={t("Start by speaking")}><Mic size={20} /></button>
          <button type="submit" className="round solid" aria-label={t("Start report")}><ArrowUp size={20} /></button>
        </form>
      </section>

      <section className="home-section">
        <div className="sec-head"><h2>{t("Upcoming committees")}</h2><span className="muted">{t("Synced from your calendar")}</span></div>
        <div className="cmt-grid">
          {COMMITTEES.map((c) => {
            const d = daysUntil(c.date);
            return (
              <article key={c.id} className="cmt-card">
                <div className="cmt-top">
                  <span className="cmt-date"><CalendarDays size={15} /> {fmtDate(c.date)}</span>
                  <span className={`due${d < 14 ? ' soon' : ''}`}>{t('in {d} days', { d })}</span>
                </div>
                <h3>{t(c.name)}</h3>
                <p className="muted">{t(c.template)}</p>
                {c.hasReport ? (
                  <button className="link-btn" onClick={() => onOpen(REPORTS[0])}>{t("Continue report v2")} <ArrowRight size={15} /></button>
                ) : (
                  <button className="link-btn" onClick={() => onNew({ committeeId: c.id })}>{t("Start report")} <ArrowRight size={15} /></button>
                )}
              </article>
            );
          })}
        </div>
      </section>

      <section className="home-section">
        <div className="sec-head"><h2>{t("Your reports")}</h2><span className="muted">{t('{n} reports', { n: REPORTS.length + (draft ? 1 : 0) })}</span></div>
        <div className="rep-list">
          {draft && (
            <button className="rep-row" onClick={onResume}>
              <span className="rep-main"><strong>{t(draft.title)}</strong><span className="muted">{t("In progress · continue where you stopped")}</span></span>
              <span className="ver">{t("v1")}</span><span className="status draft">{t("Draft")}</span><span className="muted rep-edit">{t("Just now")}</span><Avatars ids={['kw']} size={26} />
            </button>
          )}
          {REPORTS.map((r) => (
            <button key={r.id} className="rep-row" onClick={() => onOpen(r)}>
              <span className="rep-main">
                <strong>{t(r.title)}</strong>
                <span className="muted">{t(r.committee)} · {fmtDate(r.date)}</span>
              </span>
              <span className="ver">{r.version}</span>
              <span className={`status ${STATUS_CLASS[r.status]}`}>{t(r.status)}</span>
              <span className="muted rep-edit">{t(r.edited)}</span>
              <Avatars ids={r.people} size={26} />
            </button>
          ))}
        </div>
        <p className="foot-note">{t("Demo data. All reports open the same sample content.")}</p>
      </section>
    </main>
  );
}
