import { Fragment, useCallback, useMemo, useState, type ReactNode } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import IconButton from '@mui/material/IconButton'
import Paper from '@mui/material/Paper'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TableSortLabel from '@mui/material/TableSortLabel'
import TextField from '@mui/material/TextField'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useTheme } from '@mui/material/styles'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import UnfoldLessIcon from '@mui/icons-material/UnfoldLess'
import UnfoldMoreIcon from '@mui/icons-material/UnfoldMore'
import { ArcElement, BarElement, CategoryScale, Chart as ChartJS, Legend, LinearScale, Tooltip as ChartTooltip, type TooltipItem } from 'chart.js'
import { Bar, Pie } from 'react-chartjs-2'
import { useForm } from '@app/useForm'
import type { FormFields } from '@app/api'
import FlashMessages from '@app/components/FlashMessages'
import { useLocale, useT } from '@app/i18n'
import { FILL_SX, PAGE_SX } from '@app/components/layout'
import LoadingBar from '@app/components/LoadingBar'
import SplitPane from '@app/components/SplitPane'
import FitChartBox from '@shared-web/components/FitChartBox'
import DateField from '@shared-web/components/DateField'
import TablePager from '@shared-web/components/TablePager'
import { ResizeHandle, useColumnWidths } from '@shared-web/components/columnResize'

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, ChartTooltip, Legend)

// Страница «Гости сайта» — одна на все сайты, вид и данные как у формы guests сайта GEO и «Посетители схемы» modeler_web:
// дерево «дата → страна, город → IP → форма» (порядок уровней переключается), плашки итогов за период, диаграмма
// (страны / формы / пользователи) и таблицы «Пользователи / Формы / Места». Сервер — shared_web/guests.py.

interface VisitRow {
  d: string
  country: string
  city: string
  ip: string
  usr: string
  page: string
  n: number | string
  first_dt: string
  last_dt: string
}
interface UserRow {
  id: number
  sh_name: string
  count: number | null
  first_date: string | null
  last_date: string | null
}

/** Узел дерева: число обращений и время последнего (UTC); листья — формы. */
interface Node {
  key: string
  label: string
  isDate?: boolean
  user?: string
  n: number
  last: string
  kids: Node[]
}

/** Строка таблицы «Пользователи»: итоги за всё время и за выбранный период. */
interface StatUser {
  name: string
  count: number | null
  first: string | null
  last: string | null
  n: number | null
  ips: number | null
  lastIp: string
  place: string
}
interface StatKey {
  key: string
  n: number
  ips: number
  users: number
}

const DAY_MS = 86400000
const PALETTE = ['#4e73df', '#1cc88a', '#e74a3b', '#f6c23e', '#36b9cc', '#858796', '#fd7e14', '#6f42c1', '#20c9a6', '#e83e8c', '#17a2b8', '#28a745', '#dc3545', '#ffc107', '#6c757d']
const HAS_ZONE = /[zZ]|[+-]\d\d:?\d\d$/

// Ширины колонок (px) по умолчанию: колонки таблиц меняются мышью (потянуть границу в шапке; двойной щелчок — по умолчанию)
// и запоминаются в браузере. Ключ колонки — поле сортировки (у дерева — свой ключ).
const COLS_TREE = { tree: 380, n: 110, kids: 100, last: 180 }
const COLS_USERS = { name: 210, count: 90, first: 170, last: 180, n: 110, ips: 70, lastIp: 160, place: 180 }
const COLS_FORMS = { key: 280, n: 110, ips: 70, users: 90 }
const COLS_PLACES = { key: 280, n: 110, ips: 70 }

// Шапка таблицы: границы между ячейками (1px), место справа под ручку изменения ширины, перенос длинных слов по ширине колонки
const TABLE_SX = {
  tableLayout: 'fixed',
  '& .MuiTableCell-root': { overflowWrap: 'anywhere' },
  // position: relative - для ручки изменения ширины; закреплённой (stickyHeader) шапке оставляем sticky, иначе шапка прокручивается
  '& .MuiTableHead-root .MuiTableCell-root:not(.MuiTableCell-stickyHeader)': { position: 'relative' },
  '& .MuiTableHead-root .MuiTableCell-root': { borderRight: 1, borderColor: 'divider', pr: 2.5 },
  '& .MuiTableHead-root .MuiTableCell-root:last-of-type': { borderRight: 0 },
} as const

