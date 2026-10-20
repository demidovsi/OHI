import { useEffect, useState } from 'react'
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
import Typography from '@mui/material/Typography'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import ReplayIcon from '@mui/icons-material/Replay'
import SaveIcon from '@mui/icons-material/Save'
import { useForm } from '../useForm'
import type { FormFields } from '../api'
import { useAuth } from '../auth'
import { useT } from '../i18n'
import FlashMessages from '../components/FlashMessages'
import LoadingBar from '../components/LoadingBar'
import SplitPane from '../components/SplitPane'
import { COLUMN_SX, FILL_SX, PAGE_SX } from '../components/layout'
import { TablePagination, TableToolbar, baseFields } from '@shared-web/components/TableControls'

// Новостные ленты (бывший templates/rss.html, бэкенд rss.py): список лент и — для администратора — правка ленты
// справа. Поля и кнопки старой формы: corr_obj_<id>, del_obj_<id>, new_object, nsi_save, nsi_refresh,
// filter_language; поля ленты sh_name, url, lang, description, categories, type_rss, type_article, stop.

interface RssRow {
  id: number
  sh_name: string | null
  url: string | null
  lang: string | null
  description: string | null
  type_rss: string | null
  type_article: string | null
  categories: string | null
  stop: boolean | null
}

const UNIT_KEYS = ['sh_name', 'url', 'lang', 'description', 'categories', 'type_rss', 'type_article'] as const
type UnitKey = (typeof UNIT_KEYS)[number]
type Unit = Record<UnitKey, string> & { stop: boolean }

const str = (v: unknown) => (v == null || v === 'None' ? '' : String(v))

function unitFrom(u: Record<string, unknown> | undefined, suffix = ''): Unit {
  const r = Object.fromEntries(UNIT_KEYS.map((k) => [k, str(u?.[k + suffix])])) as Record<UnitKey, string>
  return { ...r, stop: Boolean(u?.['stop' + suffix]) }
}

