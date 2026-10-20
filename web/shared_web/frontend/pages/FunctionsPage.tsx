import { useEffect, useMemo, useState } from 'react'
import { alpha, useTheme } from '@mui/material/styles'
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
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import RefreshIcon from '@mui/icons-material/Refresh'
import ReplayIcon from '@mui/icons-material/Replay'
import SaveIcon from '@mui/icons-material/Save'
import UnfoldLessIcon from '@mui/icons-material/UnfoldLess'
import UnfoldMoreIcon from '@mui/icons-material/UnfoldMore'
import EditNoteIcon from '@mui/icons-material/EditNote'
import { useForm } from '@app/useForm'
import type { FormFields } from '@app/api'
import FlashMessages from '@app/components/FlashMessages'
import { useT } from '@app/i18n'
import { FILL_SX, PAGE_SX } from '@app/components/layout'
import LoadingBar from '@app/components/LoadingBar'

interface FnRow {
  id: number | string
  function: number
  code: string
  value: string | null
  sh_name: string | null
  is_number: boolean | number
  name_function: string
  description?: string | null
  is_placeholder?: boolean
  /** Секрет (токен, ключ): сервер отдаёт маску, новое значение шифрует при сохранении (shared/secret_params.py). */
  is_secret?: boolean
}

interface FnDef {
  id: number
  sh_name: string
  description?: string | null
}

const isNum = (v: boolean | number | undefined) => v === true || v === 1

// Раскрытые функции (первый уровень таблицы) — запоминаются в браузере
const OPEN_KEY = 'functions_open'
function readOpen(): Record<number, boolean> {
  try {
    return JSON.parse(localStorage.getItem(OPEN_KEY) ?? '{}') as Record<number, boolean>
  } catch {
    return {}
  }
}
const str = (v: string | null | undefined) => v ?? ''

function paramChanged(r: FnRow, init: FnRow | undefined): boolean {
  if (!init) return false
  return str(r.code) !== str(init.code) || str(r.value) !== str(init.value) || str(r.sh_name) !== str(init.sh_name) || isNum(r.is_number) !== isNum(init.is_number)
}

function headerChanged(r: FnRow, init: FnRow | undefined): boolean {
  if (!init) return false
  return str(r.name_function) !== str(init.name_function) || str(r.description) !== str(init.description)
}

