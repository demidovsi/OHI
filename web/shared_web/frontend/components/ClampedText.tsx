import { useEffect, useRef, useState } from 'react'
import Box from '@mui/material/Box'
import Link from '@mui/material/Link'
import { useT } from '@app/i18n'

// Длинный текст ячейки таблицы (Log, колонка Message): не больше `lines` строк (по умолчанию 3, с учётом переносов
// строк и переноса по ширине колонки); если текст не помещается — ссылка «Показать весь текст» / «Скрыть текст».
// Ссылка появляется только у обрезанных текстов: наличие обрезки определяется по высоте (и при смене ширины колонки).

interface Props {
  text: string
  lines?: number
}

export default function ClampedText({ text, lines = 3 }: Props) {
  const t = useT()
  const ref = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
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

  return (
    <>
      <Box
        ref={ref}
        sx={
          open
            ? { whiteSpace: 'pre-wrap', wordBreak: 'break-word' }
            : {
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                display: '-webkit-box',
                WebkitBoxOrient: 'vertical',
                WebkitLineClamp: lines,
                overflow: 'hidden',
              }
        }
      >
        {text}
      </Box>
      {(clipped || open) && (
        <Link component="button" type="button" underline="hover" onClick={() => setOpen((v) => !v)} sx={{ fontSize: 12, mt: 0.25 }}>
          {open ? t('Скрыть текст') : t('Показать весь текст')}
        </Link>
      )}
    </>
  )
}
