import { useEffect, useMemo, useState } from 'react'
import { Bar, Line } from 'react-chartjs-2'
import {
  BarElement,
  CategoryScale,
  Chart,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip as ChartTooltip,
  type ChartOptions,
} from 'chart.js'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import FormControl from '@mui/material/FormControl'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Radio from '@mui/material/Radio'
import RadioGroup from '@mui/material/RadioGroup'
import Select from '@mui/material/Select'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import Typography from '@mui/material/Typography'
import { useTheme } from '@mui/material/styles'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import ClearIcon from '@mui/icons-material/Clear'
import RefreshIcon from '@mui/icons-material/Refresh'
import { useForm } from '../useForm'
import type { FormFields } from '../api'
import { useI18n } from '../i18n'
import FlashMessages from '../components/FlashMessages'
import LoadingBar from '../components/LoadingBar'
import { PAGE_SX } from '../components/layout'
import DateField from '@shared-web/components/DateField'

Chart.register(BarElement, CategoryScale, LinearScale, LineElement, PointElement, Legend, ChartTooltip)

// Аналитика сообщений новостных лент (бывшие templates/analyses*.html, бэкенд analyses.py). Прежде график строил
// сервер (plotly → HTML), теперь сервер отдаёт данные (par.chart), график — react-chartjs-2. Поля старой формы:
// channels / participation, channel_type, period_type, selected_channel, selected_theme, date_filter_type,
// relative_period, start_date, end_date, button_to_left / button_to_right, refresh.

interface ChartData {
  mode: 'bar' | 'line'
  switch: 'channels' | 'participation'
  period: 'day' | 'week' | 'month'
  messages_count: number
  percent: number
  has_theme: boolean
  days: number
  y_kind: 'count' | 'percent'
  labels: string[]
  datasets: { label: string; data: (number | null)[] }[]
}

const PERIODS = [7, 30, 90, 180, 365] as const
const PERIOD_LABELS: Record<number, string> = {
  7: 'Последние 7 дней (неделя)',
  30: 'Последние 30 дней (месяц)',
  90: 'Последние 90 дней (квартал)',
  180: 'Последние 180 дней (полгода)',
  365: 'Последние 365 дней (год)',
}
const GROUP_LABELS = { day: 'По дням', week: 'По неделям', month: 'По месяцам' } as const

/** «5 дней» по-русски с согласованием, на других языках — одно слово. */
function daysPhrase(days: number, lang: string, t: (s: string) => string): string {
  if (lang !== 'ru') return `${days} ${t('дней')}`
  const n = Math.abs(days) % 100
  const last = n % 10
  const word = n >= 11 && n <= 14 ? 'дней' : last === 1 ? 'день' : last >= 2 && last <= 4 ? 'дня' : 'дней'
  return `${days} ${word}`
}

/** Цвет линии канала: равномерно по кругу оттенков. */
const lineColor = (i: number, n: number) => `hsl(${Math.round((360 * i) / Math.max(n, 1))}, 65%, 50%)`

