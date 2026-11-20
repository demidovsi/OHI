import { useEffect, useRef, useState } from 'react'
import Box from '@mui/material/Box'
import Link from '@mui/material/Link'
import type { SxProps, Theme } from '@mui/material/styles'
import { useT } from '@app/i18n'

// Длинный текст ячейки таблицы (Log, колонка Message): не больше `lines` строк (по умолчанию 4, с учётом переносов
// строк и переноса по ширине колонки); если текст не помещается — ссылка «Показать весь текст» под ним, а у раскрытого
// текста «Скрыть текст» — и в самом начале, и в конце (не нужно возвращаться наверх длинного текста). Обрезка определяется по высоте
// (и при смене ширины колонки).

interface Props {
  text: string
  lines?: number
  /** Раскрытое состояние снаружи (страница помнит раскрытые записи при обновлении таблицы); без него — своё. */
  open?: boolean
  onToggle?: () => void
  /** Дополнительные стили самого текста (цвет, жирность и т. п.); ссылки «Показать»/«Скрыть» они не затрагивают. */
  textSx?: SxProps<Theme>
}

export default function ClampedText({ text, lines = 4, open: openProp, onToggle, textSx }: Props) {
  const t = useT()
  const ref = useRef<HTMLDivElement>(null)
  const [openOwn, setOpenOwn] = useState(false)
  const open = openProp ?? openOwn
  const toggleOpen = onToggle ?? (() => setOpenOwn((v) => !v))
  const [clipped, setClipped] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el || open) return // раскрытый текст не измеряем: ссылка «Скрыть» остаётся
    const check = () => setClipped(el.scrollHeight > el.clientHeight + 1)
    check()
    const ro = new ResizeObserver(check)
    ro.observe(el)
    return () => ro.disconnect()
  }, [text, lines, open])

  const toggle = (label: string, tip: string) => (
    <Link component="button" type="button" underline="hover" onClick={toggleOpen} title={tip} sx={{ fontSize: 12, display: 'block' }}>
      {label}
    </Link>
  )

  return (
    <>
      {open && toggle(t('Скрыть текст'), t('Свернуть текст до нескольких строк'))}
      <Box
        ref={ref}
        sx={[
          open
            ? { whiteSpace: 'pre-wrap', wordBreak: 'break-word' }
            : {
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                display: '-webkit-box',
                WebkitBoxOrient: 'vertical',
                WebkitLineClamp: lines,
                overflow: 'hidden',
              },
          ...(Array.isArray(textSx) ? textSx : textSx ? [textSx] : []),
        ]}
      >
        {text}
      </Box>
      {open && toggle(t('Скрыть текст'), t('Свернуть текст до нескольких строк'))}
      {!open && clipped && toggle(t('Показать весь текст'), t('Развернуть: показать весь текст целиком'))}
    </>
  )
}
