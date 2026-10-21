import { useEffect, useState } from 'react'
import Box from '@mui/material/Box'
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
import Typography from '@mui/material/Typography'
import SearchIcon from '@mui/icons-material/Search'
import { useTheme } from '@mui/material/styles'
import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Tooltip as ChartTooltip,
  type TooltipItem,
} from 'chart.js'
import { Bar, Pie } from 'react-chartjs-2'
import { useForm } from '@app/useForm'
import type { FormFields } from '@app/api'
import FlashMessages from '@app/components/FlashMessages'
import { TablePagination, baseFields } from '@shared-web/components/TableControls'
import { useLocale, useT } from '@app/i18n'
import { FILL_SX, PAGE_SX } from '@app/components/layout'
import LoadingBar from '@app/components/LoadingBar'
import SplitPane from '@app/components/SplitPane'
import FitChartBox from '@shared-web/components/FitChartBox'
import DateField from '@shared-web/components/DateField'

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, ChartTooltip, Legend)

interface GuestRow {
  id: number
  sh_name: string | null
  country: string | null
  city: string | null
  visits: number
  last_visit: string | null
}

interface UserRow {
  username: string | null
  logins: number
  unique_ips: number
  last_login: string | null
  country: string | null
  city: string | null
  last_ip: string | null
}

interface PageRow {
  value: string | null
  visits: number
  unique_guests: number
  last_visit: string | null
}

interface ChartCfg {
  chart_type?: 'pie' | 'bar'
  labels?: string[]
  datasets?: { label: string; data: number[]; backgroundColor: string[]; borderColor?: string[]; borderWidth?: number }[]
}

/** Время из БД (UTC, без пояса) — в местном времени браузера: ГГГГ-ММ-ДД ЧЧ:ММ. */
function lastVisit(v: string | null): string {
  if (!v) return '—'
  const s = String(v).replace(' ', 'T')
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + 'Z')
  if (Number.isNaN(d.getTime())) return (s.length > 15 ? s.slice(0, 16) : s).replace('T', ' ')
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function parseChart(json: string | undefined): ChartCfg | null {
  if (!json) return null
  try {
    const cfg = JSON.parse(json) as ChartCfg
    return cfg.labels && cfg.labels.length ? cfg : null
  } catch {
    return null
  }
}

