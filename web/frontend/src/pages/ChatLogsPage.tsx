import { useEffect, useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControl from '@mui/material/FormControl'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Select from '@mui/material/Select'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import Typography from '@mui/material/Typography'
import { useForm } from '../useForm'
import type { FormFields } from '../api'
import { useT } from '../i18n'
import FlashMessages from '../components/FlashMessages'
import LoadingBar from '../components/LoadingBar'
import PlainTextArea from '../components/PlainTextArea'
import { FILL_SX, PAGE_SX } from '../components/layout'
import DayNavigator, { showDoUpdate, useAutoRefresh } from '@shared-web/components/DayNavigator'
import { TablePagination, TableToolbar, baseFields } from '@shared-web/components/TableControls'
import { formatLogTime } from '@shared-web/components/logTime'

// Лог чат-сообщений (бывший templates/chat_logs.html, бэкенд chat_logs.py): вся информация / выбранные сутки,
// фильтры по IP, стране, городу, типу запроса и email. Поля — как у старой формы.

interface ChatRow {
  id: number
  at_date_time: string | null
  ip: string | null
  country: string | null
  city: string | null
  type_message: string | null
  message: string | null
  answer: string | null
  td: string | null
  email: string | null
}

const AUTO_REFRESH_MS = 30 * 1000
const FILTERS = ['filter_ip', 'filter_country', 'filter_city', 'filter_email'] as const

/** Длинный текст в ячейке — три строки, щелчок открывает целиком. */
function Clamp({ text, onOpen }: { text: string | null; onOpen: () => void }) {
  if (!text) return null
  return (
    <Box
      onClick={onOpen}
      sx={{ cursor: 'pointer', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden', whiteSpace: 'pre-wrap' }}
      dir="auto"
    >
      {text}
    </Box>
  )
}

export default function ChatLogsPage() {
  const t = useT()
  const { par, messages, loading, error, submit, dismiss } = useForm('chat_logs')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [shown, setShown] = useState<{ title: string; text: string } | null>(null)

  useEffect(() => {
    if (!par) return
    setFilters(Object.fromEntries([...FILTERS, 'filter_type_message'].map((k) => [k, par[k] ?? ''])))
  }, [par])

  const fields = (extra: FormFields): FormFields => ({
    ...baseFields(par ?? {}),
    dt_start: par?.st_date ?? '',
    st_date: par?.st_date ?? '',
    ...filters,
    do_update: par && showDoUpdate(par) && par.do_update ? 'Обновлять' : undefined,
    ...extra,
  })

  const refreshIn = useAutoRefresh(par, () => submit(fields({})), shown != null, AUTO_REFRESH_MS)

  if (error) return <Typography color="error">{error}</Typography>
  if (!par) return <LoadingBar loading />

  const rows: ChatRow[] = par.data ?? []
  const formatDt: string = par.format_dt ?? 'HH:mm:ss'
  const apply = (extra: FormFields = {}) => submit(fields({ page: 1, ...extra }))
  const labels: Record<string, string> = {
    filter_ip: t('IP'),
    filter_country: t('Страна'),
    filter_city: t('Город'),
    filter_email: t('Email'),
  }

  return (
    <Box sx={PAGE_SX}>
      <FlashMessages messages={messages} onDismiss={dismiss} />
      <LoadingBar loading={loading} />

      <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5, flexShrink: 0 }}>
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
          {par.switch === 'one_day' && <DayNavigator par={par} onSubmit={submit} base={fields({})} refreshIn={refreshIn} />}
        </Box>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center', mb: 1.5 }}>
          {FILTERS.map((k) => (
            <TextField
              key={k}
              label={labels[k]}
              value={filters[k] ?? ''}
              onChange={(e) => setFilters((f) => ({ ...f, [k]: e.target.value }))}
              onKeyDown={(e) => e.key === 'Enter' && apply()}
              sx={{ width: k === 'filter_email' ? 200 : 150 }}
              title={t('Фильтр по полю «{name}»', { name: labels[k] })}
            />
          ))}
          <FormControl sx={{ minWidth: 140 }}>
            <InputLabel id="cl_type">{t('Тип запроса')}</InputLabel>
            <Select
              labelId="cl_type"
              label={t('Тип запроса')}
              value={filters.filter_type_message ?? ''}
              onChange={(e) => apply({ filter_type_message: e.target.value })}
            >
              {(par.types_message ?? ['']).map((v: string) => (
                <MenuItem key={v} value={v}>
                  {v || t('Все')}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button size="small" variant="outlined" onClick={() => apply()}>
            {t('Применить фильтры')}
          </Button>
          <Button size="small" onClick={() => submit(fields({ clear_filters: 1 }))}>
            {t('Очистить фильтры')}
          </Button>
        </Box>
        <TableToolbar par={par} onSubmit={submit} base={fields({})} hideSort />
      </Paper>

      <TableContainer component={Paper} variant="outlined" sx={FILL_SX}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>{t('Дата/Время')}</TableCell>
              <TableCell>IP</TableCell>
              <TableCell>{t('Страна')}</TableCell>
              <TableCell>{t('Город')}</TableCell>
              <TableCell>{t('Тип запроса')}</TableCell>
              <TableCell sx={{ minWidth: 260 }}>{t('Запрос')}</TableCell>
              <TableCell sx={{ minWidth: 320 }}>{t('Ответ')}</TableCell>
              <TableCell align="right">TD</TableCell>
              <TableCell>Email</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id} hover>
                <TableCell sx={{ verticalAlign: 'top' }}>{r.id}</TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap', verticalAlign: 'top' }}>{formatLogTime(r.at_date_time, formatDt)}</TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>{r.ip}</TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>{r.country}</TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>{r.city}</TableCell>
                <TableCell sx={{ verticalAlign: 'top', color: 'secondary.main' }}>{r.type_message}</TableCell>
                <TableCell sx={{ verticalAlign: 'top', fontSize: 12 }}>
                  <Clamp text={r.message} onOpen={() => setShown({ title: t('Запрос') + ' #' + r.id, text: r.message ?? '' })} />
                </TableCell>
                <TableCell sx={{ verticalAlign: 'top', fontSize: 12 }}>
                  <Clamp text={r.answer} onOpen={() => setShown({ title: t('Ответ') + ' #' + r.id, text: r.answer ?? '' })} />
                </TableCell>
                <TableCell align="right" sx={{ whiteSpace: 'nowrap', verticalAlign: 'top' }}>
                  {r.td ?? ''}
                </TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>{r.email}</TableCell>
              </TableRow>
            ))}
            {!rows.length && !loading && (
              <TableRow>
                <TableCell colSpan={10} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                  {t('Нет данных')}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination par={par} onSubmit={submit} base={fields({})} />

      <Dialog open={shown != null} onClose={() => setShown(null)} maxWidth="md" fullWidth>
        <DialogTitle>{shown?.title}</DialogTitle>
        <DialogContent dividers>
          <PlainTextArea value={shown?.text ?? ''} readOnly dir="auto" minRows={18} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShown(null)}>{t('Закрыть')}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
