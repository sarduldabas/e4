import { t } from '../i18n.js';
import { useState } from 'react';
import { Check, GitCompare, Lock, Plus, Link2, Lightbulb, X, FilePlus2, Eye } from 'lucide-react';
import { VERSION_HISTORY, VERSION_DIFF, PEOPLE, DESIGN_NOTES } from '../data.js';
import { Avatar, Drawer, Modal } from './ui.jsx';

export function VersionsDrawer({ ws, onClose, toast }) {
  const [compare, setCompare] = useState(false);
  const [composing, setComposing] = useState(false);
  const [minutes, setMinutes] = useState('');
  const [plan, setPlan] = useState(false);

  return (
    <Drawer title={t("Versions")} onClose={onClose} width={480}>
      <section className="ver-card current">
        <div className="ver-top"><span className="ver-badge">{ws.version}</span><strong>{t("Current draft")}</strong><span className="pill warn">{t("Draft")}</span></div>
        <p className="muted small">{ws.sample ? `Katrin Weber · ${t('autosaved today, 23:41')}` : t('Autosaved just now')}</p>
        {ws.sample && <p className="small">{t("Addresses the three points FAKOM raised on 05.11.2026.")}</p>}
        {ws.sample && <button className="btn sm" onClick={() => setCompare((v) => !v)}><GitCompare size={14} /> {compare ? t('Hide comparison') : t('Compare with v1')}</button>}
        {compare && (
          <ul className="diff">
            {VERSION_DIFF.map((d) => (
              <li key={d.section}>
                <div><strong>{t(d.section)}</strong><span className={`pill ${d.kind === 'Added' ? 'good' : 'info'}`}>{t(d.kind)}</span></div>
                <p className="before"><span>{t("v1")}</span>{t(d.before)}</p>
                <p className="after"><span>{t("v2")}</span>{t(d.after)}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      {ws.sample && VERSION_HISTORY.map((v) => (
        <section key={v.id} className="ver-card">
          <div className="ver-top"><span className="ver-badge">{v.id}</span><strong>{t('Presented to {committee}', { committee: v.committee })}</strong><span className="pill info"><Lock size={11} /> {t("Locked")}</span></div>
          <p className="muted small">{v.date} · {v.by}</p>
          <p className="eyebrow tight mt">{t("Committee feedback")}</p>
          <ul className="fb">
            {v.feedback.map((f) => <li key={f.text}><Check size={14} className="ok" /><span>{t(f.text)}<small>{t('Addressed in v2')} · {t(f.where)}</small></span></li>)}
          </ul>
          <div className="row gap">
            <button className="btn sm" onClick={() => toast(t('Read-only view of v1 (demo)'))}><Eye size={14} /> {t("View v1")}</button>
            <button className="btn quiet sm" onClick={() => toast(t('Restored as a new draft (demo)'))}>{t("Restore as new draft")}</button>
          </div>
        </section>
      ))}

      <section className="ver-card dashed">
        <div className="ver-top"><FilePlus2 size={18} /><strong>{t("Prepare the next version from committee feedback")}</strong></div>
        {!composing ? (
          <>
            <p className="muted small">{t("After the meeting, paste the minutes or your notes. I propose which sections change, and you approve.")}</p>
            <button className="btn sm" onClick={() => setComposing(true)}><Plus size={14} /> {t("Start new version")}</button>
          </>
        ) : (
          <>
            <label className="sr-only" htmlFor="mins">{t("Committee feedback")}</label>
            <textarea id="mins" rows={4} value={minutes} onChange={(e) => setMinutes(e.target.value)} placeholder={t("Paste minutes or notes, for example: ‘Please show the effect of a delayed Supplier B release on the premium.’")} />
            <button className="btn primary sm" disabled={!minutes.trim()} onClick={() => setPlan(true)}>{t("Propose changes")}</button>
            {plan && (
              <ul className="plan">
                <li><b>{t("Options and cost")}</b><span>{t("Add a scenario with delayed release and show the premium impact.")}</span></li>
                <li><b>{t("Timeline and milestones")}</b><span>{t("Add a delay case to the timeline.")}</span></li>
                <li><b>{t("Recommendation and next steps")}</b><span>{t("Review wording after the first two sections.")}</span></li>
                <li className="muted small">{t("Other sections stay unchanged. Nothing starts until you confirm.")}</li>
              </ul>
            )}
          </>
        )}
      </section>
    </Drawer>
  );
}

export function ShareModal({ onClose, toast }) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('Reviewer');
  return (
    <Modal title={t("Share this report")} onClose={onClose} width={520}>
      <div className="inline-add">
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("Add a colleague by name or e-mail")} aria-label={t("Colleague")} />
        <select value={role} onChange={(e) => setRole(e.target.value)} aria-label={t("Role")}><option value="Reviewer">{t("Reviewer")}</option><option value="Editor">{t("Editor")}</option></select>
        <button className="btn primary sm" disabled={!email.trim()} onClick={() => { toast(t('Invitation sent to {email} as {role} (demo)', { email, role: t(role).toLowerCase() })); setEmail(''); }}>{t("Invite")}</button>
      </div>
      <ul className="people">
        {PEOPLE.map((p) => (
          <li key={p.id}>
            <Avatar id={p.id} size={34} ring={false} />
            <span><strong>{p.name}</strong><span className="muted small">{t(p.note)}</span></span>
            <span className="muted small">{t(p.role)}</span>
          </li>
        ))}
      </ul>
      <div className="row gap">
        <button className="btn" onClick={() => toast(t('Review requested from Lena Schulz (demo)'))}>{t("Request review from Lena")}</button>
        <button className="btn quiet" onClick={() => { try { navigator.clipboard.writeText(window.location.href); } catch (e) { /* blocked in sandbox */ } toast(t('Link copied')); }}><Link2 size={15} /> {t("Copy link")}</button>
      </div>
      <p className="muted small">{t("Colleagues see changes live. Comments and edits are tracked per section and per slide.")}</p>
    </Modal>
  );
}

export function NotesPanel({ stageKey, open, setOpen }) {
  const n = DESIGN_NOTES[stageKey];
  return (
    <>
      {!open && (
        <button className="notes-fab" onClick={() => setOpen(true)} aria-label={t("Show design notes")}><Lightbulb size={16} /> {t("Design notes")}</button>
      )}
      {open && n && (
        <aside className="notes-card" aria-label={t("Design notes")}>
          <header><span><Lightbulb size={15} /> {t("Design notes")}</span><button className="iconbtn light sm" onClick={() => setOpen(false)} aria-label={t("Hide design notes")}><X size={15} /></button></header>
          <h3>{t(n.title)}</h3>
          <ul>{n.points.map((p) => <li key={p}>{t(p)}</li>)}</ul>
          {n.beyond && (
            <>
              <p className="notes-k">{t("Beyond a general chat assistant")}</p>
              <ul className="beyond">{n.beyond.map((p) => <li key={p}><Check size={13} /> {t(p)}</li>)}</ul>
            </>
          )}
        </aside>
      )}
    </>
  );
}