type Widths = ReturnType<typeof useColumnWidths>

/** Время из базы (UTC, 'YYYY-MM-DD HH:MM:SS') -> время в часовом поясе браузера. */
function local(utc: string | null | undefined, locale: string, withDate = true): string {
  if (!utc) return ''
  const d = new Date(utc.replace(' ', 'T') + (HAS_ZONE.test(utc) ? '' : 'Z'))
  if (Number.isNaN(d.getTime())) return utc
  return withDate ? d.toLocaleString(locale) : d.toLocaleTimeString(locale)
}

/** «3 дня назад» / «вчера» на языке интерфейса по времени сервера (UTC без указания пояса). */
function ago(utc: string | null | undefined, locale: string): string {
  if (!utc) return ''
  const d = new Date(utc.replace(' ', 'T') + (HAS_ZONE.test(utc) ? '' : 'Z'))
  if (Number.isNaN(d.getTime())) return ''
  let rtf: Intl.RelativeTimeFormat
  try {
    rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  } catch {
    return ''
  }
  const sec = (d.getTime() - Date.now()) / 1000
  const abs = Math.abs(sec)
  if (abs < 3600) return rtf.format(Math.round(sec / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(sec / 3600), 'hour')
  if (abs < 86400 * 60) return rtf.format(Math.round(sec / 86400), 'day')
  if (abs < 86400 * 730) return rtf.format(Math.round(sec / (86400 * 30)), 'month')
  return rtf.format(Math.round(sec / (86400 * 365)), 'year')
}

function shiftDay(date: string, days: number): string {
  return new Date(Date.parse(`${date}T12:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10)
}

function todayLocal(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const placeOf = (r: { country: string; city: string }) => [r.country, r.city].filter(Boolean).join(', ') || '—'

/** Строки запроса -> дерево: первые два уровня — дата и место (порядок по переключателю), затем IP и формы. */
function buildTree(rows: VisitRow[], dateFirst: boolean): Node[] {
  const roots: Node[] = []
  const child = (list: Node[], key: string, make: () => Node) => {
    let node = list.find((x) => x.key === key)
    if (!node) {
      node = make()
      list.push(node)
    }
    return node
  }
  const node = (key: string, label: string, isDate: boolean, user?: string): Node => ({ key, label, isDate, user, n: 0, last: '', kids: [] })
  for (const r of rows) {
    const n = Number(r.n) || 0
    const place = placeOf(r)
    const [k1, k2] = dateFirst ? [r.d, place] : [place, r.d]
    const a = child(roots, k1, () => node(k1, k1, dateFirst))
    const b = child(a.kids, `${a.key}|${k2}`, () => node(`${a.key}|${k2}`, k2, !dateFirst))
    const ip = child(b.kids, `${b.key}|${r.ip}|${r.usr}`, () => node(`${b.key}|${r.ip}|${r.usr}`, r.ip, false, r.usr))
    ip.kids.push({ key: `${ip.key}|${r.page}`, label: r.page || '—', n, last: r.last_dt, kids: [] })
    for (const x of [a, b, ip]) {
      x.n += n
      if (r.last_dt > x.last) x.last = r.last_dt
    }
  }
  // даты — от новых к старым, остальное — по убыванию числа обращений
  const sort = (nodes: Node[]) => {
    nodes.sort((x, y) => (x.isDate ? y.label.localeCompare(x.label) : y.n - x.n || x.label.localeCompare(y.label)))
    nodes.forEach((x) => sort(x.kids))
  }
  sort(roots)
  return roots
}

function allKeys(nodes: Node[]): string[] {
  return nodes.flatMap((x) => (x.kids.length ? [x.key, ...allKeys(x.kids)] : []))
}

/** Итоги по ключу (форма, место): обращений, разных IP и разных пользователей. */
function aggregate(rows: VisitRow[], keyOf: (r: VisitRow) => string): StatKey[] {
  const m = new Map<string, { n: number; ips: Set<string>; users: Set<string> }>()
  for (const r of rows) {
    const k = keyOf(r)
    const a = m.get(k) ?? { n: 0, ips: new Set<string>(), users: new Set<string>() }
    a.n += Number(r.n) || 0
    a.ips.add(r.ip)
    if (r.usr) a.users.add(r.usr)
    m.set(k, a)
  }
  return [...m.entries()].map(([key, a]) => ({ key, n: a.n, ips: a.ips.size, users: a.users.size }))
}

// Сортировка таблиц по щелчку на заголовке: по возрастанию, по убыванию, снять; выбор запоминается в браузере.
type SortDir = 'asc' | 'desc'
interface SortState {
  key: string
  dir: SortDir
}

function useColSort(storageKey: string) {
  const name = `sort_${storageKey}`
  const [sort, setSort] = useState<SortState | null>(() => {
    try {
      const v = JSON.parse(localStorage.getItem(name) ?? 'null')
      return v && typeof v.key === 'string' && (v.dir === 'asc' || v.dir === 'desc') ? v : null
    } catch {
      return null
    }
  })
  const toggle = useCallback(
    (key: string) =>
      setSort((prev) => {
        const next: SortState | null = !prev || prev.key !== key ? { key, dir: 'asc' } : prev.dir === 'asc' ? { key, dir: 'desc' } : null
        try {
          if (next) localStorage.setItem(name, JSON.stringify(next))
          else localStorage.removeItem(name)
        } catch {
          /* ignore */
        }
        return next
      }),
    [name],
  )
  return { sort, toggle }
}

const collator = new Intl.Collator(['ru', 'en'], { numeric: true, sensitivity: 'base' })

/** Строки в порядке сортировки: числа сравниваются как числа, пустые значения — в конец при любом направлении. */
function sortRows<T extends object>(rows: T[], sort: SortState | null): T[] {
  if (!sort) return rows
  const get = (r: T) => (r as Record<string, unknown>)[sort.key]
  const empty = (v: unknown) => v === null || v === undefined || v === ''
  const factor = sort.dir === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => {
    const x = get(a)
    const y = get(b)
    if (empty(x) || empty(y)) return empty(x) && empty(y) ? 0 : empty(x) ? 1 : -1
    if (typeof x === 'number' && typeof y === 'number') return (x - y) * factor
    return collator.compare(String(x), String(y)) * factor
  })
}

function SortCell({ field, sort, onSort, widths, help, children }: { field: string; sort: SortState | null; onSort: (key: string) => void; widths: Widths; help?: string; children: ReactNode }) {
  const t = useT()
  const active = sort?.key === field
  return (
    <TableCell title={help} sx={{ textAlign: 'center' }} sortDirection={active ? sort!.dir : false}>
      <TableSortLabel active={active} direction={active ? sort!.dir : 'asc'} onClick={() => onSort(field)}>
        {children}
      </TableSortLabel>
      <ResizeHandle colKey={field} widths={widths} title={t('Потяните, чтобы изменить ширину колонки; двойной клик — ширина по умолчанию')} />
    </TableCell>
  )
}

/** Ячейка шапки без сортировки: с ручкой изменения ширины. */
function HeadCell({ colKey, widths, title, align = 'center', children }: { colKey: string; widths: Widths; title?: string; align?: 'left' | 'center' | 'right'; children: ReactNode }) {
  const t = useT()
  return (
    <TableCell align={align} title={title}>
      {children}
      <ResizeHandle colKey={colKey} widths={widths} title={t('Потяните, чтобы изменить ширину колонки; двойной клик — ширина по умолчанию')} />
    </TableCell>
  )
}

/** colgroup с ширинами колонок и общая ширина таблицы (больше области — горизонтальная прокрутка). */
function Cols({ keys, widths }: { keys: string[]; widths: Widths }) {
  return (
    <colgroup>
      {keys.map((k) => (
        <col key={k} style={{ width: widths.width(k) }} />
      ))}
    </colgroup>
  )
}
const totalWidth = (keys: string[], widths: Widths) => keys.reduce((sum, k) => sum + widths.width(k), 0)

export default function GuestsPage() {
  const t = useT()
  const locale = useLocale()
  const theme = useTheme()
  const { par, messages, loading, error, submit, dismiss } = useForm('guests')
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [order, setOrder] = useState<'date' | 'place'>(() => {
    try {
      return localStorage.getItem('guests_order') === 'place' ? 'place' : 'date'
    } catch {
      return 'date'
    }
  })
  const [chart, setChart] = useState<'places' | 'forms' | 'users'>('places')
  const [tbl, setTbl] = useState<'users' | 'forms' | 'places'>('users')
  const [searchText, setSearchText] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)
  const sortUsers = useColSort('guests_users')
  const sortForms = useColSort('guests_forms')
  const sortPlaces = useColSort('guests_places')
  const wTree = useColumnWidths('guests_cols_tree', COLS_TREE)
  const wUsers = useColumnWidths('guests_cols_users', COLS_USERS)
  const wForms = useColumnWidths('guests_cols_forms', COLS_FORMS)
  const wPlaces = useColumnWidths('guests_cols_places', COLS_PLACES)

  const rows: VisitRow[] = useMemo(() => par?.rows ?? [], [par])
  const users: UserRow[] = useMemo(() => par?.users ?? [], [par])
  const tree = useMemo(() => buildTree(rows, order === 'date'), [rows, order])

  const statForms = useMemo(() => aggregate(rows, (r) => r.page || '—'), [rows])
  const statPlaces = useMemo(() => aggregate(rows, placeOf), [rows])
  const statUsers = useMemo<StatUser[]>(() => {
    const byUser = new Map(aggregate(rows, (r) => r.usr).map((a) => [a.key, a]))
    const lastRow = new Map<string, VisitRow>() // последнее обращение пользователя за период: IP и место
    for (const r of rows) {
      const o = lastRow.get(r.usr)
      if (!o || r.last_dt > o.last_dt) lastRow.set(r.usr, r)
    }
    const list: StatUser[] = users.map((u) => {
      const last = lastRow.get(u.sh_name)
      return {
        name: u.sh_name,
        count: u.count,
        first: u.first_date,
        last: u.last_date,
        n: byUser.get(u.sh_name)?.n ?? null,
        ips: byUser.get(u.sh_name)?.ips ?? null,
        lastIp: last?.ip ?? '',
        place: last ? placeOf(last) : '',
      }
    })
    const anon = byUser.get('') // IP без входа
    if (anon) {
      const last = lastRow.get('')
      list.push({ name: '', count: null, first: null, last: null, n: anon.n, ips: anon.ips, lastIp: last?.ip ?? '', place: last ? placeOf(last) : '' })
    }
    return list
  }, [rows, users])
  const sortedUsers = useMemo(() => sortRows(statUsers, sortUsers.sort), [statUsers, sortUsers.sort])
  const sortedForms = useMemo(() => sortRows(statForms, sortForms.sort), [statForms, sortForms.sort])
  const sortedPlaces = useMemo(() => sortRows(statPlaces, sortPlaces.sort), [statPlaces, sortPlaces.sort])

  if (!par) return error ? <Alert severity="error">{error}</Alert> : <LoadingBar loading />

  const mode: string = par.mode ?? 'day'
  const date: string = par.date ?? todayLocal()
  const search: string = par.search ?? ''
  const fields: FormFields = { mode, date, search }
  const text = searchText ?? search
  const hasUsers = Boolean(par.has_users)
  const visits = rows.reduce((sum, r) => sum + (Number(r.n) || 0), 0)
  const activeIps = new Set(rows.map((r) => r.ip)).size
  const activeUsers = new Set(rows.map((r) => r.usr).filter(Boolean)).size
  const pageTree = tree.slice(page * rowsPerPage, (page + 1) * rowsPerPage)
  // одни сутки — дата раскрыта сразу
  const isOpen = (node: Node, level: number) => open[node.key] ?? (mode === 'day' && level === 0)
  const flip = (node: Node, level: number) => setOpen({ ...open, [node.key]: !isOpen(node, level) })
  const setAll = (value: boolean) => setOpen(Object.fromEntries(allKeys(tree).map((k) => [k, value])))
  const run = (extra: FormFields) => {
    setPage(0)
    submit({ ...fields, ...extra })
  }

  const renderNode = (node: Node, level: number) => {
    const has = node.kids.length > 0
    const expanded = has && isOpen(node, level)
    return (
      <Fragment key={node.key}>
        <TableRow hover sx={level === 0 ? { bgcolor: 'action.hover' } : undefined}>
          <TableCell sx={{ pl: 1 + level * 2.5, whiteSpace: 'nowrap' }}>
            {has ? (
              <IconButton size="small" color="primary" onClick={() => flip(node, level)} sx={{ fontSize: 12, width: 26, mr: 0.5 }}>
                {expanded ? '▼' : '▶'}
              </IconButton>
            ) : (
              <Box component="span" sx={{ display: 'inline-block', width: 30 }} />
            )}
            <Box component="span" sx={{ fontWeight: level === 0 ? 700 : undefined, fontFamily: level === 2 ? 'monospace' : undefined }}>
              {level === 3 ? t(node.label) : node.label}
            </Box>
            {node.user && <Chip size="small" variant="outlined" color="secondary" label={node.user} title={t('Пользователь, вошедший с этого IP')} sx={{ ml: 1, height: 20 }} />}
          </TableCell>
          <TableCell align="right" sx={{ fontWeight: level < 3 ? 600 : undefined }}>
            {node.n}
          </TableCell>
          <TableCell align="right" sx={{ color: 'text.secondary' }}>
            {has ? node.kids.length : ''}
          </TableCell>
          <TableCell sx={{ whiteSpace: 'nowrap', color: 'text.secondary' }}>{local(node.last, locale, !node.isDate)}</TableCell>
        </TableRow>
        {expanded && node.kids.map((c) => renderNode(c, level + 1))}
      </Fragment>
    )
  }

  const noData = (cols: number) => (
    <TableRow>
      <TableCell colSpan={cols} align="center" sx={{ py: 4, color: 'text.secondary' }}>
        {t('Нет данных')}
      </TableCell>
    </TableRow>
  )

  const treeCard = (
    <Paper variant="outlined" sx={{ flex: '1 1 0', minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <TableContainer sx={{ ...FILL_SX, border: 0 }}>
        <Table size="small" stickyHeader sx={{ ...TABLE_SX, width: totalWidth(Object.keys(COLS_TREE), wTree), minWidth: '100%' }}>
          <Cols keys={Object.keys(COLS_TREE)} widths={wTree} />
          <TableHead>
            <TableRow>
              <HeadCell colKey="tree" widths={wTree} align="left" title={order === 'place' ? t('Страна, город → дата (местная) → IP → форма') : t('Дата (местная) → страна, город → IP → форма')}>
                {order === 'place' ? t('Место / дата / IP / форма') : t('Дата / место / IP / форма')}
              </HeadCell>
              <HeadCell colKey="n" widths={wTree} title={t('Число обращений к формам')}>{t('Обращений')}</HeadCell>
              <HeadCell colKey="kids" widths={wTree} title={t('Количество вложенных элементов следующего уровня')}>{t('Вложено')}</HeadCell>
              <HeadCell colKey="last" widths={wTree} title={t('Время последнего обращения (местное)')}>{t('Последнее')}</HeadCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {pageTree.map((node) => renderNode(node, 0))}
            {tree.length === 0 && !loading && noData(4)}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePager total={tree.length} page={page} rows={rowsPerPage} onPage={setPage} onRows={(r) => { setRowsPerPage(r); setPage(0) }} />
    </Paper>
  )

  // диаграмма: страны (круговая, по числу разных IP) / топ форм / топ пользователей (столбчатая)
  const top = (list: { label: string; value: number }[]) => list.filter((a) => a.value > 0).sort((a, b) => b.value - a.value).slice(0, 15)
  const items =
    chart === 'places'
      ? top(statPlaces.map((a) => ({ label: a.key === '—' ? t('Не определено') : a.key, value: a.ips })))
      : chart === 'forms'
        ? top(statForms.map((a) => ({ label: t(a.key), value: a.n })))
        : top(statUsers.filter((u) => u.name).map((u) => ({ label: u.name, value: u.count ?? 0 })))
  const labels = items.map((i) => i.label)
  const data = items.map((i) => i.value)
  const colors = labels.map((_, i) => PALETTE[i % PALETTE.length])
  const textColor = theme.palette.text.primary
  const rtl = theme.direction === 'rtl'

  const chartCard = (
    <Paper variant="outlined" sx={{ flex: '1 1 0', minHeight: 0, p: 1, display: 'flex', flexDirection: 'column' }}>
      <ToggleButtonGroup exclusive size="small" value={chart} onChange={(_, v) => v && setChart(v)} sx={{ mb: 1, alignSelf: 'flex-start' }}>
        <ToggleButton value="places" title={t('Посетители (разные IP) по странам')}>{t('Страны')}</ToggleButton>
        <ToggleButton value="forms" title={t('Топ форм по числу обращений')}>{t('Формы')}</ToggleButton>
        {hasUsers && <ToggleButton value="users" title={t('Топ пользователей по числу входов')}>{t('Пользователи')}</ToggleButton>}
      </ToggleButtonGroup>
      <FitChartBox>
        {items.length === 0 ? (
          <Typography color="text.secondary" sx={{ p: 2 }}>{t('Нет данных')}</Typography>
        ) : chart === 'places' ? (
          <Pie
            key="pie"
            data={{ labels, datasets: [{ data, backgroundColor: colors, borderColor: theme.palette.background.paper }] }}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                legend: { display: true, position: rtl ? 'left' : 'right', rtl, labels: { color: textColor, font: { size: 10 }, boxWidth: 12 } },
                tooltip: {
                  rtl,
                  callbacks: {
                    label: (c: TooltipItem<'pie'>) => {
                      const total = data.reduce((a, b) => a + b, 0)
                      return `${c.label}: ${c.parsed} (${total ? ((c.parsed * 100) / total).toFixed(1) : 0}%)`
                    },
                  },
                },
              },
            }}
          />
        ) : (
          <Bar
            key={`bar-${chart}`}
            data={{ labels, datasets: [{ data, backgroundColor: colors, borderColor: colors, borderWidth: 1 }] }}
            options={{
              indexAxis: 'y',
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                legend: { display: false },
                tooltip: {
                  rtl,
                  callbacks: { label: (c: TooltipItem<'bar'>) => ` ${(c.parsed.x ?? 0).toLocaleString(locale)} ${chart === 'users' ? t('входов') : t('обращений')}` },
                },
              },
              scales: {
                x: { reverse: rtl, ticks: { color: textColor, font: { size: 11 } }, beginAtZero: true },
                y: {
                  position: rtl ? 'right' : 'left',
                  ticks: {
                    color: textColor,
                    font: { size: 12 },
                    callback: function (val) {
                      const lbl = String(this.getLabelForValue(Number(val)))
                      return lbl.length > 30 ? lbl.slice(0, 28) + '…' : lbl
                    },
                  },
                },
              },
            }}
          />
        )}
      </FitChartBox>
    </Paper>
  )

  const usersTable = (
    <Table size="small" stickyHeader sx={{ ...TABLE_SX, width: totalWidth(Object.keys(COLS_USERS), wUsers), minWidth: '100%' }}>
      <Cols keys={Object.keys(COLS_USERS)} widths={wUsers} />
      <TableHead>
        <TableRow>
          <SortCell field="name" sort={sortUsers.sort} onSort={sortUsers.toggle} widths={wUsers} help={t('Пользователь сайта (email)')}>{t('Пользователь')}</SortCell>
          <SortCell field="count" sort={sortUsers.sort} onSort={sortUsers.toggle} widths={wUsers} help={t('Число входов на сайт за всё время')}>{t('Входов')}</SortCell>
          <SortCell field="first" sort={sortUsers.sort} onSort={sortUsers.toggle} widths={wUsers} help={t('Первый вход на сайт')}>{t('Первый вход')}</SortCell>
          <SortCell field="last" sort={sortUsers.sort} onSort={sortUsers.toggle} widths={wUsers} help={t('Последний вход на сайт')}>{t('Последний вход')}</SortCell>
          <SortCell field="n" sort={sortUsers.sort} onSort={sortUsers.toggle} widths={wUsers} help={t('Обращений к формам за выбранный период')}>{t('Обращений')}</SortCell>
          <SortCell field="ips" sort={sortUsers.sort} onSort={sortUsers.toggle} widths={wUsers} help={t('Разных IP за выбранный период')}>IP</SortCell>
          <SortCell field="lastIp" sort={sortUsers.sort} onSort={sortUsers.toggle} widths={wUsers} help={t('IP последнего обращения пользователя за выбранный период')}>{t('Посл. IP')}</SortCell>
          <SortCell field="place" sort={sortUsers.sort} onSort={sortUsers.toggle} widths={wUsers} help={t('Страна и город по последнему IP')}>{t('Страна, город')}</SortCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {sortedUsers.map((u) => (
          <TableRow
            key={u.name || '_anon'}
            hover
            selected={Boolean(u.name) && search === u.name}
            sx={{ cursor: u.name ? 'pointer' : undefined }}
            title={u.name ? t('Показать посещения пользователя (повторный щелчок — снять фильтр)') : undefined}
            onClick={() => {
              if (!u.name) return
              setSearchText(null)
              run({ search: search === u.name ? '' : u.name })
            }}
          >
            <TableCell sx={{ color: 'secondary.main' }}>{u.name || <Box component="span" sx={{ color: 'text.secondary' }}>{t('— без входа —')}</Box>}</TableCell>
            <TableCell align="right">{u.count ?? ''}</TableCell>
            <TableCell sx={{ whiteSpace: 'nowrap', color: 'text.secondary' }}>{local(u.first, locale)}</TableCell>
            <TableCell sx={{ whiteSpace: 'nowrap', color: 'text.secondary' }}>
              {local(u.last, locale)}
              {u.last && <Box sx={{ fontSize: 11 }}>{ago(u.last, locale)}</Box>}
            </TableCell>
            <TableCell align="right">{u.n ?? ''}</TableCell>
            <TableCell align="right">{u.ips ?? ''}</TableCell>
            <TableCell sx={{ whiteSpace: 'nowrap', fontFamily: 'monospace' }}>{u.lastIp}</TableCell>
            <TableCell>{u.place}</TableCell>
          </TableRow>
        ))}
        {sortedUsers.length === 0 && noData(8)}
      </TableBody>
    </Table>
  )

  const keyTable = (list: StatKey[], s: ReturnType<typeof useColSort>, w: Widths, keys: string[], head: string, withUsers: boolean) => (
    <Table size="small" stickyHeader sx={{ ...TABLE_SX, width: totalWidth(keys, w), minWidth: '100%' }}>
      <Cols keys={keys} widths={w} />
      <TableHead>
        <TableRow>
          <SortCell field="key" sort={s.sort} onSort={s.toggle} widths={w}>{head}</SortCell>
          <SortCell field="n" sort={s.sort} onSort={s.toggle} widths={w} help={t('Обращений')}>{t('Обращений')}</SortCell>
          <SortCell field="ips" sort={s.sort} onSort={s.toggle} widths={w} help={t('Разных IP')}>IP</SortCell>
          {withUsers && <SortCell field="users" sort={s.sort} onSort={s.toggle} widths={w} help={t('Разных пользователей')}>{t('Польз.')}</SortCell>}
        </TableRow>
      </TableHead>
      <TableBody>
        {list.map((a) => (
          <TableRow key={a.key} hover>
            <TableCell>{withUsers ? t(a.key) : a.key}</TableCell>
            <TableCell align="right">{a.n}</TableCell>
            <TableCell align="right">{a.ips}</TableCell>
            {withUsers && <TableCell align="right">{a.users}</TableCell>}
          </TableRow>
        ))}
        {list.length === 0 && noData(withUsers ? 4 : 3)}
      </TableBody>
    </Table>
  )

  const statsCard = (
    <Paper variant="outlined" sx={{ flex: '1 1 0', minHeight: 0, p: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <ToggleButtonGroup exclusive size="small" value={tbl} onChange={(_, v) => v && setTbl(v)} sx={{ mb: 1, alignSelf: 'flex-start' }}>
        {hasUsers && (
          <ToggleButton value="users" title={t('Пользователи: входов и даты входа — за всё время; обращения, IP и последнее обращение — за выбранный период')}>
            {t('Пользователи')}
          </ToggleButton>
        )}
        <ToggleButton value="forms" title={t('Формы сайта за выбранный период')}>{t('Формы')}</ToggleButton>
        <ToggleButton value="places" title={t('Страны и города посетителей (по IP) за выбранный период')}>{t('Места')}</ToggleButton>
      </ToggleButtonGroup>
      <TableContainer sx={{ ...FILL_SX, border: 0 }}>
        {tbl === 'users' && hasUsers ? usersTable : tbl === 'places' ? keyTable(sortedPlaces, sortPlaces, wPlaces, Object.keys(COLS_PLACES), t('Страна, город'), false) : keyTable(sortedForms, sortForms, wForms, Object.keys(COLS_FORMS), t('Форма'), true)}
      </TableContainer>
    </Paper>
  )

  return (
    <Box sx={PAGE_SX}>
      <LoadingBar loading={loading} />
      <FlashMessages messages={messages} onDismiss={dismiss} />
      <Typography variant="caption" color="text.secondary" sx={{ mb: 1 }}>
        {t('Посещения сайта: дата и место (порядок уровней — переключателем) → IP → открытые формы и число обращений')}
      </Typography>
      <Paper variant="outlined" sx={{ p: 1, mb: 1, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1.5 }}>
        <ToggleButtonGroup exclusive size="small" value={mode} onChange={(_, v) => v && run({ mode: v })}>
          <ToggleButton value="day" title={t('Обращения за выбранные сутки')}>{t('Сутки')}</ToggleButton>
          <ToggleButton value="all" title={t('Обращения за всё время')}>{t('Всё время')}</ToggleButton>
        </ToggleButtonGroup>
        {mode === 'day' && (
          <>
            <Tooltip title={t('Предыдущие сутки')}>
              <IconButton size="small" aria-label={t('Предыдущие сутки')} disabled={loading} onClick={() => run({ date: shiftDay(date, -1) })}>
                <ChevronLeftIcon />
              </IconButton>
            </Tooltip>
            <DateField size="small" required value={date} onCommit={(v) => v && run({ date: v })} />
            <Tooltip title={t('Следующие сутки')}>
              <span>
                <IconButton size="small" aria-label={t('Следующие сутки')} disabled={loading || date >= todayLocal()} onClick={() => run({ date: shiftDay(date, 1) })}>
                  <ChevronRightIcon />
                </IconButton>
              </span>
            </Tooltip>
          </>
        )}
        <TextField
          size="small"
          placeholder={t('Поиск…  (& — И, ; — ИЛИ)')}
          title={t('Поиск по стране, городу, IP, пользователю и названию формы: & — И (все слова), ; — ИЛИ (любое слово)')}
          value={text}
          sx={{ width: 260 }}
          onChange={(e) => setSearchText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && run({ search: text })}
          onBlur={() => text !== search && run({ search: text })}
        />
        <ToggleButtonGroup
          exclusive
          size="small"
          value={order}
          onChange={(_, v) => {
            if (!v) return
            setOrder(v)
            setOpen({})
            setPage(0)
            try {
              localStorage.setItem('guests_order', v)
            } catch {
              /* ignore */
            }
          }}
        >
          <ToggleButton value="date" title={t('Первый уровень — дата, второй — страна и город')}>{t('Дата → место')}</ToggleButton>
          <ToggleButton value="place" title={t('Первый уровень — страна и город, второй — дата')}>{t('Место → дата')}</ToggleButton>
        </ToggleButtonGroup>
        <Button size="small" startIcon={<UnfoldMoreIcon />} onClick={() => setAll(true)} title={t('Раскрыть все уровни')}>{t('Развернуть всё')}</Button>
        <Button size="small" startIcon={<UnfoldLessIcon />} onClick={() => setAll(false)} title={t('Свернуть все уровни')}>{t('Свернуть всё')}</Button>
        <Typography variant="body2" color="text.secondary">
          {order === 'place' ? t('Мест') : t('Дат')}: <b>{tree.length}</b>, {t('обращений')}: <b>{visits}</b>
        </Typography>
      </Paper>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 1 }}>
        <Chip size="small" label={<span>{t('Всего гостей:')} <b>{par.total_guests ?? '—'}</b></span>} title={t('Все IP-адреса, когда-либо заходившие на сайт')} />
        <Chip size="small" label={<span>{t('Активных:')} <b>{activeIps}</b></span>} title={t('Разных IP за выбранный период')} />
        <Chip size="small" label={<span>{t('Всего обращений:')} <b>{visits}</b></span>} title={t('Обращений к формам за выбранный период')} />
        <Chip size="small" label={<span>{t('Уникальных форм:')} <b>{statForms.length}</b></span>} title={t('Разных форм, открытых за выбранный период')} />
        {hasUsers && <Chip size="small" label={<span>{t('Пользователей:')} <b>{activeUsers}</b></span>} title={t('Разных вошедших пользователей за выбранный период')} />}
      </Box>
      <SplitPane
        storageKey="guests_cols"
        first={treeCard}
        second={<SplitPane storageKey="guests_stats" direction="column" first={chartCard} second={statsCard} defaultSize="40%" minSize={140} />}
        defaultSize="58%"
        minSize={300}
      />
    </Box>
  )
}
