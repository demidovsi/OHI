import { useCallback, useEffect, useRef, useState } from 'react'
import type { MouseEvent as ReactMouseEvent, ReactNode } from 'react'
import Box from '@mui/material/Box'

// Ширины колонок таблицы, меняемые мышью и запоминаемые в localStorage (у каждого сайта своё хранилище — свой origin).
// Таблица должна иметь tableLayout: 'fixed'; ширины колонок берутся из <ColGroupWidths/>, ручки — <ResizeHandle/> внутри ячеек заголовка.

const MIN_WIDTH = 50

export type ColumnWidths = Record<string, number>

function load(storageKey: string): ColumnWidths {
  try {
    const raw = JSON.parse(localStorage.getItem(storageKey) ?? '{}')
    if (!raw || typeof raw !== 'object') return {}
    return Object.fromEntries(Object.entries(raw).filter(([, v]) => typeof v === 'number' && v >= MIN_WIDTH)) as ColumnWidths
  } catch {
    return {}
  }
}

function save(storageKey: string, widths: ColumnWidths) {
  try {
    if (Object.keys(widths).length) localStorage.setItem(storageKey, JSON.stringify(widths))
    else localStorage.removeItem(storageKey)
  } catch {
    /* localStorage недоступен — ширины не запоминаются */
  }
}

/** Ширины колонок: defaults — ширины по умолчанию (px), меняются мышью; storageKey — ключ запоминания. */
export function useColumnWidths(storageKey: string, defaults: ColumnWidths) {
  const [custom, setCustom] = useState<ColumnWidths>(() => load(storageKey))
  const customRef = useRef(custom)
  customRef.current = custom

  const width = (key: string): number => custom[key] ?? defaults[key]

  const set = useCallback(
    (key: string, w: number, persist: boolean) => {
      const next = { ...customRef.current, [key]: Math.max(MIN_WIDTH, Math.round(w)) }
      customRef.current = next
      setCustom(next)
      if (persist) save(storageKey, next)
    },
    [storageKey],
  )

  const reset = useCallback(
    (key: string) => {
      const { [key]: _drop, ...rest } = customRef.current
      customRef.current = rest
      setCustom(rest)
      save(storageKey, rest)
    },
    [storageKey],
  )

  return { width, set, reset, custom }
}

/** Ручка на правой границе ячейки заголовка: тянуть — менять ширину, двойной клик — вернуть ширину по умолчанию. */
export function ResizeHandle({ colKey, widths, title }: { colKey: string; widths: ReturnType<typeof useColumnWidths>; title?: ReactNode }) {
  const [dragging, setDragging] = useState(false)
  const start = useRef<{ x: number; w: number } | null>(null)
  const { set, reset } = widths
  const current = widths.width(colKey)
  const currentRef = useRef(current)
  currentRef.current = current

  useEffect(() => {
    if (!dragging) return
    const onMove = (e: MouseEvent) => {
      if (start.current) set(colKey, start.current.w + e.clientX - start.current.x, false)
    }
    const onUp = () => {
      set(colKey, currentRef.current, true)
      start.current = null
      setDragging(false)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    const prevSelect = document.body.style.userSelect
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      document.body.style.userSelect = prevSelect
      document.body.style.cursor = ''
    }
  }, [dragging, colKey, set])

  const onDown = (e: ReactMouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    start.current = { x: e.clientX, w: currentRef.current }
    setDragging(true)
  }

  return (
    <Box
      role="separator"
      aria-orientation="vertical"
      title={typeof title === 'string' ? title : undefined}
      onMouseDown={onDown}
      onClick={(e) => e.stopPropagation()}
      onDoubleClick={() => reset(colKey)}
      sx={{
        position: 'absolute',
        top: 0,
        right: 0,
        bottom: 0,
        width: 8,
        cursor: 'col-resize',
        zIndex: 1,
        '&::after': {
          content: '""',
          position: 'absolute',
          top: 4,
          bottom: 4,
          right: 3,
          width: 2,
          borderRadius: 1,
          bgcolor: dragging ? 'primary.main' : 'divider',
        },
        '&:hover::after': { bgcolor: 'primary.main' },
      }}
    />
  )
}
