import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControl from '@mui/material/FormControl'
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
import TableSortLabel from '@mui/material/TableSortLabel'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useTheme } from '@mui/material/styles'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import DeleteIcon from '@mui/icons-material/Delete'
import RefreshIcon from '@mui/icons-material/Refresh'
import TagIcon from '@mui/icons-material/Tag'
import { useForm } from '../useForm'
import type { FormFields } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import FlashMessages from '../components/FlashMessages'
import LoadingBar from '../components/LoadingBar'
import SearchField from '../components/SearchField'
import NewsDialog, { type NewsUnit } from '../components/NewsDialog'
import { FILL_SX, PAGE_SX } from '../components/layout'
import DateField from '@shared-web/components/DateField'
import { TablePagination, TableToolbar } from '@shared-web/components/TableControls'

// Лента новостей за сутки (бывшие templates/news_board.html + static/js/news_board.js). Сервер (news_board.py)
// отдаёт все новости суток сразу со всеми языковыми вариантами — поиск, фильтры по каналу и теме, язык
// отображения и сортировка работают в браузере. Поля формы: st_date, find_id, delete_id.

interface NewsRow {
  id: number
  name_rss: string | null
  author: string | null
  lang: string | null
  url: string | null
  public_date: string | null
  at_date_time: string | null
  title_ru: string | null
  title_en: string | null
  title_he: string | null
  description_ru: string | null
  description_en: string | null
  description_he: string | null
  themes: string
}

interface Prepared extends NewsRow {
  _time: number
  _dateText: string
  _themes: string[]
  _haystack: string
}

type ShowLang = 'ru' | 'en' | 'he'
type SortKey = 'time' | 'name_rss' | 'title' | 'themes' | 'lang'

const LANG_KEY = 'ohi_news_board_lang'
const SELECTED_KEY = 'ohi_news_board_selected_id'
const ROWS_KEY = 'ohi_news_board_rows'
const ROW_COUNTS = [5, 10, 15, 25, 50, 100] // как в общих TableControls

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key: string, value: string | null) {
  try {
    if (value == null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    /* ignore */
  }
}

/** Время из БД (UTC без зоны) → Date браузера. */
function toLocalDate(iso: string | null): Date | null {
  if (!iso) return null
  const d = new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : iso + 'Z')
  return Number.isNaN(d.getTime()) ? null : d
}

