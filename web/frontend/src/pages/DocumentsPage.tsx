import { useRef, useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import IconButton from '@mui/material/IconButton'
import Link from '@mui/material/Link'
import Paper from '@mui/material/Paper'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import DeleteIcon from '@mui/icons-material/Delete'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import { useForm } from '../useForm'
import type { FlashMessage } from '../api'
import { useAuth } from '../auth'
import { useT } from '../i18n'
import FlashMessages from '../components/FlashMessages'
import LoadingBar from '../components/LoadingBar'
import { FILL_SX, PAGE_SX } from '../components/layout'
import { ColGroup, ResizableHeadCell, resizableTableSx, useColumnWidths } from '@shared-web/components/columnResize'

// «Документы» (только администратор): загрузка файла в бакет и запись его метаданных в БД (nsi_documents).
// Бэкенд — documents.py; загрузка — multipart на /api/v2/documents/upload, список — форма documents.

interface DocRow {
  id: number
  sh_name: string
  content_type: string | null
  size: number
  description: string | null
  uploaded_by: string | null
  inserted_date: string | null
}

// Ширины колонок (px) по умолчанию; меняются мышью в шапке и запоминаются в браузере (двойной щелчок — по умолчанию)
const COLS = { id: 70, name: 300, size: 100, type: 170, date: 170, user: 130, description: 280, actions: 110 }
const COL_KEYS = Object.keys(COLS)

const sizeText = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`)

/** Время из БД (UTC без зоны) → время браузера. */
function localTime(utc: string | null, locale?: string): string {
  if (!utc) return ''
  const d = new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(utc) ? utc : utc + 'Z')
  return Number.isNaN(d.getTime()) ? utc : d.toLocaleString(locale)
}

export default function DocumentsPage() {
  const t = useT()
  const widths = useColumnWidths('documents_cols', COLS)
  const { logout } = useAuth()
  const { par, messages, loading, error, submit, dismiss } = useForm('documents')
  const [file, setFile] = useState<File | null>(null)
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [local, setLocal] = useState<FlashMessage[]>([])
  const input = useRef<HTMLInputElement>(null)

  if (error) return <Typography color="error">{error}</Typography>
  if (!par) return <LoadingBar loading />

  const rows: DocRow[] = par.data ?? []
  const maxSize: number = par.max_size ?? 30 * 1024 * 1024
  const tooBig = file != null && file.size > maxSize
  const locale = document.documentElement.lang || undefined

  const notify = (category: string, text: string) => setLocal((m) => [...m, [category, text]])

  async function call(url: string, init?: RequestInit): Promise<{ ok: boolean; message: string } | null> {
    const res = await fetch(url, { credentials: 'same-origin', ...init })
    if (res.status === 401) {
      logout()
      return null
    }
    const body = await res.json().catch(() => ({}))
    return { ok: Boolean(body.ok), message: String(body.message ?? body.error ?? res.statusText) }
  }

  const upload = async () => {
    if (!file || tooBig) return
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('description', description)
      const r = await call('/api/v2/documents/upload', { method: 'POST', body: fd })
      if (!r) return
      notify(r.ok ? 'success' : 'warning', r.message)
      if (r.ok) {
        setFile(null)
        setDescription('')
        if (input.current) input.current.value = ''
        submit({}) // обновить список
      }
    } catch (e) {
      notify('warning', (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (row: DocRow) => {
    if (!window.confirm(`${t('Удалить документ')} «${row.sh_name}»?`)) return
    const r = await call(`/api/v2/documents/${row.id}/delete`, { method: 'POST' })
    if (!r) return
    notify(r.ok ? 'success' : 'warning', r.message)
    submit({})
  }

  return (
    <Box sx={PAGE_SX}>
      <FlashMessages messages={[...messages, ...local]} onDismiss={(i) => (i < messages.length ? dismiss(i) : setLocal((m) => m.filter((_, j) => j !== i - messages.length)))} />
      <LoadingBar loading={loading || busy} />

      {par.table_missing && (
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          {t('Таблица nsi_documents не создана: выполните scripts/create_nsi_documents.sql в базе данных')}
        </Alert>
      )}

      <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5, flexShrink: 0 }}>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
          <input
            ref={input}
            type="file"
            hidden
            accept={(par.allowed ?? []).map((e: string) => '.' + e).join(',')}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Button size="small" variant="outlined" startIcon={<UploadFileIcon />} onClick={() => input.current?.click()}>
            {t('Выбрать файл')}
          </Button>
          <Typography variant="body2" color={tooBig ? 'error' : 'text.secondary'} sx={{ minWidth: 160 }}>
            {file ? `${file.name} (${sizeText(file.size)})` : t('Файл не выбран')}
          </Typography>
          <TextField
            size="small"
            label={t('Описание')}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            sx={{ flex: '1 1 260px', minWidth: 200 }}
          />
          <Button size="small" variant="contained" disabled={!file || tooBig || busy || Boolean(par.table_missing)} onClick={upload}>
            {t('Загрузить')}
          </Button>
        </Box>
        <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 1 }}>
          {t('Бакет')}: {par.bucket}; {t('максимальный размер')}: {sizeText(maxSize)}; {t('типы файлов')}: {(par.allowed ?? []).join(', ')}
        </Typography>
      </Paper>

      <TableContainer component={Paper} variant="outlined" sx={FILL_SX}>
        <Table size="small" stickyHeader sx={resizableTableSx(COL_KEYS, widths)}>
          <ColGroup keys={COL_KEYS} widths={widths} />
          <TableHead>
            <TableRow>
              <ResizableHeadCell colKey="id" widths={widths}>ID</ResizableHeadCell>
              <ResizableHeadCell colKey="name" widths={widths}>{t('Документ')}</ResizableHeadCell>
              <ResizableHeadCell colKey="size" widths={widths} align="right">{t('Размер')}</ResizableHeadCell>
              <ResizableHeadCell colKey="type" widths={widths}>{t('Тип')}</ResizableHeadCell>
              <ResizableHeadCell colKey="date" widths={widths}>{t('Загружен')}</ResizableHeadCell>
              <ResizableHeadCell colKey="user" widths={widths}>{t('Кто загрузил')}</ResizableHeadCell>
              <ResizableHeadCell colKey="description" widths={widths}>{t('Описание')}</ResizableHeadCell>
              <ResizableHeadCell colKey="actions" widths={widths} />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id} hover>
                <TableCell sx={{ verticalAlign: 'top' }}>{r.id}</TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>
                  <Link href={`/api/v2/documents/${r.id}/download`} underline="hover" title={t('Скачать')}>
                    {r.sh_name}
                  </Link>
                </TableCell>
                <TableCell align="right" sx={{ verticalAlign: 'top', whiteSpace: 'nowrap' }}>{sizeText(r.size)}</TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>{r.content_type}</TableCell>
                <TableCell sx={{ verticalAlign: 'top', whiteSpace: 'nowrap' }}>{localTime(r.inserted_date, locale)}</TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>{r.uploaded_by}</TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>{r.description}</TableCell>
                <TableCell sx={{ verticalAlign: 'top' }}>
                  <IconButton size="small" color="error" title={t('Удалить документ')} onClick={() => remove(r)}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </TableCell>
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
    </Box>
  )
}
