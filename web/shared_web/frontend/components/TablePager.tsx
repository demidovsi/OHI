// Общий компонент обоих сайтов (shared_web/frontend): пагинация таблицы с вводом номера страницы и кнопками «первая / предыдущая / следующая / последняя».
// Страница нумеруется с 0. Подходит и для постраничной выборки на сервере (total — общее число строк), и для постраничного показа в браузере.
import { useEffect, useState } from 'react'
import Box from '@mui/material/Box'
import IconButton from '@mui/material/IconButton'
import InputBase from '@mui/material/InputBase'
import TablePagination from '@mui/material/TablePagination'
import Typography from '@mui/material/Typography'
import FirstPageIcon from '@mui/icons-material/FirstPage'
import KeyboardArrowLeftIcon from '@mui/icons-material/KeyboardArrowLeft'
import KeyboardArrowRightIcon from '@mui/icons-material/KeyboardArrowRight'
import LastPageIcon from '@mui/icons-material/LastPage'
import { useT } from '@app/i18n'

const ROWS_OPTIONS = [25, 50, 100, 200]

interface ActionsProps {
  count: number
  page: number
  rowsPerPage: number
  onPageChange: (event: React.MouseEvent<HTMLButtonElement> | null, page: number) => void
}

function Actions({ count, page, rowsPerPage, onPageChange }: ActionsProps) {
  const t = useT()
  const pages = Math.max(1, Math.ceil(count / rowsPerPage))
  const [text, setText] = useState(String(page + 1))
  useEffect(() => setText(String(page + 1)), [page])
  const go = (n: number) => onPageChange(null, Math.min(pages, Math.max(1, n)) - 1)
  const apply = () => {
    const n = parseInt(text, 10)
    if (Number.isFinite(n)) go(n)
    else setText(String(page + 1))
  }
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', ml: 1 }}>
      <IconButton size="small" onClick={() => go(1)} disabled={page === 0} aria-label={t('Первая страница')}><FirstPageIcon fontSize="small" /></IconButton>
      <IconButton size="small" onClick={() => go(page)} disabled={page === 0} aria-label={t('Предыдущая страница')}><KeyboardArrowLeftIcon fontSize="small" /></IconButton>
      <InputBase
        value={text}
        onChange={(e) => setText(e.target.value.replace(/\D/g, ''))}
        onKeyDown={(e) => e.key === 'Enter' && apply()}
        onBlur={apply}
        inputProps={{ 'aria-label': t('Номер страницы'), inputMode: 'numeric', style: { textAlign: 'center', width: 44, padding: '2px 4px' } }}
        sx={{ border: 1, borderColor: 'divider', borderRadius: 0.75, mx: 0.5 }}
      />
      <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5, whiteSpace: 'nowrap' }}>{`${t('из')} ${pages.toLocaleString()}`}</Typography>
      <IconButton size="small" onClick={() => go(page + 2)} disabled={page >= pages - 1} aria-label={t('Следующая страница')}><KeyboardArrowRightIcon fontSize="small" /></IconButton>
      <IconButton size="small" onClick={() => go(pages)} disabled={page >= pages - 1} aria-label={t('Последняя страница')}><LastPageIcon fontSize="small" /></IconButton>
    </Box>
  )
}

interface Props {
  total: number
  /** Номер страницы с 0. */
  page: number
  rows: number
  onPage: (page: number) => void
  onRows: (rows: number) => void
}

export default function TablePager({ total, page, rows, onPage, onRows }: Props) {
  const t = useT()
  return (
    <TablePagination
      component="div"
      // подпись, выбор числа строк, диапазон и кнопки не помещаются в одну строку — переносятся на следующие (пространство-распорка выключено,
      // иначе при переносе кнопки уезжают вправо отдельно от подписи)
      sx={{
        flexShrink: 0,
        '& .MuiTablePagination-toolbar': { flexWrap: 'wrap', justifyContent: 'flex-end', rowGap: 0.5, minHeight: 'auto', py: 0.5 },
        '& .MuiTablePagination-spacer': { display: 'none' },
        '& .MuiTablePagination-selectLabel, & .MuiTablePagination-displayedRows': { my: 0.5 },
      }}
      count={total}
      page={Math.min(page, Math.max(0, Math.ceil(total / rows) - 1))}
      rowsPerPage={rows}
      rowsPerPageOptions={ROWS_OPTIONS}
      ActionsComponent={Actions}
      onPageChange={(_, p) => onPage(p)}
      onRowsPerPageChange={(e) => onRows(Number(e.target.value))}
      labelRowsPerPage={t('Строк на странице')}
      labelDisplayedRows={({ from, to, count }) => `${from}–${to} (${count.toLocaleString()})`}
    />
  )
}
