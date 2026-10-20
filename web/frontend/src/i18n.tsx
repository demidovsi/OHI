import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { EN } from './locales/en'
import { HE } from './locales/he'

// Интернационализация. Ключ — исходная русская строка; словари EN/HE дают перевод.
// Языки — те же, что в старом UI (language.languages / config.languages): ru, en, he.
// Нет перевода → показываем русский текст (интерфейс не ломается).
//   const t = useT()
//   t('Все законопроекты')            → 'All bills' в EN
//   t('Строк: {n}', { n: 5 })         → подстановка {плейсхолдеров}
// Данные из БД (статусы, исходы, виды инициаторов) переводятся тем же словарём:
//   t(row.outcome) — для известных значений есть переводы, остальное как есть.

export type Lang = 'ru' | 'en' | 'he'
export const LANG_KEY = 'ohi_lang'
export const LANGS: { key: Lang; name: string }[] = [
  { key: 'ru', name: 'Russian' },
  { key: 'en', name: 'English' },
  { key: 'he', name: 'Hebrew' },
]
export function isLang(v: unknown): v is Lang {
  return v === 'ru' || v === 'en' || v === 'he'
}

interface I18nValue {
  lang: Lang
  setLang: (l: Lang) => void
  t: (s: string, vars?: Record<string, string | number>) => string
}

const I18nContext = createContext<I18nValue | null>(null)

export function readLang(): Lang {
  try {
    const v = localStorage.getItem(LANG_KEY)
    if (isLang(v)) return v
  } catch {
    /* ignore */
  }
  return 'ru'
}

function interpolate(s: string, vars?: Record<string, string | number>): string {
  if (!vars) return s
  return s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m))
}

export function translate(lang: Lang, s: string, vars?: Record<string, string | number>): string {
  if (lang !== 'ru') {
    const hit = (lang === 'he' ? HE : EN)[s]
    if (hit !== undefined) return interpolate(hit, vars)
    if (import.meta.env.DEV && s && /[А-Яа-яЁё]/.test(s)) missing.add(s)
  }
  return interpolate(s, vars)
}

/** В dev-режиме собираем непереведённые строки: window.__i18nMissing() */
const missing = new Set<string>()
if (import.meta.env.DEV) {
  ;(window as unknown as { __i18nMissing: () => string[] }).__i18nMissing = () => [...missing].sort()
}

export function I18nProvider({ children, onChange }: { children: ReactNode; onChange?: (l: Lang) => void }) {
  const [lang, setLangState] = useState<Lang>(readLang)
  const setLang = useCallback(
    (l: Lang) => {
      setLangState(l)
      try {
        localStorage.setItem(LANG_KEY, l)
      } catch {
        /* ignore */
      }
      onChange?.(l)
    },
    [onChange],
  )
  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = lang === 'he' ? 'rtl' : 'ltr' // иврит — справа налево
  }, [lang])
  const value = useMemo<I18nValue>(() => ({ lang, setLang, t: (s, vars) => translate(lang, s, vars) }), [lang, setLang])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n outside I18nProvider')
  return ctx
}

export function useT() {
  return useI18n().t
}

/** Локаль для toLocaleString / дат. */
export function useLocale(): string {
  const lang = useI18n().lang
  return lang === 'en' ? 'en-GB' : lang === 'he' ? 'he-IL' : 'ru-RU'
}
