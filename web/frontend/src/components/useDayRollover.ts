import { useEffect, useRef } from 'react'

/** Локальная дата браузера (ГГГГ-ММ-ДД). */
const localDay = () => {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/**
 * Автообновление текущих суток: когда в локальную полночь наступают следующие сутки, форма переходит на новые текущие
 * сутки (onNewDay — то же, что кнопка «Сегодня»), а не остаётся на вчерашних.
 *
 * active — автообновление включено и показаны текущие сутки; dayKey — показанные сутки (при смене хук настраивается заново).
 * Срабатывает по таймеру на полночь; в неактивной вкладке таймеры откладываются, поэтому смена суток проверяется ещё
 * раз в 30 с и при возврате на вкладку.
 */
export function useDayRollover(active: boolean, dayKey: string | undefined, onNewDay: () => void) {
  const handler = useRef(onNewDay)
  useEffect(() => {
    handler.current = onNewDay
  })

  useEffect(() => {
    if (!active) return
    let day = localDay()
    const fire = () => {
      day = localDay() // следующее срабатывание — только в следующую полночь (если сервер остался на тех же сутках)
      handler.current()
    }
    const check = () => {
      if (localDay() !== day) fire()
    }
    const now = new Date()
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 3).getTime() - now.getTime()
    const timer = setTimeout(check, midnight)
    const iv = setInterval(check, 30 * 1000)
    document.addEventListener('visibilitychange', check)
    return () => {
      clearTimeout(timer)
      clearInterval(iv)
      document.removeEventListener('visibilitychange', check)
    }
  }, [active, dayKey])
}
