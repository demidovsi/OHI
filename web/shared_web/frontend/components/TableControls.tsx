import { useEffect, useState } from 'react'
import Box from '@mui/material/Box'
import FormControl from '@mui/material/FormControl'
import IconButton from '@mui/material/IconButton'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Pagination from '@mui/material/Pagination'
import Select from '@mui/material/Select'
import TextField from '@mui/material/TextField'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import Typography from '@mui/material/Typography'
import RefreshIcon from '@mui/icons-material/Refresh'
import type { FormFields, Par } from '@app/api'
import { useT } from '@app/i18n'
import SearchField from './SearchField'

// Общий компонент обоих сайтов (shared_web/frontend). Тулбар и пагинация сохраняют свою высоту (flexShrink: 0)
// в странице PAGE_SX — прокручивается только таблица (FILL_SX). Раскладка через flex/gap, поэтому в иврите
// (rtl, kns-web) зеркалится сама.

// Общие элементы серверных таблиц — аналоги include/top_of_table.html,
// include/sort_table.html и include/pages_table.html. Имена полей — те же,
// что читает common.define_param_for_page.

const ROW_COUNTS = [5, 10, 15, 25, 50, 100]

interface Props {
  par: Par
  onSubmit: (fields: FormFields) => void
  /** Дополнительные поля, которые всегда должны уходить на сервер вместе с действием. */
  base?: FormFields
  hideSearch?: boolean
  hideSort?: boolean
}

export function baseFields(par: Par): FormFields {
  // Поля, которые старая форма отправляла всегда (иначе сервер трактует их отсутствие как сброс).
  return {
    row_count: par.row_count,
    page: par.page,
    search: par.search ?? '',
    sort: par.selected_sort,
    scroll: 0,
  }
}