function AnalysesChart({ chart }: { chart: ChartData }) {
  const theme = useTheme()
  const { t, lang } = useI18n()
  const percent = chart.y_kind === 'percent'
  const yLabel = percent ? (chart.mode === 'bar' ? t('% сообщений с темами') : t('% сообщений')) : t('Количество сообщений')
  const group = t(GROUP_LABELS[chart.period] ?? 'По дням').toLowerCase()
  const head = chart.switch === 'channels' ? t('Активность сообщений') : t('Участие каналов в темах сообщений')
  const counts =
    chart.switch === 'participation' && !chart.has_theme
      ? `(${chart.messages_count})`
      : `(${chart.messages_count} ${t('или')} ${chart.percent} %)`
  const title = `${head} ${group} ${counts} ( ${t('интервал')} ${daysPhrase(chart.days, lang, t)} )`

  const options = useMemo<ChartOptions<'bar' | 'line'>>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: chart.mode === 'line',
          position: 'right',
          labels: { color: theme.palette.text.primary, boxWidth: 12 },
          title: { display: chart.mode === 'line', text: t('Канал'), color: theme.palette.text.primary },
        },
        tooltip: {
          callbacks: percent ? { label: (c) => `${c.dataset.label ? c.dataset.label + ': ' : ''}${c.formattedValue} %` } : {},
        },
      },
      scales: {
        x: {
          title: { display: true, text: t('Дата'), color: theme.palette.text.secondary },
          ticks: { color: theme.palette.text.secondary },
          grid: { color: theme.palette.divider },
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: yLabel, color: theme.palette.text.secondary },
          ticks: { color: theme.palette.text.secondary, precision: percent ? undefined : 0 },
          grid: { color: theme.palette.divider },
        },
      },
    }),
    [chart.mode, percent, theme, t, yLabel],
  )

  const n = chart.datasets.length
  const data = {
    labels: chart.labels,
    datasets: chart.datasets.map((d, i) =>
      chart.mode === 'bar'
        ? { label: d.label || yLabel, data: d.data, backgroundColor: theme.palette.secondary.main }
        : { label: d.label, data: d.data, borderColor: lineColor(i, n), backgroundColor: lineColor(i, n), spanGaps: true, pointRadius: 2, tension: 0.2 },
    ),
  }

  return (
    <Paper variant="outlined" sx={{ flex: '1 1 0', minHeight: 320, p: 1.5, display: 'flex', flexDirection: 'column' }}>
      <Typography variant="subtitle2" sx={{ mb: 1, flexShrink: 0 }}>
        {title}
      </Typography>
      <Box sx={{ flex: '1 1 0', minHeight: 0, position: 'relative' }}>
        {chart.mode === 'bar' ? (
          <Bar options={options as ChartOptions<'bar'>} data={data as never} />
        ) : (
          <Line options={options as ChartOptions<'line'>} data={data as never} />
        )}
      </Box>
    </Paper>
  )
}

