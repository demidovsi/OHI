// Форматирование времени лога как у flask-moment в старом UI:
// строка ISO без зоны трактуется как UTC и выводится в локальном времени
// браузера по формату par.format_dt ('HH:mm:ss' | 'HH:mm:ss D.M.Y').
export function formatLogTime(iso: string | null | undefined, formatDt: string): string {
  if (!iso) return ''
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso)
  const d = new Date(hasZone ? iso : iso + 'Z')
  if (Number.isNaN(d.getTime())) return iso
  const p2 = (n: number) => String(n).padStart(2, '0')
  const time = `${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`
  if (formatDt.includes('D')) return `${time} ${d.getDate()}.${d.getMonth() + 1}.${d.getFullYear()}`
  return time
}