export function TableToolbar({ par, onSubmit, base, hideSearch, hideSort }: Props) {
  const t = useT()
  const [search, setSearch] = useState<string>(par.search ?? '')
  useEffect(() => setSearch(par.search ?? ''), [par.search])
  const fields = (extra: FormFields): FormFields => ({ ...baseFields(par), ...base, ...extra })

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center', mb: 1.5, flexShrink: 0 }}>
      {!par.no_pages && (
        <FormControl sx={{ minWidth: 90 }}>
          <InputLabel id="row_count_label">{t('Строк')}</InputLabel>
          <Select
            labelId="row_count_label"
            label={t('Строк')}
            value={par.row_count ?? 5}
            onChange={(e) => onSubmit(fields({ row_count: Number(e.target.value), page: 1 }))}
          >
            {ROW_COUNTS.map((n) => (
              <MenuItem key={n} value={n}>
                {n}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      )}

      <Typography variant="body2" color="text.secondary">
        {!par.no_pages && par.count > 0 && t('Вывод с {first} по {last} ', { first: par.first, last: par.last })}
        {t('(Всего строк = {count})', { count: par.count ?? 0 })}
      </Typography>

      {!par.no_refresh && (
        <IconButton size="small" title={t('Обновить таблицу')} onClick={() => onSubmit(fields({ refresh_table: 1 }))}>
          <RefreshIcon fontSize="small" />
        </IconButton>
      )}

      {!hideSearch && !par.no_search && (
        <SearchField
          onClear={() => {
            setSearch('')
            onSubmit(fields({ search: '', page: 1 }))
          }}
          label={par.search_label ? String(par.search_label).replace(/:\s*$/, '') : t('Поиск')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onSubmit(fields({ search, page: 1 }))
          }}
          onBlur={() => {
            if (search !== (par.search ?? '')) onSubmit(fields({ search, page: 1 }))
          }}
          title={par.title_search ? t(par.title_search) : t('Фильтрация выводимых строк таблицы')}
          // рядом с поисками по отдельным колонкам (logs: Operation/Source/Who) — той же ширины
          sx={(par.extra_searches ?? []).length ? SEARCH_FIELD_SX : { width: 300 }}
        />
      )}

      {!hideSearch &&
        !par.no_search &&
        (par.extra_searches ?? []).map((extra: ExtraSearch) => (
          <ExtraSearchField key={extra.name} extra={extra} onSubmit={(value) => onSubmit(fields({ [extra.name]: value, page: 1 }))} />
        ))}

      {!hideSort && Array.isArray(par.array_sort) && par.array_sort.length > 0 && (
        <>
          <FormControl sx={{ minWidth: 200 }}>
            <InputLabel id="sort_label">{t('Сортировка')}</InputLabel>
            <Select
              labelId="sort_label"
              label={t('Сортировка')}
              value={par.selected_sort ?? ''}
              onChange={(e) => onSubmit(fields({ sort: String(e.target.value) }))}
            >
              {par.array_sort.map((u: { id: string; sh_name: string }) => (
                <MenuItem key={u.id} value={u.id}>
                  {t(u.sh_name)}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={par.sort_trend}
            onChange={(_, v) => {
              if (v === 0) onSubmit(fields({ sort_trend0: 1 }))
              if (v === 1) onSubmit(fields({ sort_trend1: 1 }))
            }}
          >
            <ToggleButton value={0} title={t('По возрастанию')}>
              ↑
            </ToggleButton>
            <ToggleButton value={1} title={t('По убыванию')}>
              ↓
            </ToggleButton>
          </ToggleButtonGroup>
        </>
      )}
    </Box>
  )
}

/** Ширина полей поиска по отдельным колонкам (и основного поиска рядом с ними; Log). */
const SEARCH_FIELD_SX = { width: 140 } as const

// Дополнительный поисковый образ по отдельной колонке (par.extra_searches, напр. logs: level/source/who).
interface ExtraSearch {
  name: string
  label: string
  value: string
  title?: string
}

function ExtraSearchField({ extra, onSubmit }: { extra: ExtraSearch; onSubmit: (value: string) => void }) {
  const t = useT()
  const [value, setValue] = useState<string>(extra.value ?? '')
  useEffect(() => setValue(extra.value ?? ''), [extra.value])
  return (
    <SearchField
      onClear={() => {
        setValue('')
        onSubmit('')
      }}
      label={extra.label.replace(/:\s*$/, '')}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') onSubmit(value)
      }}
      onBlur={() => {
        if (value !== (extra.value ?? '')) onSubmit(value)
      }}
      title={extra.title ? t(extra.title) : undefined}
      sx={SEARCH_FIELD_SX}
    />
  )
}

export function TablePagination({ par, onSubmit, base }: Props) {
  if (!(par.count > par.row_count)) return null
  const fields = (extra: FormFields): FormFields => ({ ...baseFields(par), ...base, ...extra })
  const pageCount = Number(par.page_count ?? 1)
  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 2, py: 1.5, flexWrap: 'wrap', flexShrink: 0 }}>
      <PageInput page={Number(par.page ?? 1)} pageCount={pageCount} onGo={(p) => onSubmit(fields({ page: p }))} />
      <Pagination
        count={pageCount}
        page={par.page ?? 1}
        showFirstButton
        showLastButton
        siblingCount={2}
        onChange={(_, p) => onSubmit(fields({ page: p }))}
        color="primary"
      />
    </Box>
  )
}

/** Поле номера страницы (как «Page:» в старом UI): Enter или уход из поля — переход на страницу. */
function PageInput({ page, pageCount, onGo }: { page: number; pageCount: number; onGo: (page: number) => void }) {
  const t = useT()
  const [value, setValue] = useState(String(page))
  useEffect(() => setValue(String(page)), [page])
  const go = () => {
    const n = Math.round(Number(value))
    if (!Number.isFinite(n) || n < 1 || n > pageCount) {
      setValue(String(page)) // вне диапазона — вернуть текущую страницу
      return
    }
    if (n !== page) onGo(n)
  }
  return (
    <TextField
      label={t('Страница')}
      type="number"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') go()
      }}
      onBlur={go}
      title={t('Номер страницы (1–{n}); Enter — перейти', { n: pageCount })}
      slotProps={{ htmlInput: { min: 1, max: pageCount, step: 1 } }}
      sx={{ width: 110 }}
    />
  )
}
