import { useState } from 'react'
import Box from '@mui/material/Box'
import IconButton from '@mui/material/IconButton'
import Paper from '@mui/material/Paper'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import Typography from '@mui/material/Typography'
import { alpha } from '@mui/material/styles'
import { useForm } from '@app/useForm'
import type { FormFields } from '@app/api'
import FlashMessages from '@app/components/FlashMessages'
import DayNavigator, { showDoUpdate, useAutoRefresh } from '@shared-web/components/DayNavigator'
import { TablePagination, TableToolbar, baseFields } from '@shared-web/components/TableControls'
import { formatLogTime } from '@shared-web/components/logTime'
import ClampedText from '@shared-web/components/ClampedText'
import { useDayRollover } from '@app/components/useDayRollover'
import { ResizeHandle, useColumnWidths } from '@shared-web/components/columnResize'
import { useT } from '@app/i18n'
import { FILL_SX, PAGE_SX } from '@app/components/layout'
import LoadingBar from '@app/components/LoadingBar'

interface LogRow {
  id: number
  at_date_time: string
  level: string
  source: string
  td: string | null
  page: string | number | null
  law_id: string | null
  file_name: string | null
  comment: string | null
  request?: string | null
}

// ширины колонок по умолчанию (px); пользователь меняет их мышью (ручка на границе заголовка), ширины запоминаются в localStorage.
// Operation: значения вроде «✔️ChatGPT-ERROR», «💾Write to DB» должны помещаться без переноса по символам; Message занимает остаток
const COL_DEFAULTS = { time: 150, level: 170, source: 150, td: 80, page: 100, who: 130, server: 150 } as const
const MESSAGE_MIN_WIDTH = 320
const COL_STORAGE_KEY = 'logs.columnWidths'
// переносы по ширине колонки: при tableLayout: fixed длинные слова без пробелов не должны раздвигать соседей
const CELL_WRAP_SX = { overflowWrap: 'anywhere' } as const

type ColKey = keyof typeof COL_DEFAULTS
const COL_KEYS = Object.keys(COL_DEFAULTS) as ColKey[]
const HEADERS: [ColKey, string, 'left' | 'right'][] = [
  ['time', 'Time', 'left'],
  ['level', 'Operation', 'left'],
  ['source', 'Source', 'left'],
  ['td', 'TD', 'right'],
  ['page', 'Page/Count', 'right'],
  ['who', 'Who/Where', 'left'],
  ['server', 'Comment/Server', 'left'],
]

const AUTO_REFRESH_MS = 30 * 1000

/** Кнопка 🐞: поисковый образ ошибок в фильтре Operation (search_level; «;» — ИЛИ). */
const ERRORS_SEARCH = 'error;except'
const EMOJI_BUTTON_SX = { fontSize: '1.1rem', lineHeight: 1, width: 34, height: 34 } as const

type LevelKind = 'error' | 'debug' | 'info' | 'plain'

// Раскраска уровня/сообщения как в include/logs_table.html.
function levelKind(r: LogRow): LevelKind {
  const level = r.level ?? ''
  const request = r.request ?? ''
  if (/Error|error|ERROR|Exception/.test(level)) return 'error'
  if (/Debug|debug|Sleep/.test(level)) return 'debug'
  if (/Request|request|info/.test(level) || /info/.test(request)) return 'info'
  return 'plain'
}

function commentKind(r: LogRow): LevelKind {
  const comment = r.comment ?? ''
  const level = r.level ?? ''
  const request = r.request ?? ''
  if (/Ошибка|ошибка/.test(comment) || /Error|error|ERROR|Exception/.test(level)) return 'error'
  if (/Debug|debug|Sleep/.test(level)) return 'debug'
  if (/Request/.test(request) || /request|info/.test(level) || /info/.test(request)) return 'info'
  return 'plain'
}

const KIND_COLOR: Record<LevelKind, string | undefined> = {
  error: 'error.main',
  debug: 'primary.main',
  info: 'secondary.main',
  plain: undefined,
}

