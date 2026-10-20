// Две панели формы с перетаскиваемым разделителем (сплиттером); размер запоминается в localStorage.
// Повторяет поведение _makeResizable / _makeResizableVertical проекта BTC-5m (static/js/theme.js):
// - первая панель — фиксированный flex-basis в px БЕЗ роста, вторая забирает остаток (flex: 1),
//   поэтому линия двигается 1-в-1 с мышью;
// - захват — полоса 6px, видимая линия 2px (::after), курсор col-resize / row-resize;
// - мышь и касание (touch), во время перетаскивания выделение текста отключено;
// - размер сохраняется при отпускании, ключ storageKey (префикс ohi_split_);
// - на узком экране (< md) сплиттер скрыт, панели идут друг под другом и делят высоту поровну.
import { useEffect, useRef, useState, type ReactNode } from 'react'
import Box from '@mui/material/Box'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import { useT } from '../i18n'

interface Props {
  /** Ключ сохранения размера первой панели (без префикса), например 'votes_deputies'. */
  storageKey: string
  /** Панели; false/null — панели нет, вторая занимает всё место. */
  first: ReactNode
  second: ReactNode
  /** 'row' — панели слева/справа (вертикальная линия), 'column' — сверху/снизу. */
  direction?: 'row' | 'column'
  /** Размер первой панели, пока пользователь его не менял: px или '%'. */
  defaultSize?: number | string
  /** Минимальный размер каждой панели, px. */
  minSize?: number
}

const PREFIX = 'ohi_split_'

function readSaved(key: string): number | null {
  try {
    const v = parseFloat(localStorage.getItem(PREFIX + key) ?? '')
    return v > 0 ? v : null
  } catch {
    return null
  }
}

/** Панель-flex-колонка: внутри неё FILL_SX забирает остаток высоты. */
const PANE = { minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' } as const

export default function SplitPane({ storageKey, first, second, direction = 'row', defaultSize = '50%', minSize = 200 }: Props) {
  const theme = useTheme()
  const t = useT()
  const wide = useMediaQuery(theme.breakpoints.up('md'))
  const dark = theme.palette.mode === 'dark'
  const row = direction === 'row'
  const containerRef = useRef<HTMLDivElement>(null)
  const firstRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState<number | null>(() => readSaved(storageKey))
  const [dragging, setDragging] = useState(false)

  useEffect(() => setSize(readSaved(storageKey)), [storageKey])

  const start = (clientPos: number, touch: boolean) => {
    const el = firstRef.current
    const box = containerRef.current
    if (!el || !box) return
    const startPos = clientPos
    const startSize = row ? el.getBoundingClientRect().width : el.getBoundingClientRect().height
    const total = row ? box.getBoundingClientRect().width : box.getBoundingClientRect().height
    let current = startSize
    const move = (pos: number) => {
      // вторая панель тоже не меньше minSize; 6px — сам разделитель
      // RTL (иврит): первая панель справа — движение вправо её сужает
      const delta = row && theme.direction === 'rtl' ? startPos - pos : pos - startPos
      current = Math.min(Math.max(minSize, startSize + delta), Math.max(minSize, total - minSize - 6))
      setSize(current)
    }
    const onMouseMove = (e: MouseEvent) => move(row ? e.clientX : e.clientY)
    const onTouchMove = (e: TouchEvent) => {
      move(row ? e.touches[0].clientX : e.touches[0].clientY)
      e.preventDefault() // иначе касание прокручивает страницу вместо перетаскивания
    }
    const stop = () => {
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', stop)
      document.removeEventListener('touchmove', onTouchMove)
      document.removeEventListener('touchend', stop)
      document.removeEventListener('touchcancel', stop)
      document.body.style.userSelect = ''
      setDragging(false)
      try {
        localStorage.setItem(PREFIX + storageKey, String(Math.round(current)))
      } catch {
        /* localStorage недоступен — размер не запоминается */
      }
    }
    document.body.style.userSelect = 'none'
    setDragging(true)
    if (touch) {
      document.addEventListener('touchmove', onTouchMove, { passive: false })
      document.addEventListener('touchend', stop)
      document.addEventListener('touchcancel', stop)
    } else {
      document.addEventListener('mousemove', onMouseMove)
      document.addEventListener('mouseup', stop)
    }
  }

  // одной из панелей нет (например, панель только для администратора) — оставшаяся на всё место
  if (!first || !second) {
    return <Box sx={{ ...PANE, flex: '1 1 0' }}>{first || second}</Box>
  }

  if (!wide) {
    return (
      <Box sx={{ flex: '1 1 0', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
        <Box sx={{ ...PANE, flex: '1 1 0' }}>{first}</Box>
        <Box sx={{ ...PANE, flex: '1 1 0' }}>{second}</Box>
      </Box>
    )
  }

  const basis = size != null ? `${size}px` : typeof defaultSize === 'number' ? `${defaultSize}px` : defaultSize
  const line = dragging ? (dark ? '#6b7280' : '#9aa0ad') : dark ? '#3a3f4a' : '#c8cdd6'
  return (
    <Box ref={containerRef} sx={{ flex: '1 1 0', minHeight: 0, minWidth: 0, display: 'flex', flexDirection: row ? 'row' : 'column' }}>
      <Box ref={firstRef} sx={{ ...PANE, flex: `0 1 ${basis}`, [row ? 'minWidth' : 'minHeight']: minSize }}>
        {first}
      </Box>
      <Box
        role="separator"
        aria-orientation={row ? 'vertical' : 'horizontal'}
        onMouseDown={(e) => {
          e.preventDefault()
          start(row ? e.clientX : e.clientY, false)
        }}
        onTouchStart={(e) => start(row ? e.touches[0].clientX : e.touches[0].clientY, true)}
        onDoubleClick={() => {
          // двойной щелчок — вернуть размер по умолчанию
          setSize(null)
          try {
            localStorage.removeItem(PREFIX + storageKey)
          } catch {
            /* ignore */
          }
        }}
        title={t('Перетащите, чтобы изменить размер; двойной щелчок — по умолчанию')}
        sx={{
          flex: '0 0 6px',
          cursor: row ? 'col-resize' : 'row-resize',
          position: 'relative',
          touchAction: 'none',
          '&::after': {
            content: '""',
            position: 'absolute',
            borderRadius: '1px',
            background: line,
            ...(row ? { top: 0, bottom: 0, left: '2px', width: '2px' } : { left: 0, right: 0, top: '2px', height: '2px' }),
          },
          '&:hover::after': { background: dark ? '#6b7280' : '#9aa0ad' },
        }}
      />
      <Box sx={{ ...PANE, flex: '1 1 0', [row ? 'minWidth' : 'minHeight']: minSize }}>{second}</Box>
    </Box>
  )
}
