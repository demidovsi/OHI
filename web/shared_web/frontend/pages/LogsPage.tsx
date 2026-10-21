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
  const { par, messages, loading, error, submit, dismiss } = useForm('logs')

  const fields = (extra: FormFields): FormFields => ({
    ...baseFields(par ?? {}),
    dt_start: par?.st_date ?? '',
    st_date: par?.st_date ?? '',
    search_level: par?.search_level ?? '',
    search_source: par?.search_source ?? '',
    search_who: par?.search_who ?? '',
    // чекбокс есть только на первой странице текущих суток (dates.html)
    do_update: par && showDoUpdate(par) && par.do_update ? 'Обновлять' : undefined,
    ...extra,
  })

  // Автообновление раз в 30 с при включённом do_update (как scheduleAutoRefresh в logs.js);
  // refreshIn — секунды до обновления, показываются в подсказке галочки «Обновлять».
  const refreshIn = useAutoRefresh(par, () => submit(fields({})), false, AUTO_REFRESH_MS)

  if (error) return <Typography color="error">{error}</Typography>
  if (!par) return <LoadingBar loading />

  const rows: LogRow[] = par.data ?? []
  const errorsOn = par.search_level === ERRORS_SEARCH
  const formatDt: string = par.format_dt ?? 'HH:mm:ss'

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
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>Time</TableCell>
              <TableCell>Operation</TableCell>
              <TableCell>Source</TableCell>
              <TableCell align="right">TD</TableCell>
              <TableCell align="right">Page/Count</TableCell>
              <TableCell>Who/Where</TableCell>
              <TableCell>Comment/Server</TableCell>
              <TableCell>Message</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => {
              const lk = levelKind(r)
              const ck = commentKind(r)
              return (
                <TableRow key={r.id} hover>
                  <TableCell sx={{ whiteSpace: 'nowrap', verticalAlign: 'top' }}>{formatLogTime(r.at_date_time, formatDt)}</TableCell>
                  <TableCell sx={{ verticalAlign: 'top', color: KIND_COLOR[lk], fontWeight: lk === 'plain' ? 400 : 700 }}>
                    {r.level}
                  </TableCell>
                  <TableCell sx={{ verticalAlign: 'top' }}>{r.source}</TableCell>
                  <TableCell align="right" sx={{ whiteSpace: 'nowrap', verticalAlign: 'top' }}>
                    {r.td || ''}
                  </TableCell>
                  <TableCell align="right" sx={{ verticalAlign: 'top' }}>
                    {r.page || ''}
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'pre-wrap', fontSize: 12, verticalAlign: 'top', minWidth: 120 }}>{r.law_id ?? ''}</TableCell>
                  <TableCell sx={{ whiteSpace: 'pre-wrap', fontSize: 12, verticalAlign: 'top', minWidth: 140 }}>{r.file_name ?? ''}</TableCell>
                  <TableCell sx={{ fontSize: 12, verticalAlign: 'top', minWidth: 320, color: KIND_COLOR[ck] }}>
                    <ClampedText text={r.comment ?? ''} />
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