// Страница «Лог работы» — аналог templates/logs.html + include/logs_top1.html,
// logs_table.html + static/js/logs.js. Поля старой формы: all_days/one_day,
// left/right/current_day/dt_start/st_date, do_update, row_count/page/search/refresh_table,
// search_level/search_source/search_who (поиск по OPERATION, SOURCE и WHO; search — только по MESSAGE).
export default function LogsPage() {
  const t = useT()
  const widths = useColumnWidths(COL_STORAGE_KEY, COL_DEFAULTS)
  const { par, messages, loading, error, submit, dismiss } = useForm('logs')
  // Раскрытые записи Message помнит страница: обновление таблицы (автообновление, смена страницы/сутки) их не закрывает
  const [opened, setOpened] = useState<Set<number>>(() => new Set())
  const toggleOpened = (id: number) =>
    setOpened((prev) => {
      const next = new Set(prev)
      if (!next.delete(id)) next.add(id)
      return next
    })

  const fields = (extra: FormFields): FormFields => ({
    ...baseFields(par ?? {}),
    dt_start: par?.st_date ?? '',
    st_date: par?.st_date ?? '',
    // все поиски по отдельным колонкам (par.extra_searches): их значения идут в каждый запрос — обновление, автообновление, страницы, сутки
    ...Object.fromEntries((par?.extra_searches ?? []).map((e: { name: string }) => [e.name, par?.[e.name] ?? ''])),
    // чекбокс есть только на первой странице текущих суток (dates.html)
    do_update: par && showDoUpdate(par) && par.do_update ? 'Обновлять' : undefined,
    ...extra,
  })

  // Автообновление раз в 30 с при включённом do_update (как scheduleAutoRefresh в logs.js);
  // refreshIn — секунды до обновления, показываются в подсказке галочки «Обновлять».
  const refreshIn = useAutoRefresh(par, () => submit(fields({})), false, AUTO_REFRESH_MS)
  // при включённом автообновлении текущих суток: наступили следующие локальные сутки — перейти на новые текущие
  useDayRollover(Boolean(par && showDoUpdate(par) && par.do_update), par?.st_date, () => submit(fields({ current_day: 'current_day' })))

  if (error) return <Typography color="error">{error}</Typography>
  if (!par) return <LoadingBar loading />

  const rows: LogRow[] = par.data ?? []
  const errorsOn = par.search_level === ERRORS_SEARCH
  const formatDt: string = par.format_dt ?? 'HH:mm:ss'
  const fixedWidth = COL_KEYS.reduce((sum, k) => sum + widths.width(k), 0)

  return (
    <Box sx={PAGE_SX}>
      <FlashMessages messages={messages} onDismiss={dismiss} />
      <LoadingBar loading={loading} />

      <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5 }}>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center', mb: 1.5 }}>
          <Typography variant="h6" color="secondary">
            {t(par.title)}
          </Typography>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={par.switch}
            onChange={(_, v) => {
              if (v === 'all_days') submit(fields({ all_days: 1 }))
              if (v === 'one_day') submit(fields({ one_day: 1 }))
            }}
          >
            <ToggleButton value="all_days" title={t('Информация всего лога')}>
              {t('Вся информация')}
            </ToggleButton>
            <ToggleButton value="one_day" title={t('Информация за выбранные сутки')}>
              {t('Выбранные сутки')}
            </ToggleButton>
          </ToggleButtonGroup>
          {/* 🐞 — в фильтр Operation образ ошибок; повторное нажатие стирает его */}
          <IconButton
            size="small"
            title={t(errorsOn ? 'Убрать фильтр ошибок из Operation' : 'Только ошибки: в фильтр Operation — error;except')}
            aria-label={t('С ошибками')}
            aria-pressed={errorsOn}
            onClick={() => submit(fields({ search_level: errorsOn ? '' : ERRORS_SEARCH, page: 1 }))}
            sx={(theme) => ({
              ...EMOJI_BUTTON_SX,
              ...(errorsOn && { bgcolor: alpha(theme.palette.error.main, 0.16), outline: `1px solid ${theme.palette.error.main}` }),
            })}
          >
            🐞
          </IconButton>
          {par.switch === 'one_day' && <DayNavigator par={par} onSubmit={submit} base={fields({})} refreshIn={refreshIn} />}
        </Box>
        <TableToolbar par={par} onSubmit={submit} base={fields({})} hideSort />
      </Paper>

      <TableContainer component={Paper} variant="outlined" sx={FILL_SX}>
        <Table size="small" stickyHeader sx={{ tableLayout: 'fixed', width: '100%', minWidth: fixedWidth + MESSAGE_MIN_WIDTH }}>
          <colgroup>
            {COL_KEYS.map((k) => (
              <col key={k} style={{ width: widths.width(k) }} />
            ))}
            <col />
          </colgroup>
          <TableHead>
            <TableRow>
              {HEADERS.map(([k, label, align]) => (
                <TableCell key={k} align={align} sx={{ ...CELL_WRAP_SX, pr: 2 }}>
                  {label}
                  <ResizeHandle colKey={k} widths={widths} title={t('Потяните, чтобы изменить ширину колонки; двойной клик — ширина по умолчанию')} />
                </TableCell>
              ))}
              <TableCell>Message</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => {
              const lk = levelKind(r)
              const ck = commentKind(r)
              return (
                <TableRow key={r.id} hover>
                  <TableCell sx={{ ...CELL_WRAP_SX, verticalAlign: 'top' }}>{formatLogTime(r.at_date_time, formatDt)}</TableCell>
                  <TableCell sx={{ ...CELL_WRAP_SX, verticalAlign: 'top', color: KIND_COLOR[lk], fontWeight: lk === 'plain' ? 400 : 700 }}>
                    {r.level}
                  </TableCell>
                  <TableCell sx={{ ...CELL_WRAP_SX, verticalAlign: 'top' }}>{r.source}</TableCell>
                  <TableCell align="right" sx={{ ...CELL_WRAP_SX, verticalAlign: 'top' }}>
                    {r.td || ''}
                  </TableCell>
                  <TableCell align="right" sx={{ ...CELL_WRAP_SX, verticalAlign: 'top' }}>
                    {r.page || ''}
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'pre-wrap', fontSize: 12, verticalAlign: 'top', ...CELL_WRAP_SX }}>{r.law_id ?? ''}</TableCell>
                  <TableCell sx={{ whiteSpace: 'pre-wrap', fontSize: 12, verticalAlign: 'top', ...CELL_WRAP_SX }}>{r.file_name ?? ''}</TableCell>
                  <TableCell sx={{ fontSize: 12, verticalAlign: 'top', color: KIND_COLOR[ck], ...CELL_WRAP_SX }}>
                    <ClampedText text={r.comment ?? ''} open={opened.has(r.id)} onToggle={() => toggleOpened(r.id)} />
                  </TableCell>
                </TableRow>
              )
            })}
            {!rows.length && !loading && (
              <TableRow>
                <TableCell colSpan={8} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                  {t('Нет данных')}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination par={par} onSubmit={submit} base={fields({})} />
    </Box>
  )
}
