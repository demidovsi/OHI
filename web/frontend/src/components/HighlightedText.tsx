import { Fragment, useMemo } from 'react'
import Box from '@mui/material/Box'
import { alpha } from '@mui/material/styles'

// Текст с подсвеченными словами поисковых образов. Слова — как в образах (rss_themes.value, через ';'): ищутся целыми
// словами (границы — не буквы/цифры Unicode: \b в JS работает только для латиницы), без учёта регистра; слово вида
// ^СЛОВО^ — с учётом регистра; слово на иврите — и с приставками ל ב ה ו מ ש כ (как на сервере, common.make_search).

const NOT_LETTER_BEFORE = '(?<![\\p{L}\\p{N}_])'
const NOT_LETTER_AFTER = '(?![\\p{L}\\p{N}_])'
const HEBREW = /[א-ת]/

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** Регулярные выражения поиска: [без учёта регистра, с учётом регистра] (null — слов нет). */
function matchers(words: string[]): [RegExp | null, RegExp | null] {
  const plain: string[] = []
  const exact: string[] = []
  for (const raw of words) {
    let w = raw.trim()
    if (!w) continue
    const caseSensitive = w.startsWith('^') && w.endsWith('^') && w.length > 2
    if (caseSensitive) w = w.slice(1, -1).trim()
    w = w.replace(/^["«»“”]+|["«»“”]+$/g, '').trim() // кавычки вокруг фразы — не часть слова
    if (w.length < 2) continue
    const part = HEBREW.test(w) ? `[ובכלמשה]{0,2}${escapeRe(w)}` : escapeRe(w)
    ;(caseSensitive ? exact : plain).push(part)
  }
  const build = (parts: string[], flags: string) =>
    parts.length ? new RegExp(`${NOT_LETTER_BEFORE}(?:${parts.join('|')})${NOT_LETTER_AFTER}`, flags) : null
  return [build(plain, 'giu'), build(exact, 'gu')]
}

/** Диапазоны [начало, конец) совпадений в тексте, объединённые. */
function ranges(text: string, words: string[]): Array<[number, number]> {
  const found: Array<[number, number]> = []
  for (const re of matchers(words)) {
    if (!re) continue
    for (const m of text.matchAll(re)) {
      if (m[0].length) found.push([m.index ?? 0, (m.index ?? 0) + m[0].length])
    }
  }
  found.sort((a, b) => a[0] - b[0] || b[1] - a[1])
  const merged: Array<[number, number]> = []
  for (const r of found) {
    const last = merged[merged.length - 1]
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1])
    else merged.push([r[0], r[1]])
  }
  return merged
}

interface Props {
  text: string
  words: string[]
}

/** Текст с выделенными (<mark>) словами образов; переносы строк сохраняются стилем родителя (white-space: pre-wrap). */
export default function HighlightedText({ text, words }: Props) {
  const parts = useMemo(() => {
    const rs = text && words.length ? ranges(text, words) : []
    const out: Array<{ s: string; hit: boolean }> = []
    let pos = 0
    for (const [a, b] of rs) {
      if (a > pos) out.push({ s: text.slice(pos, a), hit: false })
      out.push({ s: text.slice(a, b), hit: true })
      pos = b
    }
    if (pos < text.length) out.push({ s: text.slice(pos), hit: false })
    return out
  }, [text, words])

  return (
    <>
      {parts.map((p, i) =>
        p.hit ? (
          <Box
            key={i}
            component="mark"
            sx={(theme) => ({ bgcolor: alpha(theme.palette.warning.main, 0.4), color: 'inherit', borderRadius: '3px', px: '1px' })}
          >
            {p.s}
          </Box>
        ) : (
          <Fragment key={i}>{p.s}</Fragment>
        ),
      )}
    </>
  )
}
