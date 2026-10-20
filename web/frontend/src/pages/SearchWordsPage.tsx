import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Bar } from 'react-chartjs-2'
import { BarElement, CategoryScale, Chart, LinearScale, Tooltip as ChartTooltip, type ChartOptions } from 'chart.js'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControl from '@mui/material/FormControl'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import InputLabel from '@mui/material/InputLabel'
import Link from '@mui/material/Link'
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
import { alpha, useTheme } from '@mui/material/styles'
import AddIcon from '@mui/icons-material/Add'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import DeleteIcon from '@mui/icons-material/Delete'
import RefreshIcon from '@mui/icons-material/Refresh'
import ReplayIcon from '@mui/icons-material/Replay'
import SaveIcon from '@mui/icons-material/Save'
import { useForm } from '../useForm'
import type { FormFields, Par } from '../api'
import { useAuth } from '../auth'
import { useT } from '../i18n'
import FlashMessages from '../components/FlashMessages'
import LoadingBar from '../components/LoadingBar'
import SplitPane from '../components/SplitPane'
import { HorizontalBarChart } from '../components/charts'
import { COLUMN_SX, FILL_SX, PAGE_SX } from '../components/layout'
import DateField from '@shared-web/components/DateField'
import { TablePagination, TableToolbar, baseFields } from '@shared-web/components/TableControls'

Chart.register(BarElement, CategoryScale, LinearScale, ChartTooltip)

// Темы новостей — поисковые образы (бывшие templates/search_words/*, бэкенд search_words.py). Режимы (switch):
// detail — новости темы и текст выбранной новости с подсветкой образов; diagram — количество новостей по датам
// темы (или по темам); service — правка темы и её история (только администратор). Имена полей — как в старой форме.

interface ThemeRow {
  id: number
  sh_name: string
  value: string
  exception: string
  stop: boolean
}

interface NewsRow {
  rss_history_id: number
  public_date: string | null
  source_name: string | null
}

const LANGS = ['ru', 'en', 'he'] as const

/** Текст с подсветкой поисковых образов (как jquery.highlightWithinTextarea в старой форме). */
function Highlighted({ text, words }: { text: string; words: string[] }) {
  const theme = useTheme()
  const parts = useMemo<ReactNode[]>(() => {
    const list = words.map((w) => w.replace(/[\r\n]/g, '')).filter((w) => w.trim())
    if (!text || !list.length) return [text]
    const re = new RegExp('(' + list.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'gi')
    return text.split(re).map((p, i) =>
      i % 2 ? (
        <Box key={i} component="mark" sx={{ bgcolor: alpha(theme.palette.primary.main, 0.3), color: 'inherit', borderRadius: 0.5 }}>
          {p}
        </Box>
      ) : (
        p
      ),
    )
  }, [text, words, theme])
  return <>{parts}</>
}

/** Интервал дат (his_interval.html): месяц влево/вправо, даты, текущий/прошлый месяц, весь период. */
function Interval({ par, onSubmit }: { par: Par; onSubmit: (f: FormFields) => void }) {
  const t = useT()
  const rtl = useTheme().direction === 'rtl'
  const PrevIcon = rtl ? ChevronRightIcon : ChevronLeftIcon
  const NextIcon = rtl ? ChevronLeftIcon : ChevronRightIcon
  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
      <IconButton size="small" title={t('Сдвинуть интервал на месяц влево')} onClick={() => onSubmit({ left_history: 1 })}>
        <PrevIcon />
      </IconButton>
      <DateField label={t('От')} title={t('Дата начала интервала выводимых данных')} value={par.date_begin} required width={150} onCommit={(v) => onSubmit({ date_begin: v })} />
      <DateField label={t('До')} title={t('Дата конца интервала выводимых данных')} value={par.date_end} required width={150} onCommit={(v) => onSubmit({ date_end: v })} />
      <IconButton size="small" title={t('Сдвинуть интервал на месяц вправо')} onClick={() => onSubmit({ right_history: 1 })}>
        <NextIcon />
      </IconButton>
      <Button size="small" title={t('В качестве интервала текущий месяц')} onClick={() => onSubmit({ current_month: 1 })}>
        {t('Текущий месяц')}
      </Button>
      <Button size="small" title={t('В качестве интервала прошедший месяц')} onClick={() => onSubmit({ previous_month: 1 })}>
        {t('Прошлый месяц')}
      </Button>
      <Button size="small" title={t('В качестве интервала весь период наблюдения (c 2000 года)')} onClick={() => onSubmit({ his_all: 1 })}>
        {t('Весь период')}
      </Button>
    </Box>
  )
}

