// Minimal i18n: English strings are the keys, German lives in i18n.de.js.
// A string without a German entry is shown in English, so nothing can break.
// The active language is set once per render by <App/> (see setLang), so components just call t().
import DE from './i18n.de.js';

let LANG = 'de'; // default language: German
export const getLang = () => LANG;
export const setLang = (l) => { LANG = l; };

/** t('Slide {n} of {total}', { n: 2, total: 9 }) */
export function t(s, params) {
  if (s == null) return s;
  let out = s;
  if (LANG === 'de') {
    if (s in DE) out = DE[s];
    else if (typeof window !== 'undefined') (window.__i18nMissing ||= new Set()).add(s); // dev aid: lists strings without a German entry
  }
  if (params) out = out.replace(/\{(\w+)\}/g, (m, k) => (k in params ? params[k] : m));
  return out;
}

/** Numbers: German uses a decimal comma. */
export const num = (n, d = 1) => {
  const s = Number(n).toFixed(d);
  return LANG === 'de' ? s.replace('.', ',') : s;
};