// Страница «Параметры функций» — аналог templates/functions/functions.html +
// include/functions_table.html, functions_options.html + static/js/functions.js.
// Поля старой формы: val~<id>, code~<id>, sh_name~<id>, is_number~<id>,
// function_name~<fid>, function_description~<fid>, name_function, description_function,
// dlg_select_function, dlg_code_parameter, dlg_is_number_parameter, dlg_comment_parameter;
// кнопки refresh, save, create_function, create_parameter, corr_function_<fid>,
// delete_function_<fid>, corr_parameter_<id>, delete_parameter_<id>.
export default function FunctionsPage() {
  const t = useT()
  const theme = useTheme()
  const { par, messages, loading, error, submit, dismiss } = useForm('functions')
  const [rows, setRows] = useState<FnRow[]>([])
  const [dlgFn, setDlgFn] = useState(false)
  const [dlgParam, setDlgParam] = useState(false)
  const [newFn, setNewFn] = useState({ name_function: '', description_function: '' })
  const [newParam, setNewParam] = useState({ dlg_select_function: '0', dlg_code_parameter: '', dlg_comment_parameter: '', dlg_is_number_parameter: false })
  const [pending, setPending] = useState<'function' | 'parameter' | null>(null)
  const [open, setOpenState] = useState<Record<number, boolean>>(readOpen)
  const [onlyChanged, setOnlyChanged] = useState(false)
  const setOpen = (next: Record<number, boolean>) => {
    setOpenState(next)
    try {
      localStorage.setItem(OPEN_KEY, JSON.stringify(next))
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    if (!par) return
    setRows((par.data ?? []).map((r: FnRow) => ({ ...r })))
    setNewFn({ name_function: par.name_function ?? '', description_function: par.description_function ?? '' })
  }, [par])

  // После ответа сервера: закрыть диалог создания, если не было предупреждений (как applyResponse в functions.js).
  useEffect(() => {
    if (!pending || !par) return
    const hadWarning = messages.some((m) => m[0] === 'warning')
    if (!hadWarning) {
      if (pending === 'function') setDlgFn(false)
      if (pending === 'parameter') {
        setDlgParam(false)
        setNewParam({ dlg_select_function: '0', dlg_code_parameter: '', dlg_comment_parameter: '', dlg_is_number_parameter: false })
      }
    }
    setPending(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [par])

  const initById = useMemo(() => {
    const m = new Map<string, FnRow>()
    for (const r of (par?.data_init ?? []) as FnRow[]) m.set(String(r.id), r)
    return m
  }, [par])

  if (error) return <Typography color="error">{error}</Typography>
  if (!par)
    return (
      <Box sx={PAGE_SX}>
        <LoadingBar loading />
      </Box>
    )

  const functions: FnDef[] = par.functions ?? []
  const existingIdents = new Set(functions.map((f) => f.sh_name).filter(Boolean))

  const fields = (extra: FormFields): FormFields => {
    const f: FormFields = {
      scroll: 0,
      name_function: newFn.name_function,
      description_function: newFn.description_function,
      dlg_select_function: newParam.dlg_select_function,
      dlg_code_parameter: newParam.dlg_code_parameter,
      dlg_comment_parameter: newParam.dlg_comment_parameter,
      dlg_is_number_parameter: newParam.dlg_is_number_parameter ? 'on' : undefined,
    }
    for (const r of rows) {
      if (r.name_function) {
        f[`function_name~${r.function}`] = r.name_function
        f[`function_description~${r.function}`] = str(r.description)
      }
      if (!r.is_placeholder) {
        f[`val~${r.id}`] = str(r.value)
        f[`code~${r.id}`] = r.code
        f[`sh_name~${r.id}`] = str(r.sh_name)
        if (isNum(r.is_number)) f[`is_number~${r.id}`] = 'on'
      }
    }
    return { ...f, ...extra }
  }

  // Строки с незаписанными изменениями и группы (функции): число параметров, есть ли изменения
  const changedRow = (r: FnRow) => {
    const init = initById.get(String(r.id))
    return Boolean((r.name_function && headerChanged(r, init)) || (!r.is_placeholder && paramChanged(r, init)))
  }
  const groups = new Map<number, { params: number; changed: boolean; paramsChanged: number }>()
  let changedCount = 0
  for (const r of rows) {
    const g = groups.get(r.function) ?? { params: 0, changed: false, paramsChanged: 0 }
    if (!r.is_placeholder) g.params += 1
    if (changedRow(r)) {
      g.changed = true
      changedCount += 1
    }
    if (!r.is_placeholder && paramChanged(r, initById.get(String(r.id)))) g.paramsChanged += 1
    groups.set(r.function, g)
  }
  const anyChanged = changedCount > 0
  const setAllOpen = (value: boolean) => setOpen(Object.fromEntries([...groups.keys()].map((fid) => [fid, value])))

  const updateRow = (id: FnRow['id'], patch: Partial<FnRow>) => setRows(rows.map((r) => (String(r.id) === String(id) ? { ...r, ...patch } : r)))

  const restoreParam = (r: FnRow) => {
    const init = initById.get(String(r.id))
    if (init) updateRow(r.id, { code: init.code, value: init.value, sh_name: init.sh_name, is_number: init.is_number })
  }
  const restoreHeader = (r: FnRow) => {
    const init = initById.get(String(r.id))
    if (init) updateRow(r.id, { name_function: init.name_function, description: init.description })
  }
  const restoreAll = () => setRows((par.data ?? []).map((r: FnRow) => ({ ...r })))

  const onRefresh = () => {
    if (anyChanged && !window.confirm(t('Есть несохранённые изменения. Перечитать данные и потерять их?'))) return
    submit(fields({ refresh: 1 }))
  }

  const toggleIsNumber = (r: FnRow, checked: boolean) => {
    if (checked && str(r.value) !== '' && Number.isNaN(Number(r.value))) {
      window.alert(t('Значение "{value}" не является числом. Исправьте значение перед переключением.', { value: str(r.value) }))
      return
    }
    updateRow(r.id, { is_number: checked ? 1 : 0 })
  }

  const fnNameValid = newFn.name_function.trim() !== '' && !existingIdents.has(newFn.name_function.trim())
  const paramValid = newParam.dlg_code_parameter.trim() !== '' && newParam.dlg_select_function !== '0' && newParam.dlg_select_function !== ''

  return (
    <Box sx={PAGE_SX}>
      <FlashMessages messages={messages} onDismiss={dismiss} />
      <LoadingBar loading={loading} />

      <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5 }}>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
          <Typography variant="h6" component="span">
            {t('Управление')}{' '}
            <Button
              color="secondary"
              startIcon={<RefreshIcon />}
              sx={{ textTransform: 'none', fontSize: 'inherit', textDecoration: 'underline' }}
              title={t('Все заново перечитать (с потерей не записанных изменений)')}
              onClick={onRefresh}
            >
              {t('Параметры микросервисов')}
            </Button>
          </Typography>
          {anyChanged && (
            <>
              <Button color="error" startIcon={<SaveIcon />} sx={{ textTransform: 'none' }} title={t('Записать информацию в базу данных')} onClick={() => submit(fields({ save: 1 }))}>
                {t('Записать')}
              </Button>
              <Button color="secondary" startIcon={<ReplayIcon />} sx={{ textTransform: 'none' }} title={t('Отменить все сделанные изменения')} onClick={restoreAll}>
                {t('Восстановить')}
              </Button>
            </>
          )}
          <Box sx={{ flexGrow: 1 }} />
          <Tooltip title={t('Развернуть все функции')}>
            <IconButton onClick={() => setAllOpen(true)} aria-label={t('Развернуть все функции')}>
              <UnfoldMoreIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title={t('Свернуть все функции')}>
            <IconButton onClick={() => setAllOpen(false)} aria-label={t('Свернуть все функции')}>
              <UnfoldLessIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title={t('Показать только строки с незаписанными изменениями')}>
            <span>
              <ToggleButton
                value="changed"
                size="small"
                selected={onlyChanged}
                disabled={!anyChanged && !onlyChanged}
                onChange={() => setOnlyChanged(!onlyChanged)}
                sx={{ textTransform: 'none', gap: 0.5 }}
              >
                <EditNoteIcon fontSize="small" />
                {t('Только изменённые')}
                {changedCount ? ` (${changedCount})` : ''}
              </ToggleButton>
            </span>
          </Tooltip>
          <Button variant="outlined" startIcon={<AddIcon />} title={t('Создать новую функцию')} onClick={() => setDlgFn(true)}>
            {t('Новая функция')}
          </Button>
          <Button variant="outlined" startIcon={<AddIcon />} title={t('Создать новый параметр функции')} onClick={() => setDlgParam(true)}>
            {t('Новый параметр')}
          </Button>
        </Box>
      </Paper>

      {/* Редактируемые поля таблицы — без подчёркивания, с лёгким фоном (в фокусе — чуть темнее) */}
      <TableContainer
        component={Paper}
        variant="outlined"
        sx={{
          ...FILL_SX,
          '& tbody .MuiInput-root::before, & tbody .MuiInput-root::after': { display: 'none' },
          '& tbody .MuiInputBase-root': { bgcolor: alpha(theme.palette.primary.main, 0.06), borderRadius: '4px', px: 0.75, py: 0.25 },
          '& tbody .MuiInputBase-root.Mui-focused': { bgcolor: alpha(theme.palette.primary.main, 0.14) },
        }}
      >
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell title={t('Код параметра')} sx={{ width: '15%', minWidth: 140 }}>
                {t('Код')}
              </TableCell>
              <TableCell title={t('Значение параметра')} sx={{ width: '25%', minWidth: 200 }}>
                {t('Значение')}
              </TableCell>
              <TableCell title={t('Признак числового значения')} align="center">
                {t('Число')}
              </TableCell>
              {/* комментарий — самая широкая колонка */}
              <TableCell title={t('Комментарий к параметру')} sx={{ width: '40%', minWidth: 260 }}>
                {t('Комментарий')}
              </TableCell>
              <TableCell title={t('Действия со строкой')} sx={{ whiteSpace: 'nowrap' }}>
                {t('Действия')}
              </TableCell>
              <TableCell align="right">ID</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => {
              const init = initById.get(String(r.id))
              const hChanged = headerChanged(r, init)
              const pChanged = paramChanged(r, init)
              const group = groups.get(r.function) ?? { params: 0, changed: false, paramsChanged: 0 }
              if (onlyChanged && !group.changed) return null
              // «только изменённые» — группа раскрыта, видны только изменённые параметры
              const isOpen = onlyChanged || Boolean(open[r.function])
              const showParam = isOpen && !r.is_placeholder && (!onlyChanged || pChanged)
              return (
                <FragmentRows
                  key={String(r.id)}
                  r={r}
                  hChanged={hChanged}
                  pChanged={pChanged}
                  isOpen={isOpen}
                  showParam={showParam}
                  paramCount={group.params}
                  paramsChanged={group.paramsChanged}
                  onToggle={() => setOpen({ ...open, [r.function]: !open[r.function] })}
                  updateRow={updateRow}
                  restoreHeader={restoreHeader}
                  restoreParam={restoreParam}
                  toggleIsNumber={toggleIsNumber}
                  submitFields={(extra) => submit(fields(extra))}
                />
              )
            })}
            {onlyChanged && !anyChanged && (
              <TableRow>
                <TableCell colSpan={6} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                  {t('Незаписанных изменений нет')}
                </TableCell>
              </TableRow>
            )}
            {!rows.length && !loading && (
              <TableRow>
                <TableCell colSpan={6} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                  {t('Нет данных')}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Диалог «Новая функция» */}
      <Dialog open={dlgFn} onClose={() => setDlgFn(false)} maxWidth="xs" fullWidth>
        <LoadingBar loading={loading} inDialog />
        <DialogTitle>{t('Новая функция')}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
          <TextField
            label="Ident"
            autoFocus
            value={newFn.name_function}
            error={existingIdents.has(newFn.name_function.trim()) && newFn.name_function.trim() !== ''}
            helperText={existingIdents.has(newFn.name_function.trim()) && newFn.name_function.trim() !== '' ? t('Функция с таким ident уже существует') : ' '}
            onChange={(e) => setNewFn({ ...newFn, name_function: e.target.value })}
          />
          <TextField label="Description" value={newFn.description_function} onChange={(e) => setNewFn({ ...newFn, description_function: e.target.value })} />
        </DialogContent>
        <DialogActions>
          <Button color="inherit" onClick={() => setDlgFn(false)}>
            {t('Отмена')}
          </Button>
          <Button
            startIcon={<SaveIcon />}
            disabled={!fnNameValid}
            title={t('Записать функцию')}
            onClick={() => {
              setPending('function')
              submit(fields({ create_function: 1 }))
            }}
          >
            {t('Сохранить')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Диалог «Новый параметр» */}
      <Dialog open={dlgParam} onClose={() => setDlgParam(false)} maxWidth="xs" fullWidth>
        <LoadingBar loading={loading} inDialog />
        <DialogTitle>{t('Новый параметр')}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
          <FormControl>
            <InputLabel id="dlg_select_function_label">{t('Функция')}</InputLabel>
            <Select
              labelId="dlg_select_function_label"
              label={t('Функция')}
              value={newParam.dlg_select_function}
              onChange={(e) => setNewParam({ ...newParam, dlg_select_function: String(e.target.value) })}
            >
              {functions.map((f) => (
                <MenuItem key={f.id} value={String(f.id)}>
                  {f.sh_name || '—'}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField label="Code" value={newParam.dlg_code_parameter} onChange={(e) => setNewParam({ ...newParam, dlg_code_parameter: e.target.value })} />
          <FormControlLabel
            title={t('Признак: величина параметра число или строка')}
            control={<Checkbox size="small" checked={newParam.dlg_is_number_parameter} onChange={(e) => setNewParam({ ...newParam, dlg_is_number_parameter: e.target.checked })} />}
            label={t('Число')}
          />
          <TextField label={t('Комментарий')} value={newParam.dlg_comment_parameter} onChange={(e) => setNewParam({ ...newParam, dlg_comment_parameter: e.target.value })} />
        </DialogContent>
        <DialogActions>
          <Button color="inherit" onClick={() => setDlgParam(false)}>
            {t('Отмена')}
          </Button>
          <Button
            startIcon={<SaveIcon />}
            disabled={!paramValid}
            title={t('Записать параметр')}
            onClick={() => {
              setPending('parameter')
              submit(fields({ create_parameter: 1 }))
            }}
          >
            {t('Сохранить')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

interface RowsProps {
  r: FnRow
  hChanged: boolean
  pChanged: boolean
  isOpen: boolean
  showParam: boolean
  paramCount: number
  /** Сколько параметров функции с незаписанными изменениями (значок в строке функции — и при изменении самой строки). */
  paramsChanged: number
  onToggle: () => void
  updateRow: (id: FnRow['id'], patch: Partial<FnRow>) => void
  restoreHeader: (r: FnRow) => void
  restoreParam: (r: FnRow) => void
  toggleIsNumber: (r: FnRow, checked: boolean) => void
  submitFields: (extra: FormFields) => void
}

// Одна запись par.data = (опционально) строка-заголовок функции + строка параметра.
function FragmentRows({ r, hChanged, pChanged, isOpen, showParam, paramCount, paramsChanged, onToggle, updateRow, restoreHeader, restoreParam, toggleIsNumber, submitFields }: RowsProps) {
  const t = useT()
  const numeric = isNum(r.is_number)
  return (
    <>
      {r.name_function && (
        <TableRow sx={{ bgcolor: 'action.hover' }}>
          <TableCell colSpan={3}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <IconButton
              size="small"
              color="primary"
              title={isOpen ? t('Свернуть параметры функции') : t('Развернуть параметры функции')}
              onClick={onToggle}
              disabled={!paramCount}
              sx={{ fontSize: 12, width: 28 }}
            >
              {isOpen ? '▼' : '▶'}
            </IconButton>
            <Box component="span" title={t('Число параметров функции')} sx={{ color: 'secondary.main', fontSize: 12, minWidth: 22 }}>
              {paramCount}
            </Box>
            {/* незаписанные изменения в строке функции или в её параметрах — видно и у свёрнутой функции */}
            <Box
              component="span"
              title={hChanged || paramsChanged ? t('Незаписанные изменения: {n}', { n: paramsChanged + (hChanged ? 1 : 0) }) : undefined}
              sx={{ width: 22, display: 'inline-flex', color: 'warning.main' }}
            >
              {(hChanged || paramsChanged > 0) && <EditNoteIcon fontSize="small" />}
            </Box>
            <TextField
              fullWidth
              variant="standard"
              value={r.name_function}
              title={t('Имя функции')}
              onChange={(e) => updateRow(r.id, { name_function: e.target.value })}
              slotProps={{ input: { sx: { color: 'error.main', fontWeight: 700 } } }}
            />
            </Box>
          </TableCell>
          <TableCell>
            <TextField
              fullWidth
              variant="standard"
              multiline
              value={str(r.description)}
              title={t('Описание функции')}
              onChange={(e) => updateRow(r.id, { description: e.target.value })}
              slotProps={{ input: { sx: { color: 'error.main' } } }}
            />
          </TableCell>
          <TableCell sx={{ whiteSpace: 'nowrap' }}>
            {hChanged && (
              <>
                <IconButton size="small" color="error" title={t('Записать изменения функции')} onClick={() => submitFields({ [`corr_function_${r.function}`]: 1 })}>
                  <SaveIcon fontSize="small" />
                </IconButton>
                <IconButton size="small" color="error" title={t('Восстановить значения')} onClick={() => restoreHeader(r)}>
                  <ReplayIcon fontSize="small" />
                </IconButton>
              </>
            )}
            <IconButton
              size="small"
              color="error"
              title={t('Удалить функцию и все ее параметры')}
              onClick={() => {
                if (window.confirm(t('Удалить функцию и все ее параметры?'))) submitFields({ [`delete_function_${r.function}`]: 1 })
              }}
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          </TableCell>
          <TableCell align="right">{r.function}</TableCell>
        </TableRow>
      )}
      {showParam && (
        <TableRow hover>
          <TableCell>
            <TextField fullWidth variant="standard" value={r.code} title={t('Код параметра')} onChange={(e) => updateRow(r.id, { code: e.target.value })} />
          </TableCell>
          <TableCell>
            {r.is_secret ? (
              // секрет: значение скрыто (маска с сервера); ввести новое — заменить маску, сервер его зашифрует
              <TextField
                fullWidth
                variant="standard"
                type="password"
                autoComplete="new-password"
                value={str(r.value)}
                title={t('Секретное значение (хранится зашифрованным). Чтобы заменить — сотрите и введите новое')}
                onFocus={(e) => e.target.select()}
                onChange={(e) => updateRow(r.id, { value: e.target.value })}
              />
            ) : numeric ? (
              <TextField fullWidth variant="standard" type="number" value={str(r.value)} title={t('Числовое значение параметра')} onChange={(e) => updateRow(r.id, { value: e.target.value })} />
            ) : (
              <TextField fullWidth variant="standard" multiline value={str(r.value)} title={t('Текстовое значение параметра')} onChange={(e) => updateRow(r.id, { value: e.target.value })} />
            )}
          </TableCell>
          <TableCell align="center">
            <Checkbox size="small" checked={numeric} title={t('Числовое значение')} onChange={(e) => toggleIsNumber(r, e.target.checked)} />
          </TableCell>
          <TableCell>
            <TextField
              fullWidth
              variant="standard"
              multiline
              value={str(r.sh_name)}
              title={t('Комментарий к параметру')}
              onChange={(e) => updateRow(r.id, { sh_name: e.target.value })}
              slotProps={{ input: { sx: { color: 'primary.main' } } }}
            />
          </TableCell>
          <TableCell sx={{ whiteSpace: 'nowrap' }}>
            {pChanged && (
              <>
                <IconButton size="small" color="error" title={t('Записать изменения строки')} onClick={() => submitFields({ [`corr_parameter_${r.id}`]: 1 })}>
                  <SaveIcon fontSize="small" />
                </IconButton>
                <IconButton size="small" color="error" title={t('Восстановить значения строки')} onClick={() => restoreParam(r)}>
                  <ReplayIcon fontSize="small" />
                </IconButton>
              </>
            )}
            <IconButton
              size="small"
              color="error"
              title={t('Удалить параметр')}
              onClick={() => {
                if (window.confirm(t('Удалить параметр ID={id} с именем [{code}]?', { id: r.id, code: r.code }))) submitFields({ [`delete_parameter_${r.id}`]: 1 })
              }}
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          </TableCell>
          <TableCell align="right">{r.id}</TableCell>
        </TableRow>
      )}
    </>
  )
}
