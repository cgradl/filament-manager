import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import en from './locales/en.json'
import de from './locales/de.json'
import es from './locales/es.json'

const SUPPORTED = ['en', 'de', 'es']
const LS_KEY = 'fm_language'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      de: { translation: de },
      es: { translation: es },
    },
    fallbackLng: 'en',
    supportedLngs: SUPPORTED,
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: LS_KEY,
    },
  })

/**
 * Set document.documentElement.lang to the combined locale so that browsers
 * use the correct regional format (e.g. 24 h time) independently of the UI
 * language.  "en" alone maps to "en-US" in Chrome (12 h); pairing it with a
 * 24 h country (e.g. "DE") gives "en-DE" which Chrome treats as 24 h.
 * Falls back to "en-GB" when no country is available (GB uses 24 h).
 */
export function applyDocLang(language: string, country: string) {
  const lang = SUPPORTED.includes(language) ? language : 'en'
  document.documentElement.lang = country ? `${lang}-${country}` : (lang === 'en' ? 'en-GB' : lang)
}

// If the user has never chosen a language manually, try to inherit from HA
if (!localStorage.getItem(LS_KEY)) {
  fetch('api/settings/ha-locale')
    .then(r => r.json())
    .then(({ language, country }: { language: string; country?: string }) => {
      // Set combined locale for regional format (number/time) regardless of language
      applyDocLang(language, country ?? '')
      if (language && SUPPORTED.includes(language) && language !== i18n.resolvedLanguage) {
        i18n.changeLanguage(language)
        // Don't persist to localStorage — keep letting HA drive it on each load
        localStorage.removeItem(LS_KEY)
      }
    })
    .catch(() => { /* silently fall back to browser/en */ })
}

export default i18n
