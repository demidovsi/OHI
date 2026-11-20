import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import Box from '@mui/material/Box'
import Dialog from '@mui/material/Dialog'
import IconButton from '@mui/material/IconButton'
import { alpha, lighten } from '@mui/material/styles'
import CloseIcon from '@mui/icons-material/Close'
import { useT } from '../i18n'

// Окно-модалка сайта: рамка, в тёмной теме фон чуть светлее страницы, окно перетаскивается за заголовок,
// размер меняется за правый нижний угол, закрывается только крестиком (не по Esc и не по клику на затемнение).
// Положение и размер запоминаются между открытиями.
//
// Геометрия задаётся атрибутом style, а не sx: RTL-плагин Emotion в интерфейсе на иврите зеркалит left/right в sx,
// а окно и его угол изменения размера должны оставаться там, где их оставил пользователь.

interface Geometry {
  x: number
  y: number
  w: number
  h: number
}

const MIN_W = 360
const MIN_H = 220
const KEEP_VISIBLE = 80 // сколько пикселей заголовка должно оставаться на экране при перетаскивании

let lastGeometry: Geometry | null = null

function initialGeometry(): Geometry {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const w = Math.min(1200, Math.round(vw * 0.8))
  const h = Math.round(vh * 0.82)
  return { w, h, x: Math.round((vw - w) / 2), y: Math.round((vh - h) / 2) }
}

function clamp(g: Geometry): Geometry {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const w = Math.max(MIN_W, Math.min(g.w, vw))
  const h = Math.max(MIN_H, Math.min(g.h, vh))
  const x = Math.max(KEEP_VISIBLE - w, Math.min(g.x, vw - KEEP_VISIBLE))
  const y = Math.max(0, Math.min(g.y, vh - 40))
  return { x, y, w, h }
}

interface Props {
  open: boolean
  /** Вызывается только по крестику. */
  onClose: () => void
  title: ReactNode
  /** Справа от названия в заголовке (например, длина текста и число строк). */
  info?: ReactNode
  /** Без затемнения и блокировки: форма позади остаётся доступной (карточка поверх формы, из которой открыта). */
  nonModal?: boolean
  /** Окно поверх другого окна: открывается со сдвигом вниз и вправо и не делит с ним запомненное положение. */
  cascade?: boolean
  /** Имя для запоминания положения и размера окна между открытиями и сеансами (localStorage); без него окно делит общее положение. */
  storageKey?: string
  children: ReactNode
}

const STORE = 'ohi_win_'

function readSaved(key?: string): Geometry | null {
  if (!key) return null
  try {
    const g = JSON.parse(localStorage.getItem(STORE + key) ?? 'null')
    return g && [g.x, g.y, g.w, g.h].every((v) => Number.isFinite(v)) ? g : null
  } catch {
    return null
  }
}

export default function ModalWindow({ open, onClose, title, info, nonModal, cascade, storageKey, children }: Props) {
  const t = useT()
  const start = (): Geometry => {
    const saved = readSaved(storageKey)
    if (saved) return clamp(saved)
    if (!cascade) return clamp(lastGeometry ?? initialGeometry())
    const g = lastGeometry ?? initialGeometry()
    return clamp({ ...g, x: g.x + 36, y: g.y + 36 })
  }
  const [geo, setGeo] = useState<Geometry>(start)
  const geoRef = useRef(geo)
  geoRef.current = geo
  const gesture = useRef<{ kind: 'move' | 'resize'; px: number; py: number; start: Geometry } | null>(null)

  useEffect(() => {
    if (open) setGeo(start())
  }, [open])
  useEffect(() => {
    const onResize = () => setGeo((g) => clamp(g))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const begin = (kind: 'move' | 'resize') => (e: ReactPointerEvent<HTMLElement>) => {
    if (e.button !== 0) return
    e.currentTarget.setPointerCapture(e.pointerId)
    gesture.current = { kind, px: e.clientX, py: e.clientY, start: geoRef.current }
    e.preventDefault()
  }
  const move = (e: ReactPointerEvent<HTMLElement>) => {
    const gs = gesture.current
    if (!gs) return
    const dx = e.clientX - gs.px
    const dy = e.clientY - gs.py
    setGeo(
      clamp(
        gs.kind === 'move'
          ? { ...gs.start, x: gs.start.x + dx, y: gs.start.y + dy }
          : { ...gs.start, w: gs.start.w + dx, h: gs.start.h + dy },
      ),
    )
  }
  const end = (e: ReactPointerEvent<HTMLElement>) => {
    if (!gesture.current) return
    gesture.current = null
    e.currentTarget.releasePointerCapture(e.pointerId)
    if (storageKey) {
      try {
        localStorage.setItem(STORE + storageKey, JSON.stringify(geoRef.current))
      } catch {
        /* хранилище недоступно: положение запомнится только до закрытия страницы */
      }
    } else if (!cascade) lastGeometry = geoRef.current
  }

  return (
    <Dialog
      open={open}
      onClose={() => {
        /* закрытие только крестиком: клик по затемнению и Esc игнорируются */
      }}
      maxWidth={false}
      {...(nonModal
        ? {
            hideBackdrop: true,
            disableEnforceFocus: true,
            disableAutoFocus: true,
            disableScrollLock: true,
            // оболочка окна пропускает щелчки к форме позади; ловит их только само окно
            sx: { pointerEvents: 'none', '& .MuiDialog-container': { pointerEvents: 'none' } },
          }
        : {})}
      slotProps={{
        paper: {
          style: { position: 'fixed', margin: 0, left: geo.x, top: geo.y, width: geo.w, height: geo.h, maxWidth: 'none', maxHeight: 'none' },
          sx: (theme) => ({
            pointerEvents: 'auto',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            backgroundImage: 'none',
            border: `2px solid ${alpha(theme.palette.primary.main, 0.75)}`,
            bgcolor: theme.palette.mode === 'dark' ? lighten(theme.palette.background.paper, 0.08) : theme.palette.background.paper,
          }),
        },
      }}
    >
      <Box
        onPointerDown={begin('move')}
        onPointerMove={move}
        onPointerUp={end}
        onPointerCancel={end}
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          px: 1.5,
          py: 0.5,
          flexShrink: 0,
          cursor: 'move',
          userSelect: 'none',
          touchAction: 'none',
          borderBottom: 1,
          borderColor: 'divider',
        }}
      >
        <Box sx={{ flex: '1 1 auto', minWidth: 0, fontSize: 14, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {title}
        </Box>
        {info && <Box sx={{ flexShrink: 0, fontSize: 13, color: 'text.secondary', whiteSpace: 'nowrap' }}>{info}</Box>}
        <IconButton size="small" title={t('Закрыть')} onPointerDown={(e) => e.stopPropagation()} onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </Box>
      <Box sx={{ flex: '1 1 0', minHeight: 0, display: 'flex', flexDirection: 'column', p: 1.5 }}>{children}</Box>
      <div
        onPointerDown={begin('resize')}
        onPointerMove={move}
        onPointerUp={end}
        onPointerCancel={end}
        title={t('Потяните, чтобы изменить размер')}
        style={{ position: 'absolute', right: 0, bottom: 0, width: 18, height: 18, cursor: 'nwse-resize', touchAction: 'none' }}
      >
        <svg width="18" height="18" viewBox="0 0 18 18" style={{ display: 'block', opacity: 0.55 }}>
          <path d="M16 6 6 16M16 11 11 16M16 15 15 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" fill="none" />
        </svg>
      </div>
    </Dialog>
  )
}