export default function RssPage() {
  const t = useT()
  const { upr } = useAuth()
  const admin = Boolean(upr?.admin)
  const { par, messages, loading, error, submit, dismiss } = useForm('rss')
  const [unit, setUnit] = useState<Unit>(unitFrom(undefined))
  const [confirmDelete, setConfirmDelete] = useState<RssRow | null>(null)

  useEffect(() => {
    if (par) setUnit(unitFrom(par.unit))
  }, [par])

  if (error) return <Typography color="error">{error}</Typography>
  if (!par) return <LoadingBar loading />

  const init = unitFrom(par.unit, '_init')
  const changed = UNIT_KEYS.some((k) => unit[k].trim() !== init[k].trim()) || unit.stop !== init.stop
  const editing = par.unit && Object.keys(par.unit).length > 0
  const required = !unit.sh_name.trim() || !unit.url.trim()

  const fields = (extra: FormFields): FormFields => ({
    ...baseFields(par),
    filter_language: par.filter_language ?? '',
    ...unit,
    stop: unit.stop ? 'on' : undefined,
    ...extra,
  })

  const rows: RssRow[] = par.data ?? []
  const set = (k: UnitKey) => (e: { target: { value: string } }) => setUnit((u) => ({ ...u, [k]: e.target.value }))

  const table = (
    <Box sx={COLUMN_SX}>
      <TableContainer component={Paper} variant="outlined" sx={FILL_SX}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>{t('ID ленты')}</TableCell>
              <TableCell>{t('Название ленты')}</TableCell>
              <TableCell>{t('URL ленты')}</TableCell>
              <TableCell>{t('Язык')}</TableCell>
              <TableCell>{t('Описание сайта')}</TableCell>
              <TableCell>{t('Тип ленты')}</TableCell>
              <TableCell>{t('Тип статьи')}</TableCell>
              <TableCell>{t('Категории')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id} hover selected={r.id === par.select_id}>
                <TableCell sx={{ whiteSpace: 'nowrap', verticalAlign: 'top' }}>
                  {r.id}
                  {admin && (
                    <IconButton size="small" color="error" title={t('Удаление новостной ленты и всех ее новостей из БД')} onClick={() => setConfirmDelete(r)}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  )}
                </TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>
                  {admin ? (
                    <Link component="button" underline="hover" sx={{ textAlign: 'start', fontSize: 'inherit' }} title={t('Поместить данные в правую часть для коррекции')} onClick={() => submit(fields({ ['corr_obj_' + r.id]: 1 }))}>
                      {r.sh_name}
                    </Link>
                  ) : (
                    r.sh_name
                  )}
                </TableCell>
                <TableCell sx={{ verticalAlign: 'top', wordBreak: 'break-all', ...(r.stop && { color: 'warning.main', textDecoration: 'line-through' }) }}>
                  {r.url}
                </TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>{r.lang}</TableCell>
                <TableCell sx={{ verticalAlign: 'top', color: 'secondary.main', maxWidth: 280 }}>
                  <Box sx={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }} title={r.description ?? ''}>
                    {r.description}
                  </Box>
                </TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>{r.type_rss}</TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>{r.type_article}</TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>{r.categories}</TableCell>
              </TableRow>
            ))}
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

  const editor = (
    <Paper variant="outlined" sx={{ flex: '1 1 0', minHeight: 0, overflow: 'auto', p: 1.5, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
        <Button size="small" color="secondary" startIcon={<AddIcon />} title={t('Сбросить параметры для формирования новой новостной ленты')} onClick={() => submit(fields({ new_object: 1 }))}>
          {t('Новый объект')}
        </Button>
        {changed && (
          <>
            <Button size="small" variant="contained" startIcon={<SaveIcon />} disabled={required} title={t('Записать изменения по новостной ленте в базу данных')} onClick={() => submit(fields({ nsi_save: 1 }))}>
              {t('Записать')}
            </Button>
            <Button size="small" startIcon={<ReplayIcon />} title={t('Отменить сделанные изменения в новостной ленте')} onClick={() => setUnit(init)}>
              {t('Восстановить')}
            </Button>
          </>
        )}
      </Box>
      {!editing ? (
        <Typography variant="body2" color="text.secondary">
          {t('Выберите ленту в таблице или создайте новую')}
        </Typography>
      ) : (
        <>
          {par.unit.id ? (
            <Typography variant="body2" color="error">
              {t('ID ленты')}={par.unit.id}
            </Typography>
          ) : null}
          <TextField label={t('Имя новостной ленты')} value={unit.sh_name} onChange={set('sh_name')} required error={!unit.sh_name.trim()} />
          <TextField label={t('Адрес новостной ленты')} value={unit.url} onChange={set('url')} required error={!unit.url.trim()} multiline minRows={2} slotProps={{ htmlInput: { dir: 'ltr' } }} />
          <FormControl>
            <InputLabel id="rss_lang">{t('Исходный язык')}</InputLabel>
            <Select labelId="rss_lang" label={t('Исходный язык')} value={unit.lang} onChange={(e) => setUnit((u) => ({ ...u, lang: e.target.value }))}>
              {(par.languages ?? []).map((l: string) => (
                <MenuItem key={l} value={l}>
                  {l || '—'}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField label={t('Описание сайта')} value={unit.description} onChange={set('description')} multiline minRows={3} />
          <TextField label={t('Тип ленты новостей')} value={unit.type_rss} onChange={set('type_rss')} />
          <TextField label={t('Категории')} value={unit.categories} onChange={set('categories')} multiline minRows={2} title={t('Перечень категорий новостей через запятую')} />
          <TextField label={t('Тип статьи')} value={unit.type_article} onChange={set('type_article')} />
          <FormControlLabel
            control={<Checkbox checked={unit.stop} onChange={(e) => setUnit((u) => ({ ...u, stop: e.target.checked }))} />}
            label={t('Останов работы с новостной лентой')}
          />
        </>
      )}
    </Paper>
  )

  return (
    <Box sx={PAGE_SX}>
      <FlashMessages messages={messages} onDismiss={dismiss} />
      <LoadingBar loading={loading} />

      <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5, flexShrink: 0 }}>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center', mb: 1.5 }}>
          <Typography variant="body2">
            {t('Останов работы с новостной лентой')} ={' '}
            <Box component="b" sx={{ color: 'secondary.main' }}>
              {par.count_stop ?? 0}
            </Box>
          </Typography>
          <FormControl sx={{ minWidth: 140 }}>
            <InputLabel id="rss_filter_lang">{t('Исходный язык')}</InputLabel>
            <Select
              labelId="rss_filter_lang"
              label={t('Исходный язык')}
              title={t('Язык новостной ленты')}
              value={par.filter_language ?? ''}
              onChange={(e) => submit(fields({ filter_language: e.target.value, page: 1 }))}
            >
              {(par.languages ?? []).map((l: string) => (
                <MenuItem key={l} value={l}>
                  {l || t('Все')}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
        <TableToolbar par={par} onSubmit={submit} base={fields({})} />
      </Paper>

      {admin ? <SplitPane storageKey="rss" first={table} second={editor} defaultSize="65%" /> : table}

      <Dialog open={confirmDelete != null} onClose={() => setConfirmDelete(null)}>
        <DialogTitle>{t('Подтверждение удаления новостной ленты')}</DialogTitle>
        <DialogContent>
          <Typography>
            {t('Действительно удалить новостную ленту [{name}] с ID={id} и все ее новости?', {
              name: confirmDelete?.sh_name ?? '',
              id: confirmDelete?.id ?? '',
            })}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDelete(null)}>{t('Отмена')}</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              const r = confirmDelete
              setConfirmDelete(null)
              if (r) submit(fields({ ['del_obj_' + r.id]: 1 }))
            }}
          >
            {t('Удалить')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