function formatDateTime(d: Date | null): string {
  if (!d) return '—'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function haystack(r: NewsRow): string {
  return [r.title_ru, r.title_en, r.title_he, r.description_ru, r.description_en, r.description_he, r.author, r.name_rss, r.themes, r.id]
    .join('   ')
    .toLowerCase()
}

function prepare(rows: NewsRow[]): Prepared[] {
  return rows.map((r) => {
    const d = toLocalDate(r.at_date_time || r.public_date)
    return {
      ...r,
      _time: d ? d.getTime() : 0,
      _dateText: formatDateTime(d),
      _themes: (r.themes || '')
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      _haystack: haystack(r),
    }
  })
}

function shiftDate(st: string, days: number): string {
  const [y, m, d] = st.split('-').map(Number)
  const dt = new Date(y, m - 1, d + days)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${dt.getFullYear()}-${p(dt.getMonth() + 1)}-${p(dt.getDate())}`
}

export default function NewsBoardPage() {
  const { t, lang: uiLang } = useI18n()
  const theme = useTheme()
  const rtl = theme.direction === 'rtl'
  const { par, messages, loading, error, submit, dismiss } = useForm('news_board')
  const [searchParams, setSearchParams] = useSearchParams()

  const [rows, setRows] = useState<Prepared[]>([])
  const [showLang, setShowLang] = useState<ShowLang>(() => {
    const v = readStorage(LANG_KEY)
    return v === 'ru' || v === 'en' || v === 'he' ? v : uiLang
  })
  const [search, setSearch] = useState('')
  const [channel, setChannel] = useState('')
  const [themeFilter, setThemeFilter] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('time')
  const [sortDir, setSortDir] = useState<1 | -1>(-1)
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})
  const [selectedId, setSelectedId] = useState<number | null>(() => {
    const v = Number(readStorage(SELECTED_KEY))
    return v > 0 ? v : null
  })
  const [openId, setOpenId] = useState<number | null>(null)
  const [gotoOpen, setGotoOpen] = useState(false)
  const [gotoValue, setGotoValue] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const [rowsPerPage, setRowsPerPage] = useState<number>(() => {
    const v = Number(readStorage(ROWS_KEY))
    return ROW_COUNTS.includes(v) ? v : 100
  })
  const scrollTo = useRef<number | null>(null)
  const openAfterFind = useRef<number | null>(null)
  const startDone = useRef(false)

  const { upr } = useAuth()
  const admin = Boolean(upr?.admin)

  const select = (id: number | null) => {
    setSelectedId(id)
    writeStorage(SELECTED_KEY, id == null ? null : String(id))
  }

  // Новые данные суток с сервера
  useEffect(() => {
    if (!par) return
    setRows(prepare((par.data ?? []) as NewsRow[]))
    setExpanded({})
    if (par.select_id) {
      select(par.select_id)
      scrollTo.current = par.select_id
      if (openAfterFind.current === par.select_id) setOpenId(par.select_id)
      openAfterFind.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- только при новом ответе сервера
  }, [par])

  // Старт: ?open_id=<id> (ссылка из чат-бота) — сутки этой новости и открыть её; иначе — показать выбранную ранее
  useEffect(() => {
    if (!par || startDone.current) return
    startDone.current = true
    const open = Number(searchParams.get('open_id'))
    if (open > 0) {
      searchParams.delete('open_id')
      setSearchParams(searchParams, { replace: true })
      openAfterFind.current = open
      submit(fields({ find_id: open }))
      return
    }
    if (selectedId != null) {
      if ((par.data ?? []).some((r: NewsRow) => r.id === selectedId)) scrollTo.current = selectedId
      else submit(fields({ find_id: selectedId }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- один раз после первой загрузки
  }, [par])

  const list = useMemo(() => {
    const q = search.trim().toLowerCase()
    const filtered = rows.filter(
      (r) => (!channel || r.name_rss === channel) && (!themeFilter || r._themes.includes(themeFilter)) && (!q || r._haystack.includes(q)),
    )
    const value = (r: Prepared): string | number => {
      if (sortKey === 'time') return r._time
      if (sortKey === 'title') return (r[`title_${showLang}`] ?? '').toLowerCase()
      return String(r[sortKey] ?? '').toLowerCase()
    }
    return filtered.sort((a, b) => {
      const av = value(a)
      const bv = value(b)
      return av < bv ? -sortDir : av > bv ? sortDir : 0
    })
  }, [rows, search, channel, themeFilter, sortKey, sortDir, showLang])

  // Пагинация — в браузере (сутки приходят целиком): смена фильтров/сортировки/суток — первая страница
  const pageCount = Math.max(1, Math.ceil(list.length / rowsPerPage))
  useEffect(() => setPage(1), [rows, search, channel, themeFilter, sortKey, sortDir, rowsPerPage])
  const pageRows = useMemo(() => list.slice((page - 1) * rowsPerPage, page * rowsPerPage), [list, page, rowsPerPage])
  // Пагинация как в Log — общие TableToolbar / TablePagination; их par собирается здесь, а «отправку» формы
  // (row_count, page) страница обрабатывает сама, без запроса к серверу
  const pagePar = {
    row_count: rowsPerPage,
    page,
    page_count: pageCount,
    count: list.length,
    first: list.length ? (page - 1) * rowsPerPage + 1 : 0,
    last: Math.min(page * rowsPerPage, list.length),
    no_refresh: true,
    no_search: true,
  }
  const onPageSubmit = (f: FormFields) => {
    const rc = Number(f.row_count)
    if (ROW_COUNTS.includes(rc) && rc !== rowsPerPage) {
      setRowsPerPage(rc)
      writeStorage(ROWS_KEY, String(rc))
      return
    }
    const p = Number(f.page)
    if (p >= 1 && p <= pageCount) setPage(p)
  }

  // Прокрутка к выбранной строке после отрисовки; строка на другой странице — сначала перейти на неё
  useEffect(() => {
    const id = scrollTo.current
    if (id == null) return
    const idx = list.findIndex((r) => r.id === id)
    if (idx >= 0) {
      const need = Math.floor(idx / rowsPerPage) + 1
      if (need !== page) {
        setPage(need)
        return // прокрутка — после отрисовки нужной страницы
      }
    }
    scrollTo.current = null
    requestAnimationFrame(() => document.getElementById(`nb_row_${id}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }))
  })

  if (error) return <Typography color="error">{error}</Typography>
  if (!par) return <LoadingBar loading />

  function fields(extra: FormFields): FormFields {
    return { st_date: par?.st_date ?? '', ...extra }
  }

  const setSort = (key: SortKey) => {
    if (key === sortKey) setSortDir((d) => (d === 1 ? -1 : 1))
    else {
      setSortKey(key)
      setSortDir(key === 'time' ? -1 : 1)
    }
  }

  const sortHead = (key: SortKey, label: string, sx?: object) => (
    <TableCell sx={sx} sortDirection={sortKey === key ? (sortDir === 1 ? 'asc' : 'desc') : false}>
      <TableSortLabel active={sortKey === key} direction={sortKey === key && sortDir === 1 ? 'asc' : 'desc'} onClick={() => setSort(key)}>
        {label}
      </TableSortLabel>
    </TableCell>
  )

  const goto = () => {
    const v = gotoValue.trim()
    if (!/^\d+$/.test(v)) return
    setGotoOpen(false)
    submit(fields({ find_id: v }))
  }

  const patchRow = (unit: NewsUnit) => {
    setRows((rs) =>
      rs.map((r) => {
        if (r.id !== unit.id) return r
        const next: NewsRow = { ...r }
        for (const l of ['ru', 'en', 'he'] as const) {
          if (unit[`title_${l}`] !== undefined) next[`title_${l}`] = unit[`title_${l}`]
          if (unit[`description_${l}`] !== undefined) next[`description_${l}`] = unit[`description_${l}`]
        }
        return { ...r, ...next, _haystack: haystack(next) }
      }),
    )
  }

  const PrevIcon = rtl ? ChevronRightIcon : ChevronLeftIcon
  const NextIcon = rtl ? ChevronLeftIcon : ChevronRightIcon
  const total = rows.length

  return (
    <Box sx={PAGE_SX}>
      <FlashMessages messages={messages} onDismiss={dismiss} />
      <LoadingBar loading={loading} />

      <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5, flexShrink: 0 }}>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <IconButton size="small" title={t('Предыдущий день')} onClick={() => submit(fields({ st_date: shiftDate(par.st_date, -1) }))}>
              <PrevIcon />
            </IconButton>
            <DateField value={par.st_date} required width={160} onCommit={(v) => submit(fields({ st_date: v }))} />
            <IconButton size="small" title={t('Следующий день')} onClick={() => submit(fields({ st_date: shiftDate(par.st_date, 1) }))}>
              <NextIcon />
            </IconButton>
            {par.st_date !== par.today && (
              <Button size="small" onClick={() => submit(fields({ st_date: par.today }))}>
                {t('Сегодня')}
              </Button>
            )}
          </Box>
          <SearchField
            size="small"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onClear={() => setSearch('')}
            label={t('Поиск')}
            title={t('Поиск по заголовку, описанию, автору, каналу...')}
            sx={{ width: 280 }}
          />
          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel id="nb_channel">{t('Канал')}</InputLabel>
            <Select labelId="nb_channel" label={t('Канал')} value={channel} onChange={(e) => setChannel(e.target.value)}>
              <MenuItem value="">{t('Все каналы')}</MenuItem>
              {(par.list_rss ?? []).map((s: string) => (
                <MenuItem key={s} value={s}>
                  {s}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel id="nb_theme">{t('Тема')}</InputLabel>
            <Select labelId="nb_theme" label={t('Тема')} value={themeFilter} onChange={(e) => setThemeFilter(e.target.value)}>
              <MenuItem value="">{t('Все темы')}</MenuItem>
              {(par.themes ?? []).map((s: string) => (
                <MenuItem key={s} value={s}>
                  {s}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 90 }}>
            <InputLabel id="nb_lang">{t('Язык')}</InputLabel>
            <Select
              labelId="nb_lang"
              label={t('Язык')}
              title={t('Язык отображения новостей')}
              value={showLang}
              onChange={(e) => {
                const v = e.target.value as ShowLang
                setShowLang(v)
                writeStorage(LANG_KEY, v)
              }}
            >
              {(['ru', 'en', 'he'] as const).map((l) => (
                <MenuItem key={l} value={l}>
                  {l.toUpperCase()}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <IconButton size="small" title={t('Обновить')} onClick={() => submit(fields({}))}>
            <RefreshIcon />
          </IconButton>
          <IconButton size="small" title={t('Перейти к новости по ID')} onClick={() => setGotoOpen(true)}>
            <TagIcon />
          </IconButton>
          {par.not_found ? (
            <Typography variant="body2" color="warning.main">
              {t('Новость с ID={id} не найдена', { id: par.not_found })}
            </Typography>
          ) : null}
          <Typography variant="body2" color="text.secondary">
            {t('Показано {n} из {total}', { n: list.length, total })}
            {total >= (par.max_rows ?? 3000) ? ` (${t('показаны первые {n}', { n: par.max_rows })})` : ''}
          </Typography>
        </Box>
        <Box sx={{ mt: 1.5 }}>
          <TableToolbar par={pagePar} onSubmit={onPageSubmit} hideSearch hideSort />
        </Box>
      </Paper>

      <TableContainer component={Paper} variant="outlined" sx={FILL_SX}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              {sortHead('time', t('Дата/время'), { width: 140 })}
              {sortHead('name_rss', t('Канал / автор'), { width: 180 })}
              {sortHead('title', t('Заголовок / описание'))}
              {sortHead('themes', t('Темы'), { width: 170 })}
              {sortHead('lang', t('Язык'), { width: 70 })}
              {admin && <TableCell sx={{ width: 44 }} />}
            </TableRow>
          </TableHead>
          <TableBody>
            {pageRows.map((r) => {
              const title = r[`title_${showLang}`] || r.title_ru || ''
              const desc = r[`description_${showLang}`] || r.description_ru || ''
              const dir = showLang === 'he' ? 'rtl' : 'ltr'
              return (
                <TableRow key={r.id} id={`nb_row_${r.id}`} hover selected={r.id === selectedId}>
                  <TableCell sx={{ whiteSpace: 'nowrap', verticalAlign: 'top' }}>
                    {r._dateText}
                    <Typography variant="caption" color="text.secondary" component="div">
                      #{r.id}
                    </Typography>
                  </TableCell>
                  <TableCell sx={{ verticalAlign: 'top' }}>
                    {r.name_rss}
                    {r.author && (
                      <Typography variant="caption" color="text.secondary" component="div">
                        {r.author}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell sx={{ verticalAlign: 'top' }} dir={dir}>
                    <Link
                      component="button"
                      underline="hover"
                      sx={{ fontWeight: 600, textAlign: 'start', fontSize: 'inherit' }}
                      onClick={() => {
                        select(r.id)
                        setOpenId(r.id)
                      }}
                    >
                      {title || t('(без заголовка)')}
                    </Link>
                    {desc && (
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        title={expanded[r.id] ? undefined : t('Показать описание полностью')}
                        onClick={() => setExpanded((e) => ({ ...e, [r.id]: !e[r.id] }))}
                        sx={{
                          cursor: 'pointer',
                          mt: 0.25,
                          ...(expanded[r.id]
                            ? { whiteSpace: 'pre-wrap' }
                            : { display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }),
                        }}
                      >
                        {desc}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell sx={{ verticalAlign: 'top' }}>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                      {r._themes.map((s) => (
                        <Chip key={s} size="small" label={s} color="secondary" variant="outlined" onClick={() => setThemeFilter(s)} />
                      ))}
                    </Box>
                  </TableCell>
                  <TableCell sx={{ verticalAlign: 'top' }}>{r.lang && <Chip size="small" label={r.lang} />}</TableCell>
                  {admin && (
                    <TableCell sx={{ verticalAlign: 'top' }}>
                      <IconButton size="small" color="error" title={t('Удалить новость')} onClick={() => setConfirmDelete(r.id)}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  )}
                </TableRow>
              )
            })}
            {!list.length && !loading && (
              <TableRow>
                <TableCell colSpan={admin ? 6 : 5} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                  {t('Нет новостей за выбранный день / по заданным фильтрам')}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination par={pagePar} onSubmit={onPageSubmit} />

      <NewsDialog
        newsId={openId}
        lang={showLang}
        onChanged={patchRow}
        onClose={() => {
          if (openId != null) scrollTo.current = openId
          setOpenId(null)
        }}
      />

      <Dialog open={gotoOpen} onClose={() => setGotoOpen(false)}>
        <DialogTitle>{t('Перейти к новости по ID')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label={t('ID новости')}
            value={gotoValue}
            onChange={(e) => setGotoValue(e.target.value.replace(/\D/g, ''))}
            onKeyDown={(e) => e.key === 'Enter' && goto()}
            slotProps={{ htmlInput: { inputMode: 'numeric' } }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setGotoOpen(false)}>{t('Отмена')}</Button>
          <Button variant="contained" disabled={!gotoValue} onClick={goto}>
            {t('Перейти')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={confirmDelete != null} onClose={() => setConfirmDelete(null)}>
        <DialogTitle>{t('Удалить новость')}</DialogTitle>
        <DialogContent>
          <Typography>{t('Удалить новость с ID={id} и её статью?', { id: confirmDelete ?? '' })}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDelete(null)}>{t('Отмена')}</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              const id = confirmDelete
              setConfirmDelete(null)
              if (id != null) submit(fields({ delete_id: id }))
            }}
          >
            {t('Удалить')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