// Страница «Гости сайта» — аналог templates/guests/guests.html. Поля старой формы:
// view_mode (guests|users|pages), date_from, date_to, search, row_count/page.
// Диаграмма: pie (по странам) / bar (топ пользователей / топ страниц).
export default function GuestsPage() {
  const theme = useTheme()
  const t = useT()
  const locale = useLocale()
  const { par, messages, loading, error, submit, dismiss } = useForm('guests')
  const [search, setSearch] = useState('')
  const [dates, setDates] = useState({ date_from: '', date_to: '' })
  useEffect(() => setSearch(par?.search ?? ''), [par?.search])
  useEffect(() => setDates({ date_from: par?.date_from ?? '', date_to: par?.date_to ?? '' }), [par?.date_from, par?.date_to])

  if (error) return <Typography color="error">{error}</Typography>
  if (!par)
    return (
      <Box sx={PAGE_SX}>
        <LoadingBar loading />
      </Box>
    )

  const fields = (extra: FormFields): FormFields => ({
    ...baseFields(par),
    view_mode: par.view_mode ?? 'guests',
    date_from: par.date_from ?? '',
    date_to: par.date_to ?? '',
    ...extra,
  })

  const mode: 'guests' | 'users' | 'pages' = par.view_mode === 'users' || par.view_mode === 'pages' ? par.view_mode : 'guests'

  /** Заголовок колонки с сортировкой на сервере (order_col / order_dir); повторный щелчок — обратный порядок.
   *  Текст по первому щелчку — по возрастанию, числа и даты — по убыванию. */
  // Колонки IP («IP-адрес» в посещениях, «Посл. IP» в пользователях) — одной ширины, по IPv4; IPv6 переносится
  const IP_WIDTH = 160
  const sortCell = (key: string, label: string, opts: { align?: 'right'; text?: boolean; width?: number } = {}) => {
    const active = par.order_col === key
    const first: 'asc' | 'desc' = opts.text ? 'asc' : 'desc'
    const dir: 'asc' | 'desc' = active ? (par.order_dir === 'asc' ? 'asc' : 'desc') : first
    return (
      <TableCell align={opts.align} sx={opts.width ? { width: opts.width } : undefined} sortDirection={active ? dir : false}>
        <TableSortLabel
          active={active}
          direction={dir}
          onClick={() => submit(fields({ order_col: key, order_dir: active ? (dir === 'asc' ? 'desc' : 'asc') : first }))}
        >
          {label}
        </TableSortLabel>
      </TableCell>
    )
  }
  const isGuests = mode === 'guests'
  const summary: Record<string, number> = par.summary ?? {}
  const chart = parseChart(par.chart_json)
  const textColor = theme.palette.text.primary
  // RTL (иврит): легенда круговой диаграммы — слева, ось значений гистограммы идёт справа налево.
  const rtl = theme.direction === 'rtl'

  const submitDates = (next: { date_from: string; date_to: string }) => {
    if (next.date_from !== (par.date_from ?? '') || next.date_to !== (par.date_to ?? '')) submit(fields(next))
  }

  return (
    <Box sx={PAGE_SX}>
      <FlashMessages messages={messages} onDismiss={dismiss} />
      <LoadingBar loading={loading} />

      <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5 }}>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
          <Typography variant="h6" color="primary">
            {t(par.title)}
          </Typography>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={par.view_mode ?? 'guests'}
            onChange={(_, v) => {
              if (v) submit(fields({ view_mode: v }))
            }}
          >
            <ToggleButton value="guests">{t('Посещения')}</ToggleButton>
            <ToggleButton value="users">{t('Пользователи')}</ToggleButton>
            <ToggleButton value="pages">{t('Страницы')}</ToggleButton>
          </ToggleButtonGroup>
          <DateField
            label={t('С')}
            value={dates.date_from}
            onCommit={(v) => {
              const next = { ...dates, date_from: v }
              setDates(next)
              submitDates(next)
            }}
            width={160}
          />
          <DateField
            label={t('По')}
            value={dates.date_to}
            onCommit={(v) => {
              const next = { ...dates, date_to: v }
              setDates(next)
              submitDates(next)
            }}
            width={160}
          />
          <TextField
            placeholder={t('Поиск...')}
            value={search}
            onChange={(e) => setSearch(e.target.value.slice(0, 60))}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submit(fields({ search, page: 1 }))
            }}
            sx={{ width: 200 }}
          />
          <IconButton size="small" title={t('Применить фильтры')} onClick={() => submit(fields({ search, page: 1 }))}>
            <SearchIcon />
          </IconButton>
        </Box>
        {Object.keys(summary).length > 0 && (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1.5 }}>
            <Chip size="small" label={<span>{t('Всего гостей:')} <b>{summary.total_guests ?? '—'}</b></span>} />
            <Chip size="small" label={<span>{t('Активных:')} <b>{summary.active_guests ?? '—'}</b></span>} />
            <Chip size="small" label={<span>{t('Всего посещений:')} <b>{summary.total_visits ?? '—'}</b></span>} />
            <Chip size="small" label={<span>{t('Уникальных страниц:')} <b>{summary.total_pages ?? '—'}</b></span>} />
            <Chip size="small" label={<span>{t('Пользователей:')} <b>{summary.total_users ?? '—'}</b></span>} />
            {par.count !== undefined && par.count !== null && (
              <Chip size="small" color="primary" variant="outlined" label={<span>{t('Записей в таблице:')} <b>{par.count}</b></span>} />
            )}
          </Box>
        )}
      </Paper>

      {/* Диаграмма и таблица — панели со сплиттером (размер — свой у каждого режима); без диаграммы таблица занимает всё место. */}
      <SplitPane
        storageKey={`guests_${mode}`}
        defaultSize="40%"
        minSize={300}
        first={
          chart && (
          <Paper variant="outlined" sx={{ flex: '1 1 0', minHeight: 0, p: 1.5, display: 'flex', flexDirection: 'column' }}>
            <Typography variant="subtitle2" color="primary" sx={{ mb: 1 }}>
              {par.chart_title ? t(par.chart_title) : ''}
            </Typography>
            <FitChartBox>
              {isGuests ? (
                <Pie
                  key="pie"
                  data={{ labels: chart.labels ?? [], datasets: chart.datasets ?? [] }}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                      legend: { display: true, position: rtl ? 'left' : 'right', rtl, labels: { color: textColor, font: { size: 10 }, boxWidth: 12 } },
                      tooltip: {
                        rtl,
                        callbacks: {
                          label: (c: TooltipItem<'pie'>) => {
                            const total = (c.dataset.data as number[]).reduce((a, b) => a + b, 0)
                            const pct = total > 0 ? ((c.parsed * 100) / total).toFixed(1) : 0
                            return `${t(String(c.label))}: ${c.parsed} (${pct}%)`
                          },
                        },
                      },
                    },
                  }}
                />
              ) : (
                <Bar
                  key={`bar-${mode}`}
                  data={{ labels: chart.labels ?? [], datasets: chart.datasets ?? [] }}
                  options={{
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                      legend: { display: false },
                      tooltip: {
                        rtl,
                        callbacks: {
                          label: (c: TooltipItem<'bar'>) =>
                            ' ' +
                            t(mode === 'users' ? '{n} входов' : '{n} посещений', {
                              n: (c.parsed.x ?? 0).toLocaleString(locale),
                            }),
                        },
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
        }
        second={
        <>
          <TableContainer component={Paper} variant="outlined" sx={FILL_SX}>
            <Table size="small" stickyHeader>
              {isGuests ? (
                <>
                  <TableHead>
                    <TableRow>
                      {sortCell('sh_name', t('IP-адрес'), { text: true, width: IP_WIDTH })}
                      {sortCell('country', t('Страна'), { text: true })}
                      {sortCell('city', t('Город'), { text: true })}
                      {sortCell('visits', t('Визитов'), { align: 'right' })}
                      {sortCell('last_visit', t('Последний визит'))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(par.data as GuestRow[] | undefined)?.map((r) => (
                      <TableRow key={r.id} hover>
                        <TableCell sx={{ fontFamily: 'monospace', color: 'primary.main', wordBreak: 'break-all' }}>{r.sh_name || '—'}</TableCell>
                        <TableCell>{r.country ? t(r.country) : '—'}</TableCell>
                        <TableCell>{r.city || '—'}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>
                          {r.visits || 0}
                        </TableCell>
                        <TableCell sx={{ whiteSpace: 'nowrap', color: 'text.secondary', fontSize: 12 }}>{lastVisit(r.last_visit)}</TableCell>
                      </TableRow>
                    ))}
                    {!par.data?.length && !loading && (
                      <TableRow>
                        <TableCell colSpan={5} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                          {t('Нет данных')}
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </>
              ) : mode === 'users' ? (
                <>
                  <TableHead>
                    <TableRow>
                      {sortCell('username', t('Пользователь'), { text: true })}
                      {sortCell('logins', t('Входов'), { align: 'right' })}
                      {sortCell('unique_ips', 'IP', { align: 'right' })}
                      {sortCell('last_ip', t('Посл. IP'), { text: true, width: IP_WIDTH })}
                      {sortCell('country', t('Страна'), { text: true })}
                      {sortCell('last_login', t('Последний вход'))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(par.data as UserRow[] | undefined)?.map((r, i) => (
                      <TableRow key={`${r.username}-${i}`} hover>
                        <TableCell sx={{ color: 'primary.main', wordBreak: 'break-all' }}>{r.username || '—'}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>
                          {r.logins || 0}
                        </TableCell>
                        <TableCell align="right">{r.unique_ips || 0}</TableCell>
                        <TableCell sx={{ fontFamily: 'monospace', fontSize: 12, wordBreak: 'break-all' }}>{r.last_ip || '—'}</TableCell>
                        <TableCell>
                          {r.country ? t(r.country) : '—'}
                          {r.city ? `, ${r.city}` : ''}
                        </TableCell>
                        <TableCell sx={{ whiteSpace: 'nowrap', color: 'text.secondary', fontSize: 12 }}>{lastVisit(r.last_login)}</TableCell>
                      </TableRow>
                    ))}
                    {!par.data?.length && !loading && (
                      <TableRow>
                        <TableCell colSpan={6} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                          {t('Нет данных')}
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </>
              ) : (
                <>
                  <TableHead>
                    <TableRow>
                      {sortCell('value', t('Страница'), { text: true })}
                      {sortCell('visits', t('Посещений'), { align: 'right' })}
                      {sortCell('unique_guests', t('Гостей'), { align: 'right' })}
                      {sortCell('last_visit', t('Последнее'))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(par.data as PageRow[] | undefined)?.map((r, i) => (
                      <TableRow key={`${r.value}-${i}`} hover>
                        <TableCell sx={{ color: 'primary.main', wordBreak: 'break-all' }}>{r.value || '—'}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>
                          {r.visits || 0}
                        </TableCell>
                        <TableCell align="right">{r.unique_guests || 0}</TableCell>
                        <TableCell sx={{ whiteSpace: 'nowrap', color: 'text.secondary', fontSize: 12 }}>{lastVisit(r.last_visit)}</TableCell>
                      </TableRow>
                    ))}
                    {!par.data?.length && !loading && (
                      <TableRow>
                        <TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                          {t('Нет данных')}
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </>
              )}
            </Table>
          </TableContainer>
          <TablePagination par={par} onSubmit={submit} base={fields({})} />
        </>
        }
      />
    </Box>
  )
}
