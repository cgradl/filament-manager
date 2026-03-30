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

// If the user has never chosen a language manually, try to inherit from HA
if (!localStorage.getItem(LS_KEY)) {
  fetch('api/settings/ha-locale')
    .then(r => r.json())
    .then(({ language }: { language: string }) => {
      if (language && SUPPORTED.includes(language) && language !== i18n.resolvedLanguage) {
        i18n.changeLanguage(language)
        // Don't persist to localStorage — keep letting HA drive it on each load
        localStorage.removeItem(LS_KEY)
      }
    })
    .catch(() => { /* silently fall back to browser/en */ })
}

export default i18n