export default function AnalysesPage() {
  const { t } = useI18n()
  const rtl = useTheme().direction === 'rtl'
  const { par, messages, loading, error, submit, dismiss } = useForm('analyses')
  const [dates, setDates] = useState({ start: '', end: '' })

  useEffect(() => {
    if (par) setDates({ start: par.start_date ?? '', end: par.end_date ?? '' })
  }, [par])

  if (error) return <Typography color="error">{error}</Typography>
  if (!par) return <LoadingBar loading />

  const relative = par.date_filter_type === 'relative'
  const fields = (extra: FormFields): FormFields => ({
    selected_channel: par.selected_channel ?? '',
    selected_theme: par.selected_theme ?? 0,
    channel_type: par.channel_type,
    period_type: par.period_type,
    date_filter_type: par.date_filter_type,
    relative_period: par.relative_period,
    start_date: dates.start,
    end_date: dates.end,
    ...extra,
  })
  const go = (extra: FormFields) => submit(fields(extra))
  const PrevIcon = rtl ? ChevronRightIcon : ChevronLeftIcon
  const NextIcon = rtl ? ChevronLeftIcon : ChevronRightIcon
  const chart = par.chart as ChartData | undefined

  return (
    <Box sx={PAGE_SX}>
      <FlashMessages messages={messages} onDismiss={dismiss} />
      <LoadingBar loading={loading} />

      <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
          <ToggleButtonGroup exclusive size="small" value={par.switch} onChange={(_, v) => v && go({ [v]: 1 })}>
            <ToggleButton value="channels" title={t('Информация по сообщениям новостных каналов')}>
              {t('Сообщения каналов')}
            </ToggleButton>
            <ToggleButton value="participation" title={t('Информация по вкладу новостных каналов в поиски по темам')}>
              {t('Участие в темах')}
            </ToggleButton>
          </ToggleButtonGroup>
          <ToggleButtonGroup exclusive size="small" value={par.channel_type} onChange={(_, v) => v && go({ channel_type: v })}>
            <ToggleButton value="message_count">{t('Сообщения всего')}</ToggleButton>
            <ToggleButton value="message_channels">{t('Сообщения в каналах')}</ToggleButton>
          </ToggleButtonGroup>
          {par.channel_type === 'message_count' ? (
            <FormControl sx={{ minWidth: 140 }}>
              <InputLabel id="an_period">{t('Группировка:')}</InputLabel>
              <Select labelId="an_period" label={t('Группировка:')} value={par.period_type} onChange={(e) => go({ period_type: e.target.value })}>
                <MenuItem value="day">{t('По суточно')}</MenuItem>
                <MenuItem value="week">{t('По недельно')}</MenuItem>
                <MenuItem value="month">{t('По месячно')}</MenuItem>
              </Select>
            </FormControl>
          ) : (
            <FormControl sx={{ minWidth: 200 }}>
              <InputLabel id="an_channel">{t('Канал')}</InputLabel>
              <Select labelId="an_channel" label={t('Канал')} value={par.selected_channel ?? ''} onChange={(e) => go({ selected_channel: e.target.value })}>
                {(par.list_channels ?? ['']).map((c: string) => (
                  <MenuItem key={c} value={c}>
                    {c || t('Все каналы')}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
          <FormControl sx={{ minWidth: 180 }}>
            <InputLabel id="an_theme">{t('Тема')}</InputLabel>
            <Select labelId="an_theme" label={t('Тема')} value={par.selected_theme ?? 0} onChange={(e) => go({ selected_theme: e.target.value })}>
              {(par.list_themes ?? []).map((th: { id: number; sh_name: string }) => (
                <MenuItem key={th.id} value={th.id}>
                  {th.id ? th.sh_name : t('Все темы')}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <IconButton size="small" title={t('Обновить информацию')} onClick={() => go({ refresh: 1 })}>
            <RefreshIcon />
          </IconButton>
        </Box>

        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
          <IconButton size="small" title={t('Сдвинуть интервал дат влево')} onClick={() => go({ button_to_left: '1' })}>
            <PrevIcon />
          </IconButton>
          <RadioGroup row value={par.date_filter_type} onChange={(e) => go({ date_filter_type: e.target.value })} title={t('Тип фильтра по дате')}>
            <FormControlLabel value="custom" control={<Radio size="small" />} label={t('Произвольный период')} />
            <FormControlLabel value="relative" control={<Radio size="small" />} label={t('Относительный период')} />
          </RadioGroup>
          {relative ? (
            <FormControl sx={{ minWidth: 240 }}>
              <InputLabel id="an_rel">{t('Период')}</InputLabel>
              <Select labelId="an_rel" label={t('Период')} value={par.relative_period} onChange={(e) => go({ relative_period: e.target.value })}>
                {PERIODS.map((p) => (
                  <MenuItem key={p} value={p}>
                    {t(PERIOD_LABELS[p])}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          ) : (
            <>
              <DateField label={t('С даты')} value={dates.start} width={150} onCommit={(v) => go({ start_date: v })} />
              <DateField label={t('По дату')} value={dates.end} width={150} onCommit={(v) => go({ end_date: v })} />
              <IconButton size="small" title={t('Очистить фильтр по дате')} onClick={() => go({ start_date: '', end_date: '' })}>
                <ClearIcon />
              </IconButton>
            </>
          )}
          <IconButton size="small" title={t('Сдвинуть интервал дат вправо')} onClick={() => go({ button_to_right: '1' })}>
            <NextIcon />
          </IconButton>
          {relative && par.start_date ? (
            <Typography variant="body2" color="text.secondary">
              {par.start_date} — {par.end_date}
            </Typography>
          ) : null}
          <Box sx={{ flexGrow: 1 }} />
          <Typography variant="body2" color="primary">
            {t('История наблюдения с')} {par.min_date_channels} {t('по')} {par.max_date_channels} ({t('всего сообщений:')} {par.total_messages_count ?? 0})
          </Typography>
        </Box>
      </Paper>

      {chart && chart.labels.length ? (
        <AnalysesChart chart={chart} />
      ) : (
        !loading && (
          <Typography variant="body2" color="text.secondary">
            {t('Нет данных')}
          </Typography>
        )
      )}
      {par.date_filter_type === 'custom' && (dates.start || dates.end) && !chart ? (
        <Button onClick={() => go({ start_date: '', end_date: '' })}>{t('Очистить фильтр по дате')}</Button>
      ) : null}
    </Box>
  )
}