function DatesBarChart({ labels, values }: { labels: string[]; values: number[] }) {
  const theme = useTheme()
  const options = useMemo<ChartOptions<'bar'>>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: theme.palette.text.secondary }, grid: { color: theme.palette.divider } },
        y: { beginAtZero: true, ticks: { color: theme.palette.text.secondary, precision: 0 }, grid: { color: theme.palette.divider } },
      },
    }),
    [theme],
  )
  const data = useMemo(
    () => ({ labels, datasets: [{ data: values, backgroundColor: theme.palette.secondary.main, borderColor: theme.palette.secondary.dark }] }),
    [labels, values, theme],
  )
  return <Bar options={options} data={data} />
}

export default function SearchWordsPage() {
  const t = useT()
  const { upr } = useAuth()
  const admin = Boolean(upr?.admin)
  const { par, messages, loading, error, submit, dismiss } = useForm('search_words')
  const [edit, setEdit] = useState({ sh_name: '', value: '', exception: '', stop: false })
  const [confirm, setConfirm] = useState<{ text: string; fields: FormFields } | null>(null)

  useEffect(() => {
    const u = par?.unit ?? {}
    setEdit({ sh_name: u.sh_name ?? '', value: u.value ?? '', exception: u.exception ?? '', stop: Boolean(u.stop) })
  }, [par])

  if (error) return <Typography color="error">{error}</Typography>
  if (!par) return <LoadingBar loading />

  const unit = par.unit ?? {}
  const changed =
    edit.sh_name.trim() !== String(unit.sh_name_init ?? '').trim() ||
    edit.value.trim() !== String(unit.value_init ?? '').trim() ||
    edit.exception.trim() !== String(unit.exception_init ?? '').trim() ||
    edit.stop !== Boolean(unit.stop_init)

  const fields = (extra: FormFields): FormFields => ({
    ...baseFields(par),
    select_theme: par.select_theme,
    theme_id: unit.id ?? 0,
    select_lang: par.select_lang,
    date_begin: par.date_begin,
    date_end: par.date_end,
    nsi_sh_name: edit.sh_name,
    nsi_value: edit.value,
    nsi_exception: edit.exception,
    stop: edit.stop ? 'on' : undefined,
    ...extra,
  })
  const go = (extra: FormFields) => submit(fields(extra))

  const themes: ThemeRow[] = par.themes ?? []
  const switchValue: string = par.switch === 'service' && !admin ? 'detail' : par.switch
  const words: string[] = par.highlight_text ?? []

  const top = (
    <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5, flexShrink: 0 }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
        <FormControl sx={{ minWidth: 220 }}>
          <InputLabel id="sw_theme">{t('Тема')}</InputLabel>
          <Select labelId="sw_theme" label={t('Тема')} value={par.select_theme ?? 0} onChange={(e) => go({ select_theme: e.target.value })}>
            {themes.map((th) => (
              <MenuItem key={th.id} value={th.id} title={th.value}>
                {th.id ? (th.stop ? '– ' : '') + th.sh_name : '—'}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <ToggleButtonGroup exclusive size="small" value={switchValue} onChange={(_, v) => v && go({ [v]: 1 })}>
          <ToggleButton value="diagram" title={t('Вывод диаграммы по датам выбранной темы или по темам')}>
            {t('Диаграмма')}
          </ToggleButton>
          <ToggleButton value="detail" title={t('Подробности по выбранной теме')}>
            {t('Подробности')}
          </ToggleButton>
          {admin && (
            <ToggleButton value="service" title={t('Управление темами')}>
              {t('Управление')}
            </ToggleButton>
          )}
        </ToggleButtonGroup>
        {switchValue === 'detail' && (
          <FormControl sx={{ minWidth: 90 }}>
            <InputLabel id="sw_lang">{t('Язык')}</InputLabel>
            <Select labelId="sw_lang" label={t('Язык')} title={t('Язык вывода текста новости')} value={par.select_lang} onChange={(e) => go({ select_lang: e.target.value })}>
              {LANGS.map((l) => (
                <MenuItem key={l} value={l}>
                  {l.toUpperCase()}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        )}
        <IconButton size="small" title={t('Полностью обновить информацию формы')} onClick={() => go({ refresh: 1 })}>
          <RefreshIcon />
        </IconButton>
        <Typography variant="body2" color="text.secondary">
          {switchValue === 'detail' && par.global_count ? t('Количество новостей темы всего') + ' = ' + par.global_count : null}
          {switchValue === 'diagram' ? t('Количество новостей за период') + ' = ' + (par.count ?? 0) : null}
          {switchValue === 'detail' && par.transcript ? '; ' + t('Длина текста на сайте') + ' = ' + (par.len_transcript ?? '') : null}
        </Typography>
      </Box>
    </Paper>
  )

  let body: ReactNode = null
  if (switchValue === 'detail') {
    const rows: NewsRow[] = par.data ?? []
    body = (
      <SplitPane
        storageKey="search_words_detail"
        defaultSize="35%"
        first={
          <Box sx={COLUMN_SX}>
            <TableToolbar par={{ ...par, no_search: true }} onSubmit={submit} base={fields({})} />
            <TableContainer component={Paper} variant="outlined" sx={FILL_SX}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell>{t('Дата')}</TableCell>
                    <TableCell align="right">{t('Номер новости')}</TableCell>
                    <TableCell>{t('Источник')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow key={r.rss_history_id} hover selected={r.rss_history_id === par.select_id}>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>{r.public_date}</TableCell>
                      <TableCell align="right">
                        <Link component="button" underline="hover" onClick={() => go({ ['show_' + r.rss_history_id]: 1 })}>
                          {r.rss_history_id}
                        </Link>
                      </TableCell>
                      <TableCell>{r.source_name}</TableCell>
                    </TableRow>
                  ))}
                  {!rows.length && !loading && (
                    <TableRow>
                      <TableCell colSpan={3} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                        {par.select_theme ? t('Нет данных') : t('Выберите тему')}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination par={par} onSubmit={submit} base={fields({})} />
          </Box>
        }
        second={
          <Paper variant="outlined" sx={{ flex: '1 1 0', minHeight: 0, overflow: 'auto', p: 1.5, whiteSpace: 'pre-wrap', fontSize: 14 }} dir={par.select_lang === 'he' ? 'rtl' : 'ltr'}>
            {par.transcript ? (
              <Highlighted text={par.transcript} words={words} />
            ) : (
              <Typography variant="body2" color="text.secondary">
                {t('Выберите новость в таблице')}
              </Typography>
            )}
          </Paper>
        }
      />
    )
  } else if (switchValue === 'diagram') {
    const labels: string[] = par.labels ?? []
    const values: number[] = par.values ?? []
    body = (
      <Box sx={COLUMN_SX}>
        <Paper variant="outlined" sx={{ p: 1, mb: 1.5, flexShrink: 0 }}>
          <Interval par={par} onSubmit={go} />
        </Paper>
        {!labels.length ? (
          <Typography variant="body2" color="text.secondary">
            {t('Нет данных')}
          </Typography>
        ) : par.select_theme ? (
          <Paper variant="outlined" sx={{ flex: '1 1 0', minHeight: 300, p: 1 }}>
            <DatesBarChart labels={labels.map((l) => String(l).slice(0, 10))} values={values} />
          </Paper>
        ) : (
          <Box sx={{ ...COLUMN_SX, overflow: 'hidden' }}>
            <HorizontalBarChart labels={labels} values={values} percent={false} summa={par.count ?? 0} legend={t('Количество новостей за период')} />
          </Box>
        )}
      </Box>
    )
  } else {
    const his: NewsRow[] = par.his_data ?? []
    body = (
      <SplitPane
        storageKey="search_words_service"
        defaultSize="45%"
        first={
          <Paper variant="outlined" sx={{ flex: '1 1 0', minHeight: 0, overflow: 'auto', p: 1.5, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {unit.id ? (
                <>
                  <Button size="small" color="secondary" startIcon={<AddIcon />} title={t('Создать новую тему')} onClick={() => go({ nsi_new_object: 1 })}>
                    {t('Создать')}
                  </Button>
                  <Button
                    size="small"
                    color="error"
                    startIcon={<DeleteIcon />}
                    title={t('Удалить выбранную тему и всю ее историческую информацию')}
                    onClick={() =>
                      setConfirm({
                        text: t('Действительно удалить тему поисковых образов [{name}] с ID={id}?', { name: unit.sh_name_init ?? '', id: unit.id }),
                        fields: { nsi_delete: 1 },
                      })
                    }
                  >
                    {t('Удалить')}
                  </Button>
                </>
              ) : null}
              {changed && (
                <>
                  <Button size="small" variant="contained" startIcon={<SaveIcon />} disabled={!edit.sh_name.trim()} title={t('Записать в БД сделанные изменения по теме')} onClick={() => go({ nsi_save: 1 })}>
                    {t('Записать')}
                  </Button>
                  <Button size="small" startIcon={<ReplayIcon />} title={t('Отменить все сделанные изменения в теме')} onClick={() => go({ nsi_refresh: 1 })}>
                    {t('Восстановить')}
                  </Button>
                </>
              )}
            </Box>
            {unit.id ? (
              <Typography variant="body2" color="primary">
                ID={unit.id}
              </Typography>
            ) : (
              <Typography variant="body2" color="text.secondary">
                {t('Новая тема')}
              </Typography>
            )}
            <TextField label={t('Тема')} title={t('Имя темы поисков в новостях')} value={edit.sh_name} onChange={(e) => setEdit((s) => ({ ...s, sh_name: e.target.value }))} required />
            <TextField
              label={t('Поисковые образы')}
              title={t('Поисковые образы через точку с запятой')}
              value={edit.value}
              onChange={(e) => setEdit((s) => ({ ...s, value: e.target.value }))}
              multiline
              minRows={6}
              maxRows={16}
            />
            <TextField
              label={t('Исключения')}
              value={edit.exception}
              onChange={(e) => setEdit((s) => ({ ...s, exception: e.target.value }))}
              multiline
              minRows={3}
              maxRows={10}
              color="error"
            />
            <FormControlLabel control={<Checkbox checked={edit.stop} onChange={(e) => setEdit((s) => ({ ...s, stop: e.target.checked }))} />} label={t('Останов работы с темой')} />
          </Paper>
        }
        second={
          <Box sx={COLUMN_SX}>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center', mb: 1 }}>
              <Typography variant="body2">
                {t('Всего новостей по теме')} ={' '}
                <Box component="b" sx={{ color: 'secondary.main' }}>
                  {par.global_count ?? 0}
                </Box>
              </Typography>
              {unit.id ? (
                <Button
                  size="small"
                  color="error"
                  startIcon={<DeleteIcon />}
                  title={t('Очистить всю историю')}
                  onClick={() => setConfirm({ text: t('Очистить всю историю темы [{name}]?', { name: unit.sh_name_init ?? '' }), fields: { his_clear: 1 } })}
                >
                  {t('Очистить')}
                </Button>
              ) : null}
            </Box>
            <Paper variant="outlined" sx={{ p: 1, mb: 1, flexShrink: 0 }}>
              <Interval par={par} onSubmit={go} />
            </Paper>
            <TableToolbar par={{ ...par, no_search: true }} onSubmit={submit} base={fields({})} hideSort />
            <TableContainer component={Paper} variant="outlined" sx={FILL_SX}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell>{t('Дата')}</TableCell>
                    <TableCell align="right">{t('Номер новости')}</TableCell>
                    <TableCell>{t('Источник')}</TableCell>
                    <TableCell />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {his.map((r) => (
                    <TableRow key={r.rss_history_id} hover>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>{r.public_date ?? ''}</TableCell>
                      <TableCell align="right">{r.rss_history_id}</TableCell>
                      <TableCell>{r.source_name}</TableCell>
                      <TableCell>
                        <IconButton
                          size="small"
                          color="error"
                          title={t('Удаление новости из темы (и, возможно, самой новости)')}
                          onClick={() =>
                            setConfirm({
                              text: t('Удалить новость {id} из темы? Если у новости нет других тем, она будет удалена вместе со статьёй.', { id: r.rss_history_id }),
                              fields: { ['his_delete_' + r.rss_history_id]: 1 },
                            })
                          }
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!his.length && !loading && (
                    <TableRow>
                      <TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                        {t('Нет данных')}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination par={par} onSubmit={submit} base={fields({})} />
          </Box>
        }
      />
    )
  }

  return (
    <Box sx={PAGE_SX}>
      <FlashMessages messages={messages} onDismiss={dismiss} />
      <LoadingBar loading={loading} />
      {top}
      {body}
      <Dialog open={confirm != null} onClose={() => setConfirm(null)}>
        <DialogTitle>{t('Подтверждение')}</DialogTitle>
        <DialogContent>
          <Typography>{confirm?.text}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(null)}>{t('Отмена')}</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              const c = confirm
              setConfirm(null)
              if (c) go(c.fields)
            }}
          >
            {t('Да')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
